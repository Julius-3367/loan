"""
URL configuration for core app
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # Landing page
    path("", views.landing_page, name="landing"),
    # Authentication
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.logout_view, name="logout"),
    # Password reset flow
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="core/password_reset.html",
            email_template_name="core/email/password_reset_email.html",
            subject_template_name="core/email/password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="core/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="core/password_reset_confirm.html",
            success_url="/password-reset-complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="core/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    # Dashboards
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("admin-panel/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path(
        "customer/dashboard/",
        views.CustomerDashboardView.as_view(),
        name="customer_dashboard",
    ),
    # User approval (admin only)
    path("users/approval/", views.user_approval_list, name="user_approval_list"),
    path("users/approve/<int:user_id>/", views.approve_user, name="approve_user"),
    path("users/reject/<int:user_id>/", views.reject_user, name="reject_user"),
]
