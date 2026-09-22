"""
users/auth_backends.py
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

    def _log_login(self, user, method, status, request, login_id='', notes=''):
        """Write an immutable UserLoginLog record. Never raises."""
        try:
            from users.models import UserLoginLog
            ip = self._get_client_ip(request) if request else None
            ua = request.META.get('HTTP_USER_AGENT', '') if request else ''
            UserLoginLog.objects.create(
                user=user if status == 'SUCCESS' else None,
                username_attempted=login_id,
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
    Authenticates against the local User table using username + password.
    Called by django.contrib.auth.authenticate(request, username=..., password=...).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None

        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            logger.debug('LocalAuthBackend: no user for username=%s', username)
            self._log_login(
                user=None, method='LOCAL', status='FAILURE',
                request=request, login_id=username,
                notes=f'No user: {username}',
            )
            return None

        if not user.check_password(password):
            logger.debug('LocalAuthBackend: wrong password for %s', user.username)
            self._log_login(
                user=user, method='LOCAL', status='FAILURE',
                request=request, login_id=username,
                notes='Incorrect password',
            )
            return None

        if not user.is_active:
            logger.warning('LocalAuthBackend: inactive user %s', user.username)
            self._log_login(
                user=user, method='LOCAL', status='LOCKED',
                request=request, login_id=username,
                notes='Account inactive',
            )
            return None

        logger.info('LocalAuthBackend: login OK for %s', user.username)
        self._log_login(user=user, method='LOCAL', status='SUCCESS',
                        request=request, login_id=username)
        return user


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
                request=request, login_id='', notes=str(exc),
            )
            return None

        if not user or not user.is_active:
            self._log_login(
                user=user, method='SSO', status='LOCKED',
                request=request, login_id=getattr(user, 'username', ''),
                notes='Account inactive after SSO',
            )
            return None

        logger.info('CentralSSOBackend: SSO login OK for %s', user.email)
        self._log_login(user=user, method='SSO', status='SUCCESS',
                        request=request, login_id=getattr(user, 'username', ''))
        return user
