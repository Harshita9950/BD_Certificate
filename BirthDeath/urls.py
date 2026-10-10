"""
BirthDeath/urls.py
==================
Root URL configuration for the
Municipal Birth & Death Certificate Management System.

Trade License routes, imports and views have been removed.
The following are retained as generic infrastructure:
  - Authentication (login, logout, CSRF, SSO)
  - User / Role management
  - Geography (District, ULB, Zone, Ward)
  - Workflow Master
  - Fee Master
  - Django admin
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from users.views import LoginPageView, DashboardView

from bd_registration.views import (
    BirthRegistrationPageView,
    DeathRegistrationPageView,
    StillBirthRegistrationPageView,
    AdoptedBirthRegistrationPageView,
)


# ─── Generic Geography Template Views ────────────────────────────────────────

class DistrictMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/district_master.html'
    login_url = '/login/'

class DistrictAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/district_add.html'
    login_url = '/login/'

class DistrictView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/district_view.html'
    login_url = '/login/'

class DistrictEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/district_edit.html'
    login_url = '/login/'


class ULBMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ulb_master.html'
    login_url = '/login/'

class ULBAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ulb_add.html'
    login_url = '/login/'

class ULBView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ulb_view.html'
    login_url = '/login/'

class ULBEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ulb_edit.html'
    login_url = '/login/'


class ZoneMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/zone_master.html'
    login_url = '/login/'

class ZoneAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/zone_add.html'
    login_url = '/login/'

class ZoneView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/zone_view.html'
    login_url = '/login/'

class ZoneEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/zone_edit.html'
    login_url = '/login/'


class WardMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ward_master.html'
    login_url = '/login/'

class WardAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ward_add.html'
    login_url = '/login/'

class WardView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ward_view.html'
    login_url = '/login/'

class WardEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/ward_edit.html'
    login_url = '/login/'


# ─── User / Role Template Views ───────────────────────────────────────────────

class UserMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/user_master.html'
    login_url = '/login/'

class UserAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/user_add.html'
    login_url = '/login/'

class UserView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/user_view.html'
    login_url = '/login/'

class UserEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/user_edit.html'
    login_url = '/login/'


class RoleMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/role_master.html'
    login_url = '/login/'

class RoleAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/role_add.html'
    login_url = '/login/'

class RoleView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/role_view.html'
    login_url = '/login/'

class RoleEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/role_edit.html'
    login_url = '/login/'


# ─── Workflow Template Views ──────────────────────────────────────────────────

class WorkflowMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_master.html'
    login_url = '/login/'

class WorkflowAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_add.html'
    login_url = '/login/'

class WorkflowView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_view.html'
    login_url = '/login/'

class WorkflowEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_edit.html'
    login_url = '/login/'

class WorkflowStepMasterView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_step_master.html'
    login_url = '/login/'

class WorkflowStepAddView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_step_add.html'
    login_url = '/login/'

class WorkflowStepView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_step_view.html'
    login_url = '/login/'

class WorkflowStepEditView(LoginRequiredMixin, TemplateView):
    template_name = 'Authority/workflow_step_edit.html'
    login_url = '/login/'


# ─── URL Patterns ─────────────────────────────────────────────────────────────

urlpatterns = [
    # ── Authentication / Dashboard ────────────────────────────────────────────
    path('',          LoginPageView.as_view(), name='login_page'),
    path('login/',    LoginPageView.as_view(), name='login_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    # ── Birth & Death Registration Form Pages ─────────────────────────────────
    path('birth-registration/',         BirthRegistrationPageView.as_view(),      name='birth_registration'),
    path('death-registration/',         DeathRegistrationPageView.as_view(),      name='death_registration'),
    path('still-birth-registration/',   StillBirthRegistrationPageView.as_view(), name='still_birth_registration'),
    path('adopted-birth-registration/', AdoptedBirthRegistrationPageView.as_view(), name='adopted_birth_registration'),

    # ── Geography Pages ───────────────────────────────────────────────────────
    path('districts/',                  DistrictMasterView.as_view(), name='district_master'),
    path('districts/add/',              DistrictAddView.as_view(),    name='district_add'),
    path('districts/view/<int:pk>/',    DistrictView.as_view(),       name='district_view'),
    path('districts/edit/<int:pk>/',    DistrictEditView.as_view(),   name='district_edit'),

    path('ulbs/',                       ULBMasterView.as_view(), name='ulbs'),
    path('ulbs/add/',                   ULBAddView.as_view(),    name='ulb_add'),
    path('ulbs/view/<int:pk>/',         ULBView.as_view(),       name='ulb_view'),
    path('ulbs/edit/<int:pk>/',         ULBEditView.as_view(),   name='ulb_edit'),

    path('zones/',                      ZoneMasterView.as_view(), name='zones'),
    path('zones/add/',                  ZoneAddView.as_view(),    name='zone_add'),
    path('zones/view/<int:pk>/',        ZoneView.as_view(),       name='zone_view'),
    path('zones/edit/<int:pk>/',        ZoneEditView.as_view(),   name='zone_edit'),

    path('wards/',                      WardMasterView.as_view(), name='wards'),
    path('wards/add/',                  WardAddView.as_view(),    name='ward_add'),
    path('wards/view/<int:pk>/',        WardView.as_view(),       name='ward_view'),
    path('wards/edit/<int:pk>/',        WardEditView.as_view(),   name='ward_edit'),

    # ── User / Role Pages ─────────────────────────────────────────────────────
    path('users/',                      UserMasterView.as_view(), name='users'),
    path('users/add/',                  UserAddView.as_view(),    name='user_add'),
    path('users/view/<int:pk>/',        UserView.as_view(),       name='user_view'),
    path('users/edit/<int:pk>/',        UserEditView.as_view(),   name='user_edit'),

    path('roles/',                      RoleMasterView.as_view(), name='roles'),
    path('roles/add/',                  RoleAddView.as_view(),    name='role_add'),
    path('roles/view/<int:pk>/',        RoleView.as_view(),       name='role_view'),
    path('roles/edit/<int:pk>/',        RoleEditView.as_view(),   name='role_edit'),

    # ── Workflow Pages ────────────────────────────────────────────────────────
    path('workflows/',                        WorkflowMasterView.as_view(),     name='workflows'),
    path('workflows/add/',                    WorkflowAddView.as_view(),        name='workflow_add'),
    path('workflows/view/<int:pk>/',          WorkflowView.as_view(),           name='workflow_view'),
    path('workflows/edit/<int:pk>/',          WorkflowEditView.as_view(),       name='workflow_edit'),

    path('workflow-steps/',                   WorkflowStepMasterView.as_view(), name='workflow_steps'),
    path('workflow-steps/add/',               WorkflowStepAddView.as_view(),    name='workflow_step_add'),
    path('workflow-steps/view/<int:pk>/',     WorkflowStepView.as_view(),       name='workflow_step_view'),
    path('workflow-steps/edit/<int:pk>/',     WorkflowStepEditView.as_view(),   name='workflow_step_edit'),

    # ── Django Admin ──────────────────────────────────────────────────────────
    path('admin/', admin.site.urls),

    # ── Authentication APIs ───────────────────────────────────────────────────
    path('api/auth/',     include('users.urls.auth',  namespace='auth')),
    path('api/users/',    include('users.urls.users', namespace='users')),

    # ── Geography APIs ────────────────────────────────────────────────────────
    path('api/geography/', include('geography.urls', namespace='geography')),

    # ── Workflow APIs ─────────────────────────────────────────────────────────
    path('api/workflow-master/', include('workflow_master.urls')),

    # ── Fee Master APIs ───────────────────────────────────────────────────────
    path('api/fee-master/', include('fee_master.urls')),

    # ── BD Master APIs ────────────────────────────────────────────────────────
    path('api/bd-master/', include('bd_master.urls', namespace='bd_master')),

    # ── BD Registration APIs ──────────────────────────────────────────────────
    path('api/bd-registration/', include('bd_registration.urls', namespace='bd_registration')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
