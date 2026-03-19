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
    # AJAX
    path("api/calculate-loan/", views.calculate_loan, name="calculate_loan"),
]
