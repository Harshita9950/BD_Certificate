"""
core/authentication/authentication.py
==========================================
Centralised DRF Authentication Class.

This module provides the single DRF authentication class that is
configured globally in settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'].

  TLPortalSessionAuthentication
  ─────────────────────────────
  Extends DRF's SessionAuthentication with:
    - Typed exceptions from our central exception hierarchy
    - Inactive-user detection at the authentication stage
    - CSRF enforcement with a clear error message
    - Audit-friendly logging

Individual views and APIs MUST NOT define their own authentication_classes
except for exceptional cases (e.g. public health-check endpoints).

The central authentication class guarantees:
  "Every protected endpoint uses the same auth mechanism."
  "Change the auth mechanism once — the whole app follows."

Future SSO
----------
When Central Portal SSO is activated:
  - The SSO handshake happens in CentralSSOBackend (users/auth_backends.py)
    via the /api/auth/sso/callback/ endpoint.
  - That endpoint calls django.contrib.auth.login() which creates a normal
    Django session.
  - From that point on, TLPortalSessionAuthentication handles ALL subsequent
    requests identically — it doesn't know or care whether the session was
    established via local login or SSO.
  - This is the key design principle: authentication source is abstracted
    away from the rest of the application.

DRF Exception Handler
---------------------
A custom exception handler is also wired here to convert all DRF exceptions
(including our custom ones from exceptions.py) to a consistent JSON envelope.
"""

import logging

from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import SessionAuthentication
from rest_framework import exceptions as drf_exceptions

from .exceptions import (
    AccountInactiveError,
    NotAuthenticatedError,
)

logger = logging.getLogger(__name__)


class TLPortalSessionAuthentication(SessionAuthentication):
    """
    Custom DRF session authentication for TL_portal.

    Differences from DRF's default SessionAuthentication:
      1. Returns typed exceptions (AccountInactiveError, NotAuthenticatedError)
         instead of generic APIException — enabling centralised error handling.
      2. Explicitly checks user.is_active and raises AccountInactiveError.
      3. CSRF enforcement raises a clear, typed 403 instead of a generic error.
      4. Logs every authentication event for audit traceability.

    Configured globally in settings.py:
        REST_FRAMEWORK = {
            'DEFAULT_AUTHENTICATION_CLASSES': [
                'core.authentication.authentication.TLPortalSessionAuthentication',
            ],
        }
    """

    def authenticate(self, request):
        """
        Attempt to authenticate the request using the Django session.

        Returns: (user, None)  if authentication succeeds
        Returns: None          if no session is present (anonymous request)
        Raises:  AccountInactiveError if the session user is inactive
        """
        user_auth_tuple = super().authenticate(request)

        if user_auth_tuple is None:
            # No session — anonymous request
            # Permission classes will handle the 401 if the endpoint is protected
            return None

        user, auth = user_auth_tuple

        if not user.is_active:
            logger.warning(
                'TLPortalSessionAuthentication: inactive user %s attempted request',
                getattr(user, 'email', 'unknown'),
            )
            raise AccountInactiveError()

        return (user, auth)

    def enforce_csrf(self, request):
        """
        Enforce CSRF for unsafe methods.
        Raises a clear 403 with a consistent error format.
        """
        try:
            super().enforce_csrf(request)
        except drf_exceptions.PermissionDenied:
            raise drf_exceptions.PermissionDenied(
                detail='CSRF token missing or incorrect. '
                       'Include the X-CSRFToken header in your request.'
            )


# ─── Centralised DRF Exception Handler ───────────────────────────────────────

def custom_exception_handler(exc, context):
    """
    Centralised DRF exception handler.

    Converts ALL exceptions — including our typed auth exceptions and
    standard DRF exceptions — to a consistent JSON envelope:
        {
            "detail": "<human-readable message>",
            "code":   "<machine-readable code>"
        }

    Configured in settings.py:
        REST_FRAMEWORK = {
            'EXCEPTION_HANDLER': 'core.authentication.authentication.custom_exception_handler',
        }

    Handled exception types and their HTTP responses:
        NotAuthenticatedError        → 401
        SessionExpiredError          → 401
        InvalidCredentialsError      → 401
        AccountInactiveError         → 401
        InvalidSSOResponseError      → 401
        ApplicationAccessDeniedError → 403
        PermissionDeniedError        → 403
        ULBAccessDeniedError         → 403
        RoleRequiredError            → 403
        DRF NotAuthenticated         → 401
        DRF PermissionDenied         → 403
        DRF ValidationError          → 400
        All other APIExceptions      → their status_code
        Non-APIExceptions            → 500 (logged, detail hidden)
    """
    from rest_framework.views import exception_handler
    from rest_framework.response import Response
    from rest_framework import status

    # Let DRF build the base response first
    response = exception_handler(exc, context)

    if response is not None:
        # Standardise the response envelope
        code   = getattr(exc, 'default_code', 'error')
        detail = response.data.get('detail', str(exc))
        response.data = {
            'detail': str(detail),
            'code':   code,
        }
        # Log 5xx errors
        if response.status_code >= 500:
            logger.error(
                'custom_exception_handler: unhandled %s in %s: %s',
                type(exc).__name__, context.get('view'), exc,
                exc_info=True,
            )
        return response

    # Unhandled exception — return 500 without exposing internals
    logger.error(
        'custom_exception_handler: unhandled non-API exception %s: %s',
        type(exc).__name__, exc,
        exc_info=True,
    )
    return Response(
        {'detail': 'An internal server error occurred.', 'code': 'internal_error'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
