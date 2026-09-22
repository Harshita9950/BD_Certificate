"""
core/authentication/permissions.py
=====================================
Reusable DRF permission classes for the TL_portal system.

Usage in settings.py (global default — already configured):
    REST_FRAMEWORK = {
        'DEFAULT_PERMISSION_CLASSES': [
            'core.authentication.permissions.IsAuthenticatedUser',
        ],
    }

Usage on individual views (exceptional cases only):
    class MyView(APIView):
        permission_classes = [HasRole('OFFICER', 'COMMISSIONER')]

Authorisation hierarchy enforced here:
  1. Is the user authenticated and active?          → IsAuthenticatedUser
  2. Does the user have Trade Licence app access?   → ApplicationAccessPermission
  3. Does the user hold the required role(s)?       → HasRole
  4. Does the user hold a specific permission code? → HasPermission
  5. Does the request concern the user's own ULB?   → ULBIsolationPermission

All permission failures raise typed exceptions from exceptions.py so that
error handling is centralised and consistent across the entire application.
"""

import logging

from rest_framework.permissions import BasePermission

from .exceptions import (
    AccountInactiveError,
    ApplicationAccessDeniedError,
    NotAuthenticatedError,
    PermissionDeniedError,
    RoleRequiredError,
    ULBAccessDeniedError,
)

logger = logging.getLogger(__name__)

# Application code this portal serves
_APP_CODE = 'TRADE_LICENSE'


# ─── 1. Core authentication check ────────────────────────────────────────────

class IsAuthenticatedUser(BasePermission):
    """
    Replacement for DRF's IsAuthenticated that raises typed exceptions
    from our central exception hierarchy instead of generic API exceptions.

    This is set as the global DEFAULT_PERMISSION_CLASS in settings.py.
    Individual endpoints that should be public must explicitly set:
        permission_classes = [AllowAny]
    """

    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous:
            raise NotAuthenticatedError()
        if not request.user.is_active:
            raise AccountInactiveError()
        return True


# ─── 2. Application-level access ─────────────────────────────────────────────

class ApplicationAccessPermission(BasePermission):
    """
    Verifies the user has an active UserApplicationAccess record for
    TRADE_LICENSE.

    When CENTRAL_PORTAL_ENABLED=False, all authenticated users with any
    role are treated as having application access (local mode).

    When CENTRAL_PORTAL_ENABLED=True, access must be explicitly granted
    via a UserApplicationAccess record — typically created during the
    first SSO login or by an administrator.

    Use alongside IsAuthenticatedUser:
        permission_classes = [IsAuthenticatedUser, ApplicationAccessPermission]
    """

    def has_permission(self, request, view):
        from django.conf import settings

        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()

        # In local mode, skip the application-access check
        if not getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            return True

        if not user.has_application_access(_APP_CODE):
            logger.warning(
                'ApplicationAccessPermission: user %s denied access to %s',
                user.email, _APP_CODE,
            )
            raise ApplicationAccessDeniedError()

        return True


# ─── 3. Role-based permission ─────────────────────────────────────────────────

class HasRole(BasePermission):
    """
    Allows access only to users whose role is in the given set.

    Usage (factory pattern — returns a configured permission class):
        permission_classes = [HasRole.of('OFFICER', 'COMMISSIONER')]

    Or as a direct class with roles set on subclass:
        class OfficerOnly(HasRole):
            allowed_roles = ['OFFICER', 'COMMISSIONER']

    Never check role names directly in view/business logic.
    Always use this class so that role changes propagate everywhere.
    """

    allowed_roles: list[str] = []

    @classmethod
    def of(cls, *roles: str) -> type:
        """
        Factory: create an anonymous subclass with the given roles.
        Usage: permission_classes = [HasRole.of('OFFICER', 'DA')]
        """
        return type(
            f'HasRole_{"_".join(roles)}',
            (cls,),
            {'allowed_roles': list(roles)},
        )

    def has_permission(self, request, view):
        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()
        if not self.allowed_roles:
            return True  # No restriction configured — allow
        if user.role not in self.allowed_roles:
            logger.warning(
                'HasRole: user %s (role=%s) denied; requires one of %s',
                user.email, user.role, self.allowed_roles,
            )
            raise RoleRequiredError(
                detail=f'This action requires one of the following roles: '
                       f'{", ".join(self.allowed_roles)}.'
            )
        return True


