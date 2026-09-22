"""
users/auth_backends.py
========================
Django authentication backends for TL_portal.

Two backends are defined here:
  1. LocalAuthBackend    — active, validates against local User table
  2. CentralSSOBackend   — stub; delegates to CentralPortalService when enabled

AUTHENTICATION_BACKENDS in settings.py controls which are active.
Adding or removing a backend here is the only change needed to switch
authentication providers for the entire application.

Design rule: business views and APIs only ever touch request.user.
They must never import or call anything from this file directly.
"""

import logging

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User   = get_user_model()


# ─── Shared base ──────────────────────────────────────────────────────────────

class _BaseAuthBackend:
    """Shared helpers used by both backends."""

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None

    def _log_login(self, user, method, status, request, notes=''):
        """Write an immutable UserLoginLog record. Never raises."""
        try:
            from users.models import UserLoginLog
            ip = self._get_client_ip(request) if request else None
            ua = request.META.get('HTTP_USER_AGENT', '') if request else ''
            UserLoginLog.objects.create(
                user=user if status == 'SUCCESS' else None,
                email_attempted=getattr(user, 'email', ''),
                method=method,
                status=status,
                ip_address=ip,
                user_agent=ua,
                notes=notes,
            )
        except Exception:
            logger.exception('_BaseAuthBackend: failed to write UserLoginLog')

    @staticmethod
    def _get_client_ip(request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


# ─── Backend 1: Local Authentication ─────────────────────────────────────────

class LocalAuthBackend(_BaseAuthBackend):
    """
    MODE 1 — Local login against the TL_portal User table.

    Accepts any of: email, username, or mobile as the login identifier.
    Password is validated with user.check_password().

    Called by django.contrib.auth.authenticate(request, username=..., password=...).
    Django's built-in LoginView passes the form field as `username`; this
    backend treats that value as an email first, then username, then mobile.
    """

    def authenticate(self, request, username=None, email=None, password=None, **kwargs):
        if password is None:
            return None

        login_id = email or username
        if not login_id:
            return None

        user = self._find_user(login_id)

        if user is None:
            logger.debug('LocalAuthBackend: no user for identifier=%s', login_id)
            self._log_login(
                user=None, method='LOCAL', status='FAILURE',
                request=request, notes=f'No user: {login_id}',
            )
            return None

        if not user.check_password(password):
            logger.debug('LocalAuthBackend: wrong password for %s', user.email)
            self._log_login(
                user=user, method='LOCAL', status='FAILURE',
                request=request, notes='Incorrect password',
            )
            return None

        if not user.is_active:
            logger.warning('LocalAuthBackend: inactive user %s', user.email)
            self._log_login(
                user=user, method='LOCAL', status='LOCKED',
                request=request, notes='Account inactive',
            )
            return None

        logger.info('LocalAuthBackend: login OK for %s', user.email)
        self._log_login(user=user, method='LOCAL', status='SUCCESS', request=request)
        return user

    @staticmethod
    def _find_user(login_id: str):
        """Try email → username → mobile. Returns User or None."""
        try:
            return User.objects.get(email__iexact=login_id)
        except User.DoesNotExist:
            pass
        try:
            return User.objects.get(username__iexact=login_id)
        except User.DoesNotExist:
            pass
        stripped = login_id.lstrip('+')
        if stripped.isdigit():
            try:
                return User.objects.get(mobile=login_id)
            except User.DoesNotExist:
                pass
        return None


# ─── Backend 2: Central Portal SSO ───────────────────────────────────────────

class CentralSSOBackend(_BaseAuthBackend):
    """
    MODE 2 — Central Portal / SSO authentication.

    This backend is activated by:
      1. Setting CENTRAL_PORTAL_ENABLED=True in .env
      2. Uncommenting 'users.auth_backends.CentralSSOBackend'
         in settings.AUTHENTICATION_BACKENDS

    It delegates ALL Central Portal communication to CentralPortalService
    (core/authentication/central_portal.py).  No CP-specific logic lives here.

    Two entry points:
      A. authenticate(request, sso_token=<assertion>)
         Used when the CP issues a signed one-time token passed directly
         to the TL_portal (non-OAuth flow).

      B. The OAuth callback flow uses handle_sso_callback() in
         users/views.py → CentralPortalService.handle_callback()
         and does NOT go through this authenticate() method.
         After handle_callback() returns a local user, the view calls
         django.contrib.auth.login(request, user) directly.

    In both cases the result is an identical Django session —
    subsequent requests are handled by TLPortalSessionAuthentication
    without knowing which auth path was used.
    """

    def authenticate(self, request, sso_token=None, **kwargs):
        """
        Validate a Central Portal assertion token and return the local user.
        Returns None (not raises) if CP is disabled or token is absent,
        so Django falls through to the next backend in the list.
        """
        from django.conf import settings
        if not getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            return None
        if not sso_token:
            return None

        try:
            from core.authentication.central_portal import get_central_portal_service
            service = get_central_portal_service()
            user    = service.validate_assertion(sso_token)
        except Exception as exc:
            logger.error('CentralSSOBackend.authenticate failed: %s', exc)
            self._log_login(
                user=None, method='SSO', status='FAILURE',
                request=request, notes=str(exc),
            )
            return None

        if not user or not user.is_active:
            self._log_login(
                user=user, method='SSO', status='LOCKED',
                request=request, notes='Account inactive after SSO',
            )
            return None

        logger.info('CentralSSOBackend: SSO login OK for %s', user.email)
        self._log_login(user=user, method='SSO', status='SUCCESS', request=request)
        return user
