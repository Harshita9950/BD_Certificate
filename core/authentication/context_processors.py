"""
core/authentication/context_processors.py
============================================
Django template context processors for authentication context.

Makes auth_context available in all Django templates without
requiring each view to explicitly pass it.

Configured in settings.py TEMPLATES[0]['OPTIONS']['context_processors'].

Usage in templates:
    {{ auth_user.get_full_name }}
    {{ auth_ulb_code }}
    {{ auth_role }}
    {% if 'application.approve' in auth_permissions %}...{% endif %}
"""

from django.conf import settings


def auth_context(request):
    """
    Inject the current user's auth context into every template.
    Reads from request.auth_context populated by TLPortalAuthMiddleware.
    Falls back gracefully if the middleware hasn't run (e.g. in tests).
    """
    ctx = getattr(request, 'auth_context', {})
    return {
        'auth_user':        ctx.get('user'),
        'auth_is_authenticated': ctx.get('is_authenticated', False),
        'auth_ulb_code':    ctx.get('ulb_code', ''),
        'auth_role':        ctx.get('role', ''),
        'auth_app_code':    ctx.get('app_code', 'TRADE_LICENSE'),
        'auth_permissions': ctx.get('permissions', set()),
        'central_portal_enabled': getattr(settings, 'CENTRAL_PORTAL_ENABLED', False),
    }
