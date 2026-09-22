from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, Role, Permission, UserApplicationAccess, CentralIdentity, UserLoginLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering        = ['-date_joined']
    list_display    = ('email', 'get_full_name', 'role', 'ulb_code',
                       'is_active', 'is_verified', 'is_staff', 'date_joined')
    list_filter     = ('role', 'is_active', 'is_verified', 'is_staff', 'ulb_code')
    search_fields   = ('email', 'first_name', 'last_name', 'mobile', 'username', 'ulb_code')
    readonly_fields = ('date_joined', 'last_login', 'updated_at')

    fieldsets = (
        (None,                   {'fields': ('email', 'password')}),
        (_('Personal info'),     {'fields': ('first_name', 'last_name', 'mobile', 'username')}),
        (_('Role & Org'),        {'fields': ('role', 'ulb_code', 'department', 'zone', 'ward')}),
        (_('Permissions'),       {'fields': ('is_active', 'is_staff', 'is_superuser',
                                             'is_verified', 'groups', 'user_permissions')}),
        (_('Important dates'),   {'fields': ('date_joined', 'last_login', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'first_name', 'last_name', 'role',
                        'ulb_code', 'password1', 'password2'),
        }),
    )


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display  = ('code', 'module', 'description')
    list_filter   = ('module',)
    search_fields = ('code', 'description')
    ordering      = ('module', 'code')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'ulb_code', 'is_active')
    list_filter   = ('is_active', 'ulb_code')
    search_fields = ('name', 'code')
    filter_horizontal = ('permissions',)


@admin.register(UserApplicationAccess)
class UserApplicationAccessAdmin(admin.ModelAdmin):
    list_display  = ('user', 'application_code', 'is_active', 'granted_at', 'granted_by')
    list_filter   = ('application_code', 'is_active')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'granted_by')


@admin.register(CentralIdentity)
class CentralIdentityAdmin(admin.ModelAdmin):
    list_display  = ('user', 'provider', 'central_user_id', 'is_active', 'last_sso_login')
    list_filter   = ('provider', 'is_active')
    search_fields = ('user__email', 'central_user_id', 'central_username')
    raw_id_fields = ('user',)


@admin.register(UserLoginLog)
class UserLoginLogAdmin(admin.ModelAdmin):
    list_display  = ('email_attempted', 'method', 'status', 'ip_address', 'timestamp')
    list_filter   = ('method', 'status')
    search_fields = ('email_attempted', 'ip_address')
    readonly_fields = ('user', 'email_attempted', 'method', 'status',
                       'ip_address', 'user_agent', 'timestamp', 'notes')

    def has_delete_permission(self, request, obj=None):
        """Login logs are audit records — prevent deletion from admin."""
        return False

    def has_change_permission(self, request, obj=None):
        return False
