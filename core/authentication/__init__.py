"""
core/authentication
====================
Central authentication and authorisation infrastructure for TL_portal.

Public API — import from here, not from submodules directly:

    from core.authentication import (
        # DRF auth class
        TLPortalSessionAuthentication,

        # DRF permission classes
        IsAuthenticatedUser,
        ApplicationAccessPermission,
        HasRole,
        HasPermission,
        ULBIsolationPermission,
        IsOfficer,
        IsAdminUser,

        # Decorators (for function-based / non-DRF views)
        login_required_api,
        require_role,
        require_permission,
        require_app_access,
        require_ulb_match,

        # Exceptions
        AuthenticationError,
        AuthorisationError,
        NotAuthenticatedError,
        SessionExpiredError,
        InvalidCredentialsError,
        AccountInactiveError,
        InvalidSSOResponseError,
        ApplicationAccessDeniedError,
        PermissionDeniedError,
        ULBAccessDeniedError,
        RoleRequiredError,

        # Central Portal service (SSO orchestration)
        CentralPortalService,
        get_central_portal_service,

        # DRF exception handler
        custom_exception_handler,
    )

Do NOT import from submodules (exceptions.py, permissions.py, etc.) directly
in business code.  Always import from core.authentication so that the
internal module layout can be refactored without breaking callers.
"""

from .authentication import TLPortalSessionAuthentication, custom_exception_handler
from .central_portal import CentralPortalService, get_central_portal_service
from .decorators import (
    login_required_api,
    require_app_access,
    require_permission,
    require_role,
    require_ulb_match,
)
from .exceptions import (
    AccountInactiveError,
    ApplicationAccessDeniedError,
    AuthenticationError,
    AuthorisationError,
    InvalidCredentialsError,
    InvalidSSOResponseError,
    NotAuthenticatedError,
    PermissionDeniedError,
    RoleRequiredError,
    SessionExpiredError,
    ULBAccessDeniedError,
)
from .permissions import (
    ApplicationAccessPermission,
    HasPermission,
    HasRole,
    IsAdminUser,
    IsAuthenticatedUser,
    IsOfficer,
    ULBIsolationPermission,
)

__all__ = [
    # Auth class
    'TLPortalSessionAuthentication',
    'custom_exception_handler',
    # Permissions
    'IsAuthenticatedUser',
    'ApplicationAccessPermission',
    'HasRole',
    'HasPermission',
    'ULBIsolationPermission',
    'IsOfficer',
    'IsAdminUser',
    # Decorators
    'login_required_api',
    'require_role',
    'require_permission',
    'require_app_access',
    'require_ulb_match',
    # Exceptions
    'AuthenticationError',
    'AuthorisationError',
    'NotAuthenticatedError',
    'SessionExpiredError',
    'InvalidCredentialsError',
    'AccountInactiveError',
    'InvalidSSOResponseError',
    'ApplicationAccessDeniedError',
    'PermissionDeniedError',
    'ULBAccessDeniedError',
    'RoleRequiredError',
    # Central Portal
    'CentralPortalService',
    'get_central_portal_service',
]
