"""
Loans App URL Configuration
"""

from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    # Customer URLs
    path('', views.customer_loan_dashboard, name='customer_dashboard'),
    path('profile/', views.customer_profile, name='customer_profile'),
    path('apply/', views.apply_for_loan, name='apply_for_loan'),
    path('applications/', views.my_applications, name='my_applications'),
    path('application/<int:pk>/', views.application_detail, name='application_detail'),
    path('application/<int:application_pk>/add-guarantor/', views.add_guarantor, name='add_guarantor'),
    path('application/<int:application_pk>/upload-document/', views.upload_document, name='upload_document'),
    path('application/<int:pk>/submit/', views.submit_application, name='submit_application'),
    path('loans/', views.my_loans, name='my_loans'),
    path('loan/<int:pk>/', views.loan_detail, name='loan_detail'),
    
    # Staff URLs
    path('staff/', views.staff_loan_dashboard, name='staff_dashboard'),
    path('staff/applications/', views.applications_list, name='applications_list'),
    path('staff/application/<int:pk>/', views.application_detail, name='staff_application_detail'),
    path('staff/application/<int:pk>/process/', views.process_application, name='process_application'),
    path('staff/application/<int:application_pk>/override-score/', views.override_credit_score, name='override_credit_score'),
    
    # API
    path('api/calculate-loan/', views.calculate_loan, name='calculate_loan'),
]
