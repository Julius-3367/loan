"""
Loans App URL Configuration — Customer Portal
Staff/admin loan processing is handled in Odoo.
"""

from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    # Customer dashboard
    path("", views.customer_loan_dashboard, name="customer_dashboard"),
    # Profile / KYC
    path("profile/", views.customer_profile, name="customer_profile"),
    # Applications
    path("apply/", views.apply_for_loan, name="apply_for_loan"),
    path("applications/", views.my_applications, name="my_applications"),
    path("application/<int:pk>/", views.application_detail, name="application_detail"),
    path(
        "application/<int:pk>/submit/",
        views.submit_application,
        name="submit_application",
    ),
    # Documents & guarantors
    path(
        "application/<int:application_pk>/upload-document/",
        views.upload_document,
        name="upload_document",
    ),
    path(
        "application/<int:application_pk>/add-guarantor/",
        views.add_guarantor,
        name="add_guarantor",
    ),
    # Active loans
    path("my-loans/", views.my_loans, name="my_loans"),
    path("loan/<int:pk>/", views.loan_detail, name="loan_detail"),
    # Repayment schedule
    path(
        "loan/<int:loan_pk>/schedule/",
        views.repayment_schedule,
        name="repayment_schedule",
    ),
    # PDF statement download
    path(
        "loan/<int:loan_pk>/statement/",
        views.download_statement,
        name="download_statement",
    ),
    # Notifications
    path("notifications/", views.notifications_list, name="notifications"),
    path(
        "notifications/<int:pk>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path(
        "notifications/mark-all-read/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
    # AJAX
    path("api/calculate-loan/", views.calculate_loan, name="calculate_loan"),
]
