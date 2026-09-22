"""
users/urls/users.py — User management endpoints
Mounted at: /api/users/
"""

from django.urls import path
from users.views import RegisterView, ProfileView

app_name = 'users'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/',  ProfileView.as_view(),  name='profile'),
]
