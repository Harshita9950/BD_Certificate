from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from users.views import LoginPageView, DashboardView


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

urlpatterns = [
    path('', LoginPageView.as_view(), name='login_page'),
    path('login/', LoginPageView.as_view(), name='login_page'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    path('districts/', DistrictMasterView.as_view(), name='district_master'),
    path('districts/add/', DistrictAddView.as_view(), name='district_add'),
    path('districts/view/<int:pk>/', DistrictView.as_view(), name='district_view'),
    path('districts/edit/<int:pk>/', DistrictEditView.as_view(), name='district_edit'),

    path('ulbs/', ULBMasterView.as_view(), name='ulbs'),
    path('ulbs/add/', ULBAddView.as_view(), name='ulb_add'),
    path('ulbs/view/<int:pk>/', ULBView.as_view(), name='ulb_view'),
    path('ulbs/edit/<int:pk>/', ULBEditView.as_view(), name='ulb_edit'),

    path('zones/', ZoneMasterView.as_view(), name='zones'),
    path('zones/add/', ZoneAddView.as_view(), name='zone_add'),
    path('zones/view/<int:pk>/', ZoneView.as_view(), name='zone_view'),
    path('zones/edit/<int:pk>/', ZoneEditView.as_view(), name='zone_edit'),

    path('wards/', WardMasterView.as_view(), name='wards'),
    path('wards/add/', WardAddView.as_view(), name='ward_add'),
    path('wards/view/<int:pk>/', WardView.as_view(), name='ward_view'),
    path('wards/edit/<int:pk>/', WardEditView.as_view(), name='ward_edit'),

    path('users/', UserMasterView.as_view(), name='users'),
    path('users/add/', UserAddView.as_view(), name='user_add'),
    path('users/view/<int:pk>/', UserView.as_view(), name='user_view'),
    path('users/edit/<int:pk>/', UserEditView.as_view(), name='user_edit'),

    path('admin/', admin.site.urls),

    path('api/auth/', include('users.urls.auth', namespace='auth')),
    path('api/users/', include('users.urls.users', namespace='users')),
    path('api/geography/', include('geography.urls', namespace='geography')),
    path('api/trade-master/', include('trade_master.urls', namespace='trade_master')),
    path('api/trade-license/', include('trade_license.urls', namespace='trade_license')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )