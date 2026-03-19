"""
URL configuration for core app
"""

from django.urls import path

from . import views

urlpatterns = [
    # Landing page
    path("", views.landing_page, name="landing"),
    # Authentication
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.logout_view, name="logout"),
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
