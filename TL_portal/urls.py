"""
TL_portal/urls.py — Root URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from users.views import LoginPageView, DashboardView

urlpatterns = [
    # ── HTML pages ─────────────────────────────────────────────────────────────
    path('',          LoginPageView.as_view(),  name='login_page'),
    path('login/',    LoginPageView.as_view(),  name='login_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    # ── Django Admin ───────────────────────────────────────────────────────────
    path('admin/', admin.site.urls),

    # ── REST APIs ──────────────────────────────────────────────────────────────
    path('api/auth/',          include('users.urls.auth',         namespace='auth')),
    path('api/users/',         include('users.urls.users',        namespace='users')),
    path('api/geography/',     include('geography.urls',          namespace='geography')),
    path('api/trade-master/',  include('trade_master.urls',       namespace='trade_master')),
    path('api/trade-license/', include('trade_license.urls',      namespace='trade_license')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
