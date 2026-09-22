"""
users/models.py
===============
Custom User model and supporting authorization models for the
Municipal Trade Licence Management System.

Design principles
-----------------
1. Email is the primary login credential (not username).
   Mobile/username are stored as optional secondary identifiers.

2. Role → Permission architecture.
   Hard-coded "user type" checks are avoided. Roles are database records.
   Fine-grained permissions are strings (e.g. 'application.approve')
   assigned to roles and therefore to users.

3. Central Portal / SSO readiness.
   CentralIdentity stores an external identity reference so that the
   same physical person authenticating via the Central Portal maps to
   their existing local User without creating a duplicate account.

4. Application-level authorization.
   UserApplicationAccess records which applications (TRADE_LICENSE,
   UD_TAX, etc.) a user is authorized to access, enabling future
   multi-application portal support.

5. Soft-delete only.
   Users are never hard-deleted. Use is_active = False to deactivate.

6. ULB / Zone / Ward context.
   Officers are assigned to a ULB (Urban Local Body), zone, and ward.
   This drives workflow routing and jurisdiction.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─── Choices ──────────────────────────────────────────────────────────────────

class UserRole(models.TextChoices):
    """
    Predefined role names used for quick role checks in code.
    Actual permission sets are assigned to Role instances in the database,
    not hard-coded here — this enum is only for bootstrap/reference.
    """
    CITIZEN        = 'CITIZEN',        _('Citizen / Applicant')
    DA             = 'DA',             _('Dealing Assistant')
    HEALTH_OFFICER = 'HEALTH_OFFICER', _('Health Officer')
    CHO            = 'CHO',            _('Chief Health Officer')
    ACCOUNTANT     = 'ACCOUNTANT',     _('Accountant')
    RI             = 'RI',             _('Revenue Inspector')
    ZONE_OFFICER   = 'ZONE_OFFICER',   _('Zone Officer')
    OFFICER        = 'OFFICER',        _('Licensing Officer')
    COMMISSIONER   = 'COMMISSIONER',   _('Municipal Commissioner')
    AUDITOR        = 'AUDITOR',        _('Auditor')
    ADMIN          = 'ADMIN',          _('System Administrator')


class ApplicationCode(models.TextChoices):
    """
    Known application codes for application-level authorization.
    The Central Portal uses these codes to indicate which application
    a user is being routed to.
    """
    TRADE_LICENSE     = 'TRADE_LICENSE',     _('Trade Licence')
    UD_TAX            = 'UD_TAX',            _('UD Tax')
    ADVERTISEMENT_TAX = 'ADVERTISEMENT_TAX', _('Advertisement Tax')
    HRMS              = 'HRMS',              _('HRMS')


# ─── User Manager ─────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    """Email-based user manager."""

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_('An email address is required.'))
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', UserRole.CITIZEN)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        if not extra_fields['is_staff']:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if not extra_fields['is_superuser']:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self._create_user(email, password, **extra_fields)


# ─── Core User Model ──────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    """
    Central user record for the TL_portal system.

    All actors — citizens, officers, inspectors, commissioners, admins —
    share this single model. The `role` field drives workflow routing;
    the `Role` → `Permission` system enforces fine-grained access control.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    email      = models.EmailField(_('email address'), unique=True, db_index=True)
    username   = models.CharField(
        _('username'), max_length=150, unique=True, blank=True, null=True,
        help_text=_('Optional. Used as an alternative login identifier for officers.'),
    )
    mobile     = models.CharField(_('mobile number'), max_length=15, blank=True, default='')
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name  = models.CharField(_('last name'),  max_length=150, blank=True)

    # ── Role ──────────────────────────────────────────────────────────────────
    role = models.CharField(
        _('role'), max_length=30,
        choices=UserRole.choices,
        default=UserRole.CITIZEN,
        db_index=True,
    )

    # ── Organisational context ────────────────────────────────────────────────
    # ulb_code kept for backwards compatibility and as the ULB isolation key
    # used throughout the auth layer. The FK fields are the authoritative links.
    ulb_code   = models.CharField(
        _('ULB code'), max_length=50, blank=True, default='',
        db_index=True,
    )
    department = models.CharField(_('department'), max_length=100, blank=True, default='')
    zone       = models.CharField(_('zone'), max_length=100, blank=True, default='')
    ward       = models.CharField(_('ward'), max_length=100, blank=True, default='')

    # FK links to geography master — nullable; set when geography records exist
    ulb_fk  = models.ForeignKey(
        'geography.ULB', on_delete=models.PROTECT,
        null=True, blank=True, related_name='users',
        verbose_name=_('ULB'),
    )
    zone_fk = models.ForeignKey(
        'geography.Zone', on_delete=models.PROTECT,
        null=True, blank=True, related_name='users',
        verbose_name=_('zone'),
    )
    ward_fk = models.ForeignKey(
        'geography.Ward', on_delete=models.PROTECT,
        null=True, blank=True, related_name='users',
        verbose_name=_('ward'),
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_active   = models.BooleanField(_('active'), default=True,
                                      help_text=_('Deactivate instead of deleting.'))
    is_staff    = models.BooleanField(_('staff status'), default=False)
    is_verified = models.BooleanField(
        _('email verified'), default=False,
        help_text=_('User has confirmed their email address.'),
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    updated_at  = models.DateTimeField(_('updated at'),  auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name        = _('User')
        verbose_name_plural = _('Users')
        ordering            = ['-date_joined']
        indexes = [
            models.Index(fields=['email', 'role']),
            models.Index(fields=['ulb_code', 'role']),
        ]

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}> [{self.role}]'

    def get_full_name(self):
        name = f'{self.first_name} {self.last_name}'.strip()
        return name or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    # ── Convenience role checks ───────────────────────────────────────────────
    @property
    def is_citizen(self):
        return self.role == UserRole.CITIZEN

    @property
    def is_officer(self):
        """True for any municipal officer role."""
        return self.role in (
            UserRole.DA, UserRole.HEALTH_OFFICER, UserRole.CHO,
            UserRole.ACCOUNTANT, UserRole.RI, UserRole.ZONE_OFFICER,
            UserRole.OFFICER, UserRole.COMMISSIONER,
        )

    @property
    def is_system_admin(self):
        return self.role == UserRole.ADMIN

    def has_application_access(self, app_code):
        """Check if this user is authorized for a given application code."""
        return self.application_accesses.filter(
            application_code=app_code, is_active=True
        ).exists()


# ─── Role & Permission ────────────────────────────────────────────────────────

class Permission(models.Model):
    """
    A named permission string (e.g. 'application.approve').
    Permissions are assigned to Roles, not directly to Users.

    Predefined permission codes (for reference — stored in DB, not hard-coded):
      application.view         application.create        application.submit
      application.scrutiny     application.raise_deficiency
      application.forward      application.approve       application.reject
      inspection.view          inspection.assign         inspection.complete
      fee.view                 fee.calculate             fee.approve
      license.view             license.generate          license.renew
      license.modify           license.transfer          license.suspend
      license.cancel           reports.view
    """
    code        = models.CharField(_('code'), max_length=100, unique=True, db_index=True)
    description = models.CharField(_('description'), max_length=255, blank=True)
    module      = models.CharField(
        _('module'), max_length=50, blank=True,
        help_text=_('Logical grouping, e.g. application / inspection / fee / license.'),
    )

    class Meta:
        verbose_name        = _('Permission')
        verbose_name_plural = _('Permissions')
        ordering            = ['module', 'code']

    def __str__(self):
        return self.code


class Role(models.Model):
    """
    A database-driven role that owns a set of permissions.
    Users are assigned one role; permissions flow from there.
    This keeps authorization flexible — add/remove permissions
    from a role without touching code.
    """
    name        = models.CharField(_('name'), max_length=100, unique=True)
    code        = models.CharField(
        _('code'), max_length=30,
        choices=UserRole.choices,
        unique=True, db_index=True,
    )
    description = models.TextField(_('description'), blank=True)
    permissions = models.ManyToManyField(
        Permission, blank=True,
        related_name='roles',
        verbose_name=_('permissions'),
    )
    ulb_code    = models.CharField(
        _('ULB code'), max_length=50, blank=True, default='',
        help_text=_('Leave blank for system-wide roles.'),
    )
    is_active   = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name        = _('Role')
        verbose_name_plural = _('Roles')
        ordering            = ['name']

    def __str__(self):
        return self.name


# ─── Application-Level Authorization ─────────────────────────────────────────

class UserApplicationAccess(models.Model):
    """
    Records which application(s) a user is authorized to access.

    This is the hook for Central Portal multi-application routing:
    when the Central Portal hands off a user, the system checks this
    table to confirm the user may enter the Trade Licence application.

    One record per user per application.
    """
    user             = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='application_accesses',
        verbose_name=_('user'),
    )
    application_code = models.CharField(
        _('application code'), max_length=50,
        choices=ApplicationCode.choices,
        db_index=True,
    )
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='access_grants',
        verbose_name=_('granted by'),
    )
    granted_at = models.DateTimeField(_('granted at'), default=timezone.now)
    is_active  = models.BooleanField(_('active'), default=True)
    notes      = models.TextField(_('notes'), blank=True)

    class Meta:
        verbose_name        = _('User Application Access')
        verbose_name_plural = _('User Application Accesses')
        unique_together     = ('user', 'application_code')
        ordering            = ['user', 'application_code']

    def __str__(self):
        status = 'ACTIVE' if self.is_active else 'REVOKED'
        return f'{self.user.email} → {self.application_code} [{status}]'


