"""
users/views.py
==============
Authentication and user-management API views.

All views use request.user as the single source of authenticated identity.
No view performs its own session/token inspection — authentication is
handled globally by TLPortalSessionAuthentication (core/authentication/).

Authentication flows
--------------------
LOCAL LOGIN:
  1. GET  /api/auth/csrf/    → sets CSRF cookie
  2. POST /api/auth/login/   → LocalAuthBackend validates, Django creates session
  3. All subsequent calls use the session cookie automatically
  4. POST /api/auth/logout/  → session flushed

CENTRAL PORTAL SSO (future — wired but not active):
  1. GET  /api/auth/sso/initiate/   → redirect to CP login URL
  2. GET  /api/auth/sso/callback/   → CP returns code → exchange → local session
  3. All subsequent calls use the session cookie (same as local)
  4. POST /api/auth/logout/         → local session flushed (+ optional CP logout)
"""

import logging

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views import View

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication.exceptions import InvalidSSOResponseError
from .models import User
from .serializers import (
     UserRegistrationSerializer, 
     UserProfileSerializer,  
     UserManagementSerializer, 
     UserCreateSerializer,
     UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


# ─── HTML Login Page ─────────────────────────────────────────────────────────

@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginPageView(View):
    """
    GET  /login/   — renders the login page
    Redirects to /dashboard/ if the user already has an active session.
    The form submits via AJAX to POST /api/auth/login/ — no separate
    authentication logic lives here.
    """

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'Auth/login.html')


class DashboardView(View):
    """
    GET /dashboard/
    Requires an active session. Unauthenticated requests redirect to /login/.
    Auth context (user, role, permissions) is injected by TLPortalAuthMiddleware
    via the auth_context template context processor — nothing is written to
    localStorage or sessionStorage.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect(f'/login/?next={request.path}')
        if not request.user.is_active:
            logout(request)
            return redirect('/login/')
        return render(request, 'Authority/dashboard.html')


# ─── CSRF Token ───────────────────────────────────────────────────────────────

@method_decorator(ensure_csrf_cookie, name='dispatch')
class CSRFTokenView(APIView):
    """
    GET /api/auth/csrf/
    Sets the CSRF cookie. Call this on SPA startup before any unsafe request.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # No auth needed — public endpoint

    def get(self, request):
        return Response({'detail': 'CSRF cookie set.'})


# ─── Local Login ─────────────────────────────────────────────────────────────

