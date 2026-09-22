"""
core/authentication/decorators.py
====================================
View-level authentication and authorisation decorators.

These decorators are a thin convenience layer over the DRF permission
classes defined in permissions.py.  They are provided for:
  - Function-based views
  - Django template views (non-DRF)
  - Exceptional per-view overrides

For DRF APIViews and ViewSets, use permission_classes instead.
For global defaults, use settings.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'].

Decorators available
--------------------
  @login_required_api     — 401 JSON response if not authenticated
  @require_role(*roles)   — 403 JSON response if role not in set
  @require_permission(code) — 403 JSON response if permission code absent
  @require_app_access     — 403 JSON response if no TRADE_LICENSE access
  @require_ulb_match      — 403 JSON response on cross-ULB object access
"""

import functools
import logging

from django.http import JsonResponse

from .exceptions import (
    ApplicationAccessDeniedError,
    AuthenticationError,
    AuthorisationError,
    NotAuthenticatedError,
    PermissionDeniedError,
    RoleRequiredError,
)

logger = logging.getLogger(__name__)


def _json_error(exc: Exception) -> JsonResponse:
    """Convert a centralised auth exception to a JsonResponse."""
    from rest_framework import status as drf_status

    if isinstance(exc, AuthenticationError):
        http_status = exc.status_code
    elif isinstance(exc, AuthorisationError):
        http_status = exc.status_code
    else:
        http_status = drf_status.HTTP_500_INTERNAL_SERVER_ERROR

    detail = exc.detail if hasattr(exc, 'detail') else str(exc)
    return JsonResponse({'detail': str(detail)}, status=http_status)


# ─── @login_required_api ─────────────────────────────────────────────────────

def login_required_api(view_func):
    """
    Decorator for function-based views and Django template views.
    Returns 401 JSON if request.user is anonymous or inactive.
    For DRF APIViews use permission_classes = [IsAuthenticatedUser] instead.

    Usage:
        @login_required_api
        def my_view(request):
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return _json_error(NotAuthenticatedError())
        if not request.user.is_active:
            from .exceptions import AccountInactiveError
            return _json_error(AccountInactiveError())
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── @require_role ────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Decorator factory: restricts access to users whose role is in *roles.

    Usage:
        @require_role('OFFICER', 'COMMISSIONER')
        def approve_application(request, pk):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return _json_error(NotAuthenticatedError())
            if request.user.role not in roles:
                logger.warning(
                    'require_role: user %s (role=%s) denied; requires %s',
                    request.user.email, request.user.role, roles,
                )
                return _json_error(
                    RoleRequiredError(
                        detail=f'Requires one of: {", ".join(roles)}'
                    )
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── @require_permission ──────────────────────────────────────────────────────

def require_permission(permission_code: str):
    """
    Decorator factory: restricts access to users whose Role includes the
    named Permission code (e.g. 'application.approve').

    Usage:
        @require_permission('license.generate')
        def generate_licence(request, pk):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return _json_error(NotAuthenticatedError())
            from .permissions import HasPermission
            if not HasPermission._user_has_permission(request.user, permission_code):
                logger.warning(
                    'require_permission: user %s denied; requires %s',
                    request.user.email, permission_code,
                )
                return _json_error(
                    PermissionDeniedError(
                        detail=f'Required permission: {permission_code}'
                    )
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── @require_app_access ─────────────────────────────────────────────────────

def require_app_access(view_func):
    """
    Decorator: enforces that the user has an active UserApplicationAccess
    record for TRADE_LICENSE.

    Only meaningful when CENTRAL_PORTAL_ENABLED=True.
    In local mode this is a no-op (all authenticated users are allowed).

    Usage:
        @require_app_access
        def dashboard(request):
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings
        if not request.user or not request.user.is_authenticated:
            return _json_error(NotAuthenticatedError())
        if getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            if not request.user.has_application_access('TRADE_LICENSE'):
                logger.warning(
                    'require_app_access: user %s denied TRADE_LICENSE access',
                    request.user.email,
                )
                return _json_error(ApplicationAccessDeniedError())
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── @require_ulb_match ───────────────────────────────────────────────────────

def require_ulb_match(get_obj_ulb):
    """
    Decorator factory: enforces ULB isolation at the view level.
    `get_obj_ulb` is a callable that receives (request, *args, **kwargs)
    and returns the ULB code of the object being accessed.

    ADMIN role bypasses this check.

    Usage:
        @require_ulb_match(lambda req, pk: Application.objects.get(pk=pk).ulb_code)
        def application_detail(request, pk):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from users.models import UserRole
            if not request.user or not request.user.is_authenticated:
                return _json_error(NotAuthenticatedError())
            if request.user.role != UserRole.ADMIN and not request.user.is_superuser:
                try:
                    obj_ulb = get_obj_ulb(request, *args, **kwargs)
                except Exception:
                    obj_ulb = None
                if obj_ulb and request.user.ulb_code and obj_ulb != request.user.ulb_code:
                    from .exceptions import ULBAccessDeniedError
                    logger.warning(
                        'require_ulb_match: user %s (ulb=%s) denied access to ulb=%s',
                        request.user.email, request.user.ulb_code, obj_ulb,
                    )
                    return _json_error(ULBAccessDeniedError())
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