# ─── 4. Named permission code ─────────────────────────────────────────────────

class HasPermission(BasePermission):
    """
    Checks that the user's assigned Role includes a specific Permission code.
    Permission codes are defined in users/models.py Permission model and
    stored in the database — never hard-coded.

    Usage (factory pattern):
        permission_classes = [HasPermission.of('application.approve')]

    Permission codes follow the pattern:  <module>.<action>
    Examples:
        application.view       application.approve    application.reject
        inspection.assign      fee.calculate          license.generate
        reports.view
    """

    required_permission: str = ''

    @classmethod
    def of(cls, permission_code: str) -> type:
        """
        Factory: create an anonymous subclass checking the given permission code.
        Usage: permission_classes = [HasPermission.of('license.generate')]
        """
        return type(
            f'HasPermission_{permission_code.replace(".", "_")}',
            (cls,),
            {'required_permission': permission_code},
        )

    def has_permission(self, request, view):
        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()
        if not self.required_permission:
            return True

        if not self._user_has_permission(user, self.required_permission):
            logger.warning(
                'HasPermission: user %s (role=%s) denied; requires permission %s',
                user.email, user.role, self.required_permission,
            )
            raise PermissionDeniedError(
                detail=f'Required permission: {self.required_permission}'
            )
        return True

    @staticmethod
    def _user_has_permission(user, permission_code: str) -> bool:
        """
        Look up whether the user's role includes the named permission code.
        Admins bypass all permission checks.
        """
        from users.models import UserRole
        if user.role == UserRole.ADMIN or user.is_superuser:
            return True
        try:
            from users.models import Role
            role_obj = Role.objects.filter(
                code=user.role, is_active=True
            ).prefetch_related('permissions').first()
            if role_obj is None:
                return False
            return role_obj.permissions.filter(code=permission_code).exists()
        except Exception:
            logger.exception(
                'HasPermission: error checking permission %s for user %s',
                permission_code, user.email,
            )
            return False


# ─── 5. ULB isolation ────────────────────────────────────────────────────────

class ULBIsolationPermission(BasePermission):
    """
    Enforces ULB data isolation at the permission level.

    A user must not access another ULB's data by manipulating a URL
    parameter, query string or request body.

    This permission checks the `ulb_code` on the object (if provided to
    has_object_permission) against the user's assigned `ulb_code`.

    System Admins bypass ULB isolation (they manage all ULBs).

    Usage on ViewSets that handle object-level access:
        permission_classes = [IsAuthenticatedUser, ULBIsolationPermission]

    In the view's get_queryset(), also filter by request.user.ulb_code:
        def get_queryset(self):
            return Application.objects.filter(ulb_code=self.request.user.ulb_code)
    """

    def has_permission(self, request, view):
        # List-level: queryset filtering in get_queryset() handles isolation
        return True

    def has_object_permission(self, request, view, obj):
        from users.models import UserRole
        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()

        # Admins can access any ULB
        if user.role == UserRole.ADMIN or user.is_superuser:
            return True

        # Get the ULB code from the object (support different field names)
        obj_ulb = (
            getattr(obj, 'ulb_code', None)
            or getattr(obj, 'municipality_code', None)
            or getattr(obj, 'ulb', None)
        )

        if obj_ulb and user.ulb_code and obj_ulb != user.ulb_code:
            logger.warning(
                'ULBIsolationPermission: user %s (ulb=%s) attempted access '
                'to object ulb=%s',
                user.email, user.ulb_code, obj_ulb,
            )
            raise ULBAccessDeniedError()

        return True


# ─── Convenience composites ───────────────────────────────────────────────────

class IsOfficer(BasePermission):
    """
    Shorthand: allows access to any municipal officer role.
    Equivalent to HasRole.of('DA','HEALTH_OFFICER','CHO','ACCOUNTANT',
                              'RI','ZONE_OFFICER','COMMISSIONER','ADMIN')
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()
        if not user.is_officer and not user.is_system_admin:
            raise RoleRequiredError(
                detail='This action is restricted to municipal officers.'
            )
        return True


class IsAdminUser(BasePermission):
    """Allows access only to ADMIN role users."""

    def has_permission(self, request, view):
        user = request.user
        if not user or user.is_anonymous:
            raise NotAuthenticatedError()
        if not user.is_system_admin:
            raise RoleRequiredError(
                detail='This action is restricted to system administrators.'
            )
        return True