@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    """
    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }

    Authenticates via AUTHENTICATION_BACKENDS (LocalAuthBackend → CentralSSOBackend).
    On success: creates a Django session, returns user profile.
    On failure: 401 with typed error code.
    """
    permission_classes    = [permissions.AllowAny]
    authentication_classes = []  # Session doesn't exist yet at login time

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return Response(
                {'detail': 'Username and password are required.', 'code': 'missing_credentials'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)

        if user is None:
            return Response(
                {'detail': 'Invalid credentials or account is inactive.',
                 'code': 'invalid_credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        logger.info('LoginView: session created for %s', user.email)
        return Response({
            'detail': 'Login successful.',
            'user':   UserProfileSerializer(user).data,
        }, status=status.HTTP_200_OK)


# ─── Logout ───────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Flushes the local Django session.
    If CENTRAL_PORTAL_PROPAGATE_LOGOUT=True, returns a CP logout URL.
    """
    # Uses global IsAuthenticatedUser — session must be valid

    def post(self, request):
        user_email = request.user.email
        cp_logout_url = None

        # Ask Central Portal service for logout URL (no-op if SSO disabled)
        try:
            from core.authentication.central_portal import get_central_portal_service
            cp_logout_url = get_central_portal_service().get_logout_url()
        except Exception:
            pass  # Never let CP errors block local logout

        logout(request)
        logger.info('LogoutView: session ended for %s', user_email)

        response_data = {'detail': 'Logged out successfully.'}
        if cp_logout_url:
            response_data['central_portal_logout_url'] = cp_logout_url

        return Response(response_data, status=status.HTTP_200_OK)


# ─── Session Status ───────────────────────────────────────────────────────────

class SessionStatusView(APIView):
    """
    GET /api/auth/status/
    Returns current user profile if authenticated; 401 otherwise.
    Used by the SPA on page load to restore application state.
    """

    def get(self, request):
        return Response({'user': UserProfileSerializer(request.user).data})


# ─── Central Portal SSO — Initiate ───────────────────────────────────────────

class SSOInitiateView(APIView):
    """
    GET /api/auth/sso/initiate/
    Redirects the browser to the Central Portal login page.
    Only active when CENTRAL_PORTAL_ENABLED=True.

    Returns 503 when SSO is not configured, so the frontend can
    gracefully fall back to local login.
    """
    permission_classes    = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.conf import settings
        if not getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            return Response(
                {'detail': 'Central Portal SSO is not enabled.',
                 'code': 'sso_disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            import secrets
            state = secrets.token_urlsafe(32)
            request.session['sso_state'] = state  # CSRF protection for the callback

            from core.authentication.central_portal import get_central_portal_service
            auth_url = get_central_portal_service().get_authorization_url(state=state)
            return Response({'authorization_url': auth_url})
        except NotImplementedError:
            return Response(
                {'detail': 'Central Portal SSO integration is not yet implemented.',
                 'code': 'sso_not_implemented'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.error('SSOInitiateView error: %s', exc)
            raise InvalidSSOResponseError(
                detail='Failed to initiate Central Portal SSO.'
            )


# ─── Central Portal SSO — Callback ───────────────────────────────────────────

class SSOCallbackView(APIView):
    """
    GET /api/auth/sso/callback/
    Receives the authorization code from the Central Portal after login.

    Flow:
      CP redirects → /api/auth/sso/callback/?code=...&state=...
          ↓
      Validate state (CSRF protection)
          ↓
      CentralPortalService.handle_callback(code) → local User
          ↓
      django.contrib.auth.login() → Django session created
          ↓
      Return user profile (SPA redirects to dashboard)

    Currently returns 503 until CentralPortalClient methods are implemented.
    Wired and ready — no URL or settings change needed when CP is ready.
    """
    permission_classes    = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.conf import settings
        if not getattr(settings, 'CENTRAL_PORTAL_ENABLED', False):
            return Response(
                {'detail': 'Central Portal SSO is not enabled.',
                 'code': 'sso_disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        code  = request.query_params.get('code',  '').strip()
        state = request.query_params.get('state', '').strip()
        error = request.query_params.get('error', '').strip()

        if error:
            logger.warning('SSOCallbackView: CP returned error: %s', error)
            raise InvalidSSOResponseError(
                detail=f'Central Portal returned an error: {error}'
            )

        if not code:
            raise InvalidSSOResponseError(detail='Authorization code is missing.')

        # Validate state to prevent CSRF on the callback
        session_state = request.session.pop('sso_state', None)
        if session_state and session_state != state:
            raise InvalidSSOResponseError(detail='Invalid SSO state parameter.')

        try:
            from core.authentication.central_portal import get_central_portal_service
            user = get_central_portal_service().handle_callback(code=code, state=state)
        except InvalidSSOResponseError:
            raise
        except NotImplementedError:
            return Response(
                {'detail': 'Central Portal SSO integration is not yet implemented.',
                 'code': 'sso_not_implemented'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.error('SSOCallbackView: handle_callback failed: %s', exc)
            raise InvalidSSOResponseError(
                detail='SSO authentication failed. Please try again.'
            )

        login(request, user, backend='users.auth_backends.CentralSSOBackend')
        logger.info('SSOCallbackView: SSO session created for %s', user.email)

        return Response({
            'detail': 'SSO login successful.',
            'user':   UserProfileSerializer(user).data,
        }, status=status.HTTP_200_OK)


# ─── User Registration ────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    POST /api/users/register/
    Public — citizen self-registration (local mode only).
    """
    queryset              = User.objects.all()
    serializer_class      = UserRegistrationSerializer
    permission_classes    = [permissions.AllowAny]
    authentication_classes = []


# ─── Profile ──────────────────────────────────────────────────────────────────

class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/users/profile/ — own profile
    PATCH /api/users/profile/ — update own profile
    Uses global IsAuthenticatedUser — no override needed.
    """
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

class UserManagementListView(generics.ListAPIView):
    queryset = User.objects.all().select_related(
        'ulb_fk',
        'ulb_fk__district',
        'zone_fk',
        'ward_fk',
    )
    serializer_class = UserManagementSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserManagementDetailView(generics.RetrieveAPIView):
    queryset = User.objects.all().select_related(
        'ulb_fk',
        'ulb_fk__district',
        'zone_fk',
        'ward_fk',
    )
    serializer_class = UserManagementSerializer
    permission_classes = [permissions.IsAuthenticated]

class UserManagementUpdateView(generics.UpdateAPIView):
    queryset = User.objects.all().select_related(
        'ulb_fk',
        'ulb_fk__district',
        'zone_fk',
        'ward_fk',
    )
    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]