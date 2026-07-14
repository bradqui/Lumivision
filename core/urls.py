from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("healthz", views.healthz, name="healthz"),
    # Auth
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="auth/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("join/<uuid:token>/", views.join, name="join"),
    # Account
    path("account/", views.account, name="account"),
    path("account/password/", views.password_change, name="password_change"),
    # Boards
    path("boards/new/", views.board_create, name="board_create"),
    path("b/<slug:slug>/", views.board_detail, name="board_detail"),
    path("b/<slug:slug>/edit/", views.board_edit, name="board_edit"),
    path("b/<slug:slug>/delete/", views.board_delete, name="board_delete"),
    path("b/<slug:slug>/reorder/", views.board_reorder, name="board_reorder"),
    path("b/<slug:slug>/upload/", views.asset_quick_upload, name="asset_quick_upload"),
    path(
        "b/<slug:slug>/remove/<int:pk>/",
        views.board_asset_remove,
        name="board_asset_remove",
    ),
    # Assets
    path("assets/new/", views.asset_create, name="asset_create"),
    path("a/<int:pk>/", views.asset_detail, name="asset_detail"),
    path("a/<int:pk>/edit/", views.asset_edit, name="asset_edit"),
    path("a/<int:pk>/delete/", views.asset_delete, name="asset_delete"),
    path("api/og-preview/", views.og_preview, name="og_preview"),
    # Management
    path("manage/settings/", views.manage_settings, name="manage_settings"),
    path("manage/invites/", views.manage_invites, name="manage_invites"),
    path("manage/invites/<int:pk>/revoke/", views.invite_revoke, name="invite_revoke"),
    path("manage/users/", views.manage_users, name="manage_users"),
    path("manage/users/<int:pk>/update/", views.user_update, name="user_update"),
    path(
        "manage/users/<int:pk>/password/",
        views.user_set_password,
        name="user_set_password",
    ),
]