# ─── Central Identity (SSO readiness) ────────────────────────────────────────

class CentralIdentity(models.Model):
    """
    Maps a local User to an external identity from the Central Portal.

    When the Central Portal authenticates a user and hands off a
    trusted identity (via SSO callback, signed assertion, etc.),
    this record is used to find the corresponding local User without
    creating a duplicate account.

    One User can have at most one CentralIdentity record.
    The `provider` field allows for multiple Central Portal types
    in the future (e.g. State SSO, National SSO).
    """
    user             = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='central_identity',
        verbose_name=_('local user'),
    )
    provider         = models.CharField(
        _('provider'), max_length=100, default='CENTRAL_PORTAL',
        help_text=_('Identifies the SSO provider. E.g. CENTRAL_PORTAL, STATE_SSO.'),
    )
    central_user_id  = models.CharField(
        _('central user ID'), max_length=255, db_index=True,
        help_text=_('The unique user identifier from the Central Portal.'),
    )
    central_username = models.CharField(
        _('central username'), max_length=255, blank=True,
        help_text=_('Username as known to the Central Portal (for display only).'),
    )
    extra_data       = models.JSONField(
        _('extra data'), default=dict, blank=True,
        help_text=_('Additional claims/attributes received from the Central Portal.'),
    )
    linked_at        = models.DateTimeField(_('linked at'), default=timezone.now)
    last_sso_login   = models.DateTimeField(_('last SSO login'), null=True, blank=True)
    is_active        = models.BooleanField(_('active'), default=True)

    class Meta:
        verbose_name        = _('Central Identity')
        verbose_name_plural = _('Central Identities')
        unique_together     = ('provider', 'central_user_id')
        ordering            = ['user']

    def __str__(self):
        return f'{self.user.email} ↔ {self.provider}:{self.central_user_id}'


