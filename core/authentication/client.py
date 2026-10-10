"""
core/authentication/client.py
================================
Central Portal HTTP adapter.

This is the ONLY place in the entire codebase that communicates with
the Central Portal's external API.  No other module may make direct
HTTP calls to the Central Portal.

Current state: STUB — no real HTTP calls are made.
All methods raise NotImplementedError until the Central Portal
integration contract is finalised and credentials are provided.

When the Central Portal is ready:
  1. Set CENTRAL_PORTAL_ENABLED=True in .env
  2. Set all CENTRAL_PORTAL_* env vars
  3. Install `httpx` or `requests` (add to requirements.txt)
  4. Implement the methods marked TODO below
  5. No other file in the codebase needs to change

Supported future mechanisms (implement whichever the CP uses):
  A. OAuth 2.0 Authorization Code Flow
  B. OIDC (OpenID Connect)
  C. SAML 2.0 Assertion
  D. Custom signed token / one-time code exchange
  E. Shared session infrastructure
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Data containers ──────────────────────────────────────────────────────────

@dataclass
class CentralPortalIdentity:
    """
    Normalised identity data returned by the Central Portal.
    Regardless of the SSO mechanism used, the adapter must populate
    this dataclass so that the rest of the system has a stable contract.
    """
    central_user_id:  str
    email:            str
    first_name:       str                 = ''
    last_name:        str                 = ''
    mobile:           str                 = ''
    ulb_code:         str                 = ''
    department:       str                 = ''
    role_code:        str                 = ''
    application_codes: list[str]          = field(default_factory=list)
    extra_data:       dict                = field(default_factory=dict)
    provider:         str                 = 'CENTRAL_PORTAL'


@dataclass
class TokenResponse:
    """Normalised token response from the Central Portal (OAuth/OIDC)."""
    access_token:  str
    token_type:    str   = 'Bearer'
    expires_in:    int   = 3600
    refresh_token: str   = ''
    id_token:      str   = ''
    scope:         str   = ''


# ─── Central Portal HTTP Client ───────────────────────────────────────────────

class CentralPortalClient:
    """
    HTTP adapter for all Central Portal communication.

    Configuration is read from settings (sourced from .env):
        CENTRAL_PORTAL_URL
        CENTRAL_PORTAL_CLIENT_ID
        CENTRAL_PORTAL_CLIENT_SECRET
        CENTRAL_PORTAL_REDIRECT_URI
        CENTRAL_PORTAL_APPLICATION_CODE

    Do not instantiate directly outside of CentralPortalService.
    """

    def __init__(self):
        self._base_url      = getattr(settings, 'CENTRAL_PORTAL_URL', '')
        self._client_id     = getattr(settings, 'CENTRAL_PORTAL_CLIENT_ID', '')
        self._client_secret = getattr(settings, 'CENTRAL_PORTAL_CLIENT_SECRET', '')
        self._redirect_uri  = getattr(settings, 'CENTRAL_PORTAL_REDIRECT_URI', '')
        self._app_code      = getattr(settings, 'CENTRAL_PORTAL_APPLICATION_CODE',
                                      'BIRTH_DEATH')

    # ── Authorization URL ─────────────────────────────────────────────────────

    def get_authorization_url(self, state: str = '') -> str:
        """
        Build and return the Central Portal's authorization / login URL.
        The browser is redirected here to begin the SSO flow.

        For OAuth 2.0:
            {base_url}/oauth/authorize?
                client_id=...&redirect_uri=...&response_type=code&state=...
                &scope=openid profile email
                &application_code={app_code}

        TODO: Implement once CP URL structure is confirmed.
        """
        # TODO: build real URL
        raise NotImplementedError(
            'CentralPortalClient.get_authorization_url() is not yet implemented. '
            'Set CENTRAL_PORTAL_ENABLED=False to use local authentication.'
        )

    # ── Code Exchange ─────────────────────────────────────────────────────────

    def exchange_code(self, code: str, state: str = '') -> TokenResponse:
        """
        Exchange the authorization code for tokens.
        Called from the SSO callback view after the CP redirects back.

        POST {base_url}/oauth/token
            grant_type=authorization_code
            code={code}
            redirect_uri={redirect_uri}
            client_id={client_id}
            client_secret={client_secret}

        TODO: Implement with httpx or requests once CP endpoint is known.
        """
        raise NotImplementedError(
            'CentralPortalClient.exchange_code() is not yet implemented.'
        )

    # ── User Info ─────────────────────────────────────────────────────────────

    def get_user_info(self, access_token: str) -> CentralPortalIdentity:
        """
        Fetch the authenticated user's identity from the CP userinfo endpoint.

        GET {base_url}/oauth/userinfo
            Authorization: Bearer {access_token}

        Returns a normalised CentralPortalIdentity dataclass.

        TODO: Implement and map CP's JSON response fields to the dataclass.
        """
        raise NotImplementedError(
            'CentralPortalClient.get_user_info() is not yet implemented.'
        )

    # ── Token Validation ──────────────────────────────────────────────────────

    def validate_access(self, access_token: str) -> bool:
        """
        Validate whether an access token is still active (introspection).
        Used for short-lived assertion tokens from the Central Portal.

        POST {base_url}/oauth/introspect
            token={access_token}
            client_id={client_id}
            client_secret={client_secret}

        Returns True if active, False otherwise.

        TODO: Implement once CP token introspection endpoint is known.
        """
        raise NotImplementedError(
            'CentralPortalClient.validate_access() is not yet implemented.'
        )

    # ── Logout ────────────────────────────────────────────────────────────────

    def logout(self, access_token: str = '', id_token: str = '') -> Optional[str]:
        """
        Initiate a Central Portal logout.
        Returns the CP logout URL to redirect the browser to, or None
        if propagated logout is not configured.

        Only called when CENTRAL_PORTAL_PROPAGATE_LOGOUT=True.

        TODO: Implement if CP provides a logout endpoint.
        """
        if not getattr(settings, 'CENTRAL_PORTAL_PROPAGATE_LOGOUT', False):
            logger.debug('CentralPortalClient.logout: propagate_logout=False, skipping.')
            return None
        raise NotImplementedError(
            'CentralPortalClient.logout() is not yet implemented.'
        )

    # ── Validate SSO Assertion (non-OAuth flow) ───────────────────────────────

    def validate_assertion(self, assertion_token: str) -> CentralPortalIdentity:
        """
        Validate a signed assertion token (non-OAuth SSO mechanism).
        Used when the CP issues a one-time signed token instead of
        an OAuth authorization code.

        TODO: Implement based on the CP's signing algorithm and key.
        """
        raise NotImplementedError(
            'CentralPortalClient.validate_assertion() is not yet implemented.'
        )

    # ── Health check ──────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """
        Simple connectivity check to the Central Portal.
        Returns True if reachable, False otherwise.
        Used in monitoring / startup checks.
        """
        if not self._base_url:
            logger.warning('CentralPortalClient.ping: CENTRAL_PORTAL_URL is not set.')
            return False
        try:
            import urllib.request
            urllib.request.urlopen(self._base_url, timeout=5)
            return True
        except Exception as exc:
            logger.warning('CentralPortalClient.ping failed: %s', exc)
            return False
