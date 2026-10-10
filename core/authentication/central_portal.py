"""
core/authentication/central_portal.py
=========================================
Central Portal Service — orchestration layer.

This service sits between the Django authentication system and the raw
HTTP adapter (client.py).  It owns the business logic for:

  1. Initiating the SSO login flow (get_authorization_url)
  2. Handling the SSO callback (exchange code → identity → local user)
  3. Mapping a Central Portal identity to a local User
  4. Verifying application-level access
  5. Coordinating logout

Architecture position
---------------------
  CentralSSOBackend (users/auth_backends.py)
      ↓  delegates to
  CentralPortalService  ← THIS FILE
      ↓  delegates HTTP to
  CentralPortalClient (client.py)

No business module, view, or model may import from client.py directly.
They must go through CentralPortalService or the DRF auth class.

Current state
-------------
The service is fully structured but all methods that require a live
Central Portal are stubs returning descriptive errors.  The local auth
path works completely without any of this.

Activation steps (when CP is ready)
-------------------------------------
1. Set CENTRAL_PORTAL_ENABLED=True in .env
2. Fill CENTRAL_PORTAL_URL, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
3. Implement the TODO sections in client.py
4. Uncomment CentralSSOBackend in settings.AUTHENTICATION_BACKENDS
5. Nothing else in the codebase changes
"""

import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from .client import CentralPortalClient, CentralPortalIdentity
from .exceptions import (
    ApplicationAccessDeniedError,
    InvalidSSOResponseError,
)

logger = logging.getLogger(__name__)


