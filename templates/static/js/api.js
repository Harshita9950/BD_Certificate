"use strict";

const CSRF_COOKIE = "tl_csrftoken";
const UNSAFE      = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function getCsrf() {
    const row = document.cookie.split("; ").find(r => r.startsWith(CSRF_COOKIE + "="));
    return row ? decodeURIComponent(row.split("=")[1]) : "";
}

class ApiError extends Error {
    constructor(status, code, detail, data) {
        super(String(detail));
        this.name   = "ApiError";
        this.status = status;
        this.code   = code;
        this.detail = detail;
        this.data   = data;
    }
}

async function request(method, path, body = null, extra = {}) {
    const headers = { "Accept": "application/json", "Content-Type": "application/json", ...extra };

    if (UNSAFE.has(method.toUpperCase())) {
        headers["X-CSRFToken"] = getCsrf();
    }

    const init = { method: method.toUpperCase(), headers, credentials: "include" };
    if (body !== null && UNSAFE.has(method.toUpperCase())) {
        init.body = JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(path, init);
    } catch {
        throw new ApiError(0, "network_error", "Network error — could not reach the server.", null);
    }

    if (response.status === 401) {
        window.location.href = "/login/?next=" + encodeURIComponent(window.location.pathname);
        throw new ApiError(401, "not_authenticated", "Session expired.", null);
    }

    if (response.status === 403) {
        const data = await _safeJson(response);
        throw new ApiError(403, data?.code || "forbidden", data?.detail || "Access denied.", data);
    }

    if (!response.ok) {
        const data = await _safeJson(response);
        throw new ApiError(response.status, data?.code || "api_error", data?.detail || `HTTP ${response.status}`, data);
    }

    return response.status === 204 ? null : response.json();
}

async function _safeJson(r) {
    try { return await r.json(); } catch { return null; }
}

const api = {
    get:    (path, headers = {})            => request("GET",    path, null, headers),
    post:   (path, body = {}, headers = {}) => request("POST",   path, body, headers),
    put:    (path, body = {}, headers = {}) => request("PUT",    path, body, headers),
    patch:  (path, body = {}, headers = {}) => request("PATCH",  path, body, headers),
    delete: (path, headers = {})            => request("DELETE", path, null, headers),
    ApiError,
    getCsrf,
};

export default api;
export { ApiError, getCsrf };
