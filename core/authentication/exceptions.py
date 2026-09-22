"""
core/authentication/exceptions.py
===================================
Centralised authentication and authorisation exception hierarchy.

ALL authentication/authorisation errors raised anywhere in the application
should use one of these types.  They are caught and converted to the
appropriate HTTP response in one place:
  - DRF exception handler  →  core/authentication/authentication.py
  - Middleware              →  core/authentication/middleware.py

This means individual views and business modules never need to know
which HTTP status code maps to which error condition.

Exception hierarchy
-------------------
AuthenticationError
    ├── NotAuthenticatedError       → 401  (no session / anonymous)
    ├── SessionExpiredError         → 401  (session existed but is stale)
    ├── InvalidCredentialsError     → 401  (wrong email/password)
    ├── AccountInactiveError        → 401  (user.is_active == False)
    └── InvalidSSOResponseError     → 401  (Central Portal returned bad data)

AuthorisationError
    ├── ApplicationAccessDeniedError → 403  (no UserApplicationAccess record)
    ├── PermissionDeniedError        → 403  (missing role/permission)
    ├── ULBAccessDeniedError         → 403  (cross-ULB data access attempt)
    └── RoleRequiredError            → 403  (action requires a specific role)
"""

from rest_framework import status
from rest_framework.exceptions import APIException


# ─── Base types ───────────────────────────────────────────────────────────────

class AuthenticationError(APIException):
    """Base for all 401-class authentication failures."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = 'authentication_error'
    default_detail = 'Authentication is required.'


class AuthorisationError(APIException):
    """Base for all 403-class authorisation failures."""
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'authorisation_error'
    default_detail = 'You do not have permission to perform this action.'


# ─── 401 — Authentication failures ───────────────────────────────────────────

class NotAuthenticatedError(AuthenticationError):
    """
    No active session.  The user has not logged in, or the session
    cookie is absent / invalid.
    Raised by: TLPortalSessionAuthentication, AuthenticationMiddleware.
    """
    default_code   = 'not_authenticated'
    default_detail = 'Authentication credentials were not provided.'


class SessionExpiredError(AuthenticationError):
    """
    A session existed but has expired (Django session age exceeded or
    the session record was deleted server-side).
    Raised by: AuthenticationMiddleware.
    """
    default_code   = 'session_expired'
    default_detail = 'Your session has expired. Please log in again.'


class InvalidCredentialsError(AuthenticationError):
    """
    Email / password combination is incorrect.
    Raised by: LocalAuthBackend (surfaced through LoginView).
    Never exposed verbosely to prevent user-enumeration attacks.
    """
    default_code   = 'invalid_credentials'
    default_detail = 'Invalid credentials. Please check your email and password.'


class AccountInactiveError(AuthenticationError):
    """
    The user account exists but is_active == False.
    Raised by: LocalAuthBackend, TLPortalSessionAuthentication.
    """
    default_code   = 'account_inactive'
    default_detail = 'This account has been deactivated. Please contact the administrator.'


class InvalidSSOResponseError(AuthenticationError):
    """
    The Central Portal returned an invalid, expired or tampered
    identity assertion during the SSO handshake.
    Raised by: CentralSSOBackend, CentralPortalService.
    """
    default_code   = 'invalid_sso_response'
    default_detail = 'The SSO response from the Central Portal was invalid or expired.'


# ─── 403 — Authorisation failures ────────────────────────────────────────────

class ApplicationAccessDeniedError(AuthorisationError):
    """
    The authenticated user has no active UserApplicationAccess record
    for this application (e.g. TRADE_LICENSE).
    Raised by: ApplicationAccessPermission, AuthenticationMiddleware.
    """
    default_code   = 'application_access_denied'
    default_detail = 'You are not authorised to access the Trade Licence application.'


class PermissionDeniedError(AuthorisationError):
    """
    The user is authenticated and has application access, but lacks
    a specific named permission (e.g. 'application.approve').
    Raised by: HasPermission permission class.
    """
    default_code   = 'permission_denied'
    default_detail = 'You do not have the required permission for this action.'


class ULBAccessDeniedError(AuthorisationError):
    """
    The user attempted to access data belonging to a ULB they are
    not assigned to.  This enforces ULB data isolation.
    Raised by: ULBIsolationPermission, ULBIsolationMixin.
    """
    default_code   = 'ulb_access_denied'
    default_detail = 'You are not authorised to access data for this ULB.'


class RoleRequiredError(AuthorisationError):
    """
    The action requires one of a set of roles that the user does not hold.
    Raised by: HasRole permission class, @require_role decorator.
    """
    default_code   = 'role_required'
    default_detail = 'Your role does not permit this action.'
