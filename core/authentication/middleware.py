"""
core/authentication/middleware.py
====================================
Centralised authentication and session validation middleware.

Middleware in this file runs on EVERY request before it reaches a view.
It handles concerns that must be consistent across the entire application:

  1. TLPortalAuthMiddleware
     - Attaches auth_context to request (user, ulb, app_code, roles, permissions)
     - This context is available in ALL views via request.auth_context

  2. SessionValidationMiddleware
     - Detects expired or invalid sessions early
     - Clears stale sessions cleanly rather than letting Django propagate errors
     - Returns a centralised 401 JSON response for API requests

  3. ApplicationAccessMiddleware
     - When CENTRAL_PORTAL_ENABLED=True, verifies the user has application access
     - Skips public endpoints (login, CSRF, registration, admin, static)
     - Returns a centralised 403 JSON response for denied access

Ordering in settings.MIDDLEWARE (after SessionMiddleware, before CommonMiddleware):
    ...
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core.authentication.middleware.TLPortalAuthMiddleware',
    'core.authentication.middleware.SessionValidationMiddleware',
    'core.authentication.middleware.ApplicationAccessMiddleware',
    'django.middleware.common.CommonMiddleware',
    ...
"""

import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# URL path prefixes that never require authentication
_PUBLIC_PREFIXES = (
    '/admin/',
    '/api/auth/csrf/',
    '/api/auth/login/',
    '/api/auth/sso/',
    '/api/users/register/',
    '/static/',
    '/media/',
    '/favicon.ico',
)


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def _api_request(request) -> bool:
    """True if the request expects a JSON API response."""
    return (
        request.path.startswith('/api/')
        or 'application/json' in request.META.get('HTTP_ACCEPT', '')
    )


def _json_401(detail: str) -> JsonResponse:
    return JsonResponse({'detail': detail, 'code': 'not_authenticated'}, status=401)


def _json_403(detail: str, code: str = 'permission_denied') -> JsonResponse:
    return JsonResponse({'detail': detail, 'code': code}, status=403)


# ─── 1. Auth Context Middleware ───────────────────────────────────────────────

class TLPortalAuthMiddleware(MiddlewareMixin):
    """
    Attaches a rich `auth_context` dict to every request.

    After this middleware runs, any view can access:
        request.auth_context['user']         → User instance or None
        request.auth_context['is_authenticated']
        request.auth_context['ulb_code']     → str or ''
        request.auth_context['role']         → str role code or ''
        request.auth_context['app_code']     → application code string
        request.auth_context['permissions']  → set of permission code strings

    This is the single source of truth for "who is the current user"
    and "what can they do".  Views and templates should read from here
    rather than directly interrogating request.user.role / request.user.ulb_code.
    """

    def process_request(self, request):
        user = getattr(request, 'user', None)
        is_auth = bool(user and user.is_authenticated and user.is_active)

        request.auth_context = {
            'user':             user if is_auth else None,
            'is_authenticated': is_auth,
            'ulb_code':         getattr(user, 'ulb_code', '') if is_auth else '',
            'role':             getattr(user, 'role', '')     if is_auth else '',
            'app_code':         getattr(settings, 'CENTRAL_PORTAL_APPLICATION_CODE',
                                        'BIRTH_DEATH'),
            'permissions':      self._load_permissions(user) if is_auth else set(),
        }

    @staticmethod
    def _load_permissions(user) -> set:
        """
        Load the permission codes for this user's role.
        Returns an empty set on any error so auth never breaks from a DB issue.
        """
        try:
            from users.models import UserRole, Role
            if user.role == UserRole.ADMIN or user.is_superuser:
                # Admins hold all permissions — return sentinel
                return {'*'}
            role_obj = Role.objects.filter(
                code=user.role, is_active=True
            ).prefetch_related('permissions').first()
            if role_obj is None:
                return set()
            return set(role_obj.permissions.values_list('code', flat=True))
        except Exception:
            logger.exception('TLPortalAuthMiddleware: error loading permissions for %s', user)
            return set()


# ─── 2. Session Validation Middleware ────────────────────────────────────────

class SessionValidationMiddleware(MiddlewareMixin):
    """
    Detects and handles session anomalies before they reach views.

    Scenarios handled:
      A. Valid session + active user  → pass through (most requests)
      B. No session at all            → pass through (public endpoints)
      C. Session exists but user is_active=False  → flush session, 401
      D. Session references a deleted/missing user → flush session, 401

    This middleware acts early so that individual views never encounter
    a "ghost" session pointing at a non-existent or deactivated user.
    """

    def process_request(self, request):
        if _is_public(request.path):
            return None

        user = getattr(request, 'user', None)
        if user is None or user.is_anonymous:
            # No session — let permission classes handle it per-view
            return None

        # Session references a deactivated account
        if not user.is_active:
            logger.warning(
                'SessionValidationMiddleware: flushing session for inactive user %s',
                getattr(user, 'email', 'unknown'),
            )
            request.session.flush()
            if _api_request(request):
                from .exceptions import AccountInactiveError
                exc = AccountInactiveError()
                return _json_401(str(exc.detail))
            return None   # HTML pages redirect via LoginView

        return None  # All good — continue to view


# ─── 3. Application Access Middleware ────────────────────────────────────────

class ApplicationAccessMiddleware(MiddlewareMixin):
    """
    When CENTRAL_PORTAL_ENABLED=True, verifies that every authenticated
    user has an active UserApplicationAccess record for the configured
    application (CENTRAL_PORTAL_APPLICATION_CODE).

    In local mode (CENTRAL_PORTAL_ENABLED=False) this middleware is a no-op.

    Public endpoints listed in _PUBLIC_PREFIXES are always bypassed.

    This middleware is the enforcement point so that individual views
    don't need to repeat the application-access check.
    """

    def process_request(self, request):
        if not getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            return None

        if _is_public(request.path):
            return None

        user = getattr(request, 'user', None)
        if user is None or user.is_anonymous:
            return None  # Auth check is handled by permission classes

        app_code = getattr(settings, 'CENTRAL_PORTAL_APPLICATION_CODE', 'BIRTH_DEATH')
        if not user.has_application_access(app_code):
            logger.warning(
                'ApplicationAccessMiddleware: user %s denied %s access',
                user.email, app_code,
            )
            if _api_request(request):
                from .exceptions import ApplicationAccessDeniedError
                exc = ApplicationAccessDeniedError()
                return _json_403(str(exc.detail), 'application_access_denied')
            # For non-API requests redirect to a denial page (future)
            return _json_403(str(ApplicationAccessDeniedError().detail), 'application_access_denied')

        return None
