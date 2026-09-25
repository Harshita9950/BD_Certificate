from rest_framework.permissions import BasePermission

from users.models import Role


class WorkflowPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        permission_code = 'workflow.view'

        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            permission_code = 'workflow.manage'

        return Role.objects.filter(
            code=request.user.role,
            is_active=True,
            permissions__code=permission_code,
        ).exists()