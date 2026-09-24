"""
users/urls/users.py — User management endpoints

Mounted at: /api/users/
"""

from django.urls import path

from users.views import (
    RegisterView,
    ProfileView,
    UserManagementListView,
    UserManagementDetailView,
    UserManagementUpdateView,
    RoleManagementListView,
    PermissionListView,
    RoleManagementUpdateView,
)

app_name = 'users'

urlpatterns = [
    path(
        'register/',
        RegisterView.as_view(),
        name='register',
    ),

    path(
        'profile/',
        ProfileView.as_view(),
        name='profile',
    ),

    path(
        'management/',
        UserManagementListView.as_view(),
        name='user_management',
    ),

    path(
        'management/<int:pk>/',
        UserManagementDetailView.as_view(),
        name='management-detail'
    ),

    path(
        'management/<int:pk>/update/',
        UserManagementUpdateView.as_view(),
        name='management-update'
    ),

    path(
        'roles/',
        RoleManagementListView.as_view(),
        name='role-management',
    ),

    path(
        'permissions/',
        PermissionListView.as_view(),
        name='permission-list',
    ),

    path(
        'roles/<int:pk>/update/',
        RoleManagementUpdateView.as_view(),
        name='role-management-update',
    ),
]