# ─── Audit / Login Log ────────────────────────────────────────────────────────

class UserLoginLog(models.Model):
    """
    Immutable log of each login event.
    Used for security auditing and session traceability.
    Records must never be deleted.
    """

    class LoginMethod(models.TextChoices):
        LOCAL  = 'LOCAL',  _('Local Login')
        SSO    = 'SSO',    _('Central Portal SSO')

    class LoginStatus(models.TextChoices):
        SUCCESS = 'SUCCESS', _('Success')
        FAILURE = 'FAILURE', _('Failure')
        LOCKED  = 'LOCKED',  _('Account Locked')

    user        = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='login_logs',
        verbose_name=_('user'),
        help_text=_('Null if the login attempt could not be associated with a user.'),
    )
    email_attempted = models.EmailField(_('email attempted'), blank=True)
    method      = models.CharField(_('method'), max_length=10, choices=LoginMethod.choices)
    status      = models.CharField(_('status'), max_length=10, choices=LoginStatus.choices)
    ip_address  = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    user_agent  = models.TextField(_('user agent'), blank=True)
    timestamp   = models.DateTimeField(_('timestamp'), default=timezone.now, db_index=True)
    notes       = models.TextField(_('notes'), blank=True)

    class Meta:
        verbose_name        = _('User Login Log')
        verbose_name_plural = _('User Login Logs')
        ordering            = ['-timestamp']
        # Prevent accidental deletion via Django admin bulk-delete
        default_permissions = ('view',)

    def __str__(self):
        return f'[{self.status}] {self.email_attempted} via {self.method} @ {self.timestamp}'


class UserOrganisationalScope(models.Model):
    """
    Explicit organisational scope assignment for a user.

    A user may be assigned to multiple ULBs, zones, or wards — for example,
    a zone officer covering two zones, or an auditor with state-wide access.
    This model records each explicit scope grant.

    The scope_level field determines what the ulb/zone/ward FKs mean:
      ULB  → user operates at the full ULB level; zone and ward are null
      ZONE → user operates within a specific zone; ward is null
      WARD → user operates within a specific ward

    Business-data filtering queries should join through this model rather
    than relying solely on User.ulb_fk.
    """

    class ScopeLevel(models.TextChoices):
        ULB  = 'ULB',  _('ULB')
        ZONE = 'ZONE', _('Zone')
        WARD = 'WARD', _('Ward')

    user        = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='org_scopes'
    )
    scope_level = models.CharField(max_length=4, choices=ScopeLevel.choices, db_index=True)
    ulb         = models.ForeignKey(
        'geography.ULB', on_delete=models.PROTECT, related_name='user_scopes'
    )
    zone        = models.ForeignKey(
        'geography.Zone', on_delete=models.PROTECT,
        null=True, blank=True, related_name='user_scopes'
    )
    ward        = models.ForeignKey(
        'geography.Ward', on_delete=models.PROTECT,
        null=True, blank=True, related_name='user_scopes'
    )
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _('User Organisational Scope')
        verbose_name_plural = _('User Organisational Scopes')
        indexes = [
            models.Index(fields=['user', 'scope_level', 'is_active']),
            models.Index(fields=['ulb', 'is_active']),
        ]

    def __str__(self):
        target = self.ward or self.zone or self.ulb
        return f'{self.user.email} → {self.scope_level}: {target}'
