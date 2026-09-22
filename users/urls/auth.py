"""
users/urls/auth.py — Authentication endpoints
Mounted at: /api/auth/
"""

from django.urls import path
from users.views import (
    CSRFTokenView,
    LoginView,
    LogoutView,
    SessionStatusView,
    SSOCallbackView,
    SSOInitiateView,
)

app_name = 'auth'

urlpatterns = [
    # ── Local auth ────────────────────────────────────────────────────────────
    path('csrf/',    CSRFTokenView.as_view(),    name='csrf'),
    path('login/',   LoginView.as_view(),        name='login'),
    path('logout/',  LogoutView.as_view(),       name='logout'),
    path('status/',  SessionStatusView.as_view(), name='status'),

    # ── Central Portal SSO (wired — activated by CENTRAL_PORTAL_ENABLED=True) ─
    path('sso/initiate/',  SSOInitiateView.as_view(),  name='sso_initiate'),
    path('sso/callback/',  SSOCallbackView.as_view(),  name='sso_callback'),
]