class CentralPortalService:
    """
    Orchestrates all interactions with the Central Portal.
    Instantiated once per request in CentralSSOBackend.
    """

    def __init__(self):
        self._client   = CentralPortalClient()
        self._app_code = getattr(settings, 'CENTRAL_PORTAL_APPLICATION_CODE', 'BIRTH_DEATH')
        self._enabled  = getattr(settings, 'CENTRAL_PORTAL_ENABLED', False)

    # ── 1. Initiate SSO flow ──────────────────────────────────────────────────

    def get_authorization_url(self, state: str = '') -> str:
        """
        Return the URL the browser should be redirected to in order to
        begin the Central Portal authentication flow.

        Called by: SSOInitiateView (users/views.py — future)
        """
        if not self._enabled:
            raise RuntimeError(
                'Central Portal SSO is not enabled. '
                'Set CENTRAL_PORTAL_ENABLED=True in .env to use SSO.'
            )
        return self._client.get_authorization_url(state=state)

    # ── 2. Handle callback ────────────────────────────────────────────────────

    def handle_callback(self, code: str, state: str = '') -> 'User':
        """
        Handle the SSO callback from the Central Portal.

        Flow:
          code + state received at /api/auth/sso/callback/
              ↓
          exchange_code() → tokens
              ↓
          get_user_info() → CentralPortalIdentity
              ↓
          validate_application_access()
              ↓
          find_or_create_local_user()
              ↓
          return local User (Django creates session in the view)

        Returns the local User instance ready for login().
        Raises InvalidSSOResponseError on any failure.
        """
        if not self._enabled:
            raise InvalidSSOResponseError(
                detail='Central Portal SSO is not enabled.'
            )

        try:
            token_response = self._client.exchange_code(code=code, state=state)
        except NotImplementedError:
            raise InvalidSSOResponseError(
                detail='Central Portal integration is not yet implemented.'
            )
        except Exception as exc:
            logger.error('CentralPortalService.handle_callback: exchange_code failed: %s', exc)
            raise InvalidSSOResponseError(
                detail='Failed to exchange authorisation code with Central Portal.'
            )

        try:
            identity = self._client.get_user_info(token_response.access_token)
        except NotImplementedError:
            raise InvalidSSOResponseError(
                detail='Central Portal user info endpoint is not yet implemented.'
            )
        except Exception as exc:
            logger.error('CentralPortalService.handle_callback: get_user_info failed: %s', exc)
            raise InvalidSSOResponseError(
                detail='Failed to retrieve user identity from Central Portal.'
            )

        self._validate_application_access(identity)
        return self._find_or_create_local_user(identity, token_response.access_token)

    # ── 3. Validate application access ───────────────────────────────────────

    def _validate_application_access(self, identity: CentralPortalIdentity) -> None:
        """
        Verify the CP identity includes access to this application.
        Raises ApplicationAccessDeniedError if not.
        """
        if self._app_code not in identity.application_codes:
            logger.warning(
                'CentralPortalService: identity %s does not include %s access. '
                'Granted codes: %s',
                identity.central_user_id, self._app_code, identity.application_codes,
            )
            raise ApplicationAccessDeniedError()

    # ── 4. Find or create local user ──────────────────────────────────────────

    def _find_or_create_local_user(
        self,
        identity: CentralPortalIdentity,
        access_token: str = '',
    ) -> 'User':
        """
        Map the Central Portal identity to a local User record.

        Strategy:
          a) Look up CentralIdentity by (provider, central_user_id) → existing user
          b) Look up User by email → link their CentralIdentity
          c) Create a new User with no password (SSO users don't need one)

        This ensures one physical person has exactly one local User record
        regardless of how many times they log in via SSO.
        """
        from users.models import CentralIdentity, User, UserApplicationAccess, UserRole

        # a) Existing SSO link
        try:
            ci = CentralIdentity.objects.select_related('user').get(
                provider=identity.provider,
                central_user_id=identity.central_user_id,
                is_active=True,
            )
            user = ci.user
            self._refresh_central_identity(ci, identity, access_token)
            logger.info(
                'CentralPortalService: existing SSO user %s logged in', user.email
            )
        except CentralIdentity.DoesNotExist:
            # b) Match by email and link
            try:
                user = User.objects.get(email__iexact=identity.email)
                logger.info(
                    'CentralPortalService: linking existing user %s to CP identity',
                    user.email,
                )
            except User.DoesNotExist:
                # c) Create new user
                user = User.objects.create_user(
                    email=identity.email,
                    password=None,         # No local password for SSO users
                    first_name=identity.first_name,
                    last_name=identity.last_name,
                    mobile=identity.mobile,
                    ulb_code=identity.ulb_code,
                    department=identity.department,
                    role=identity.role_code or UserRole.CITIZEN,
                    is_verified=True,      # CP has already verified the identity
                )
                logger.info(
                    'CentralPortalService: created new user %s from CP identity',
                    user.email,
                )

            # Create CentralIdentity link
            CentralIdentity.objects.create(
                user=user,
                provider=identity.provider,
                central_user_id=identity.central_user_id,
                central_username=identity.email,
                extra_data=identity.extra_data,
            )

        # Ensure UserApplicationAccess exists for this application
        UserApplicationAccess.objects.get_or_create(
            user=user,
            application_code=self._app_code,
            defaults={'is_active': True},
        )

        # Update last SSO login timestamp
        if hasattr(user, 'central_identity'):
            ci = user.central_identity
            ci.last_sso_login = timezone.now()
            ci.save(update_fields=['last_sso_login'])

        return user

    @staticmethod
    def _refresh_central_identity(ci, identity: CentralPortalIdentity, access_token: str):
        """Keep the CentralIdentity record fresh after each SSO login."""
        ci.extra_data      = identity.extra_data
        ci.last_sso_login  = timezone.now()
        ci.save(update_fields=['extra_data', 'last_sso_login'])

    # ── 5. Logout ─────────────────────────────────────────────────────────────

    def get_logout_url(self, access_token: str = '', id_token: str = '') -> Optional[str]:
        """
        Return the Central Portal logout URL if propagated logout is configured.
        Returns None if CENTRAL_PORTAL_PROPAGATE_LOGOUT=False (default).
        Called by: LogoutView (users/views.py)
        """
        if not self._enabled:
            return None
        try:
            return self._client.logout(
                access_token=access_token,
                id_token=id_token,
            )
        except NotImplementedError:
            return None
        except Exception as exc:
            logger.warning('CentralPortalService.get_logout_url failed: %s', exc)
            return None

    # ── 6. Validate standalone assertion ─────────────────────────────────────

    def validate_assertion(self, assertion_token: str) -> 'User':
        """
        Validate a one-time signed assertion from the Central Portal
        (non-OAuth SSO mechanism) and return the local user.
        Used by CentralSSOBackend.authenticate() when the CP passes
        a signed token directly rather than an OAuth code.
        """
        try:
            identity = self._client.validate_assertion(assertion_token)
        except NotImplementedError:
            raise InvalidSSOResponseError(
                detail='Central Portal assertion validation is not yet implemented.'
            )
        except Exception as exc:
            logger.error('CentralPortalService.validate_assertion failed: %s', exc)
            raise InvalidSSOResponseError(
                detail='Failed to validate the Central Portal assertion.'
            )

        self._validate_application_access(identity)
        return self._find_or_create_local_user(identity)


# ─── Module-level singleton (lazy) ───────────────────────────────────────────

_service_instance: Optional[CentralPortalService] = None


def get_central_portal_service() -> CentralPortalService:
    """
    Return the module-level CentralPortalService instance.
    Use this instead of instantiating CentralPortalService directly.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = CentralPortalService()
    return _service_instance
