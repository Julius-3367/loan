"""
Django Admin Configuration for Loan Management
Professional admin interfaces for all loan models
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    LoanProduct,
    Customer,
    CreditScore,
    LoanApplication,
    Loan,
    LoanRepayment,
    EmployerVerification,
    GuarantorVerification,
    LoanDocument,
)


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'code',
        'category',
        'min_amount',
        'max_amount',
        'interest_rate',
        'interest_method',
        'is_active',
        'created_at',
    ]
    list_filter = ['category', 'is_active', 'interest_method']
    search_fields = ['name', 'code', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'category', 'description', 'is_active')
        }),
        ('Loan Limits', {
            'fields': ('min_amount', 'max_amount', 'min_tenure_months', 'max_tenure_months')
        }),
        ('Interest Configuration', {
            'fields': ('interest_rate', 'interest_method')
        }),
        ('Fees', {
            'fields': ('origination_fee_percentage', 'origination_fee_fixed', 'processing_fee')
        }),
        ('Penalties', {
            'fields': ('penalty_rate', 'grace_period_days')
        }),
        ('Requirements', {
            'fields': (
                'requires_guarantor',
                'requires_employer_verification',
                'min_credit_score',
                'default_repayment_frequency',
            )
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name',
        'id_number',
        'employment_status',
        'monthly_income',
        'kyc_verified',
        'get_kyc_completion',
        'is_blacklisted',
        'created_at',
    ]
    list_filter = ['kyc_verified', 'is_blacklisted', 'employment_status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'id_number']
    readonly_fields = ['created_at', 'updated_at', 'kyc_verified_at', 'get_age']

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Personal Information', {
            'fields': ('date_of_birth', 'get_age', 'id_number', 'address', 'county', 'city')
        }),
        ('Employment Information', {
            'fields': (
                'employment_status',
                'employer_name',
                'employer_contact',
                'employer_email',
                'monthly_income',
                'employment_date',
            )
        }),
        ('Financial Information', {
            'fields': ('existing_loans', 'bank_name', 'bank_account')
        }),
        ('KYC Documents', {
            'fields': (
                'national_id_file',
                'national_id_verified',
                'bank_statement_file',
                'bank_statement_verified',
                'face_recognition_photo',
                'face_recognition_verified',
                'face_encoding_data',
                'face_scan_date',
            )
        }),
        ('KYC Status', {
            'fields': ('kyc_verified', 'kyc_verified_at', 'kyc_verified_by')
        }),
        ('Status', {
            'fields': ('is_blacklisted', 'blacklist_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Customer Name'

    def get_kyc_completion(self, obj):
        completion = obj.get_kyc_completion_percentage()
        if completion == 100:
            color = 'green'
            status = 'Complete'
        elif completion >= 66:
            color = 'yellow'
            status = 'Good'
        elif completion >= 33:
            color = 'orange'
            status = 'Partial'
        else:
            color = 'red'
            status = 'Low'

        return format_html(
            '<span style="color: {};">{}%</span>',
            color,
            completion
        )
    get_kyc_completion.short_description = 'KYC %'


@admin.register(CreditScore)
class CreditScoreAdmin(admin.ModelAdmin):
    list_display = [
        'customer',
        'loan_application',
        'total_score',
        'recommendation',
        'is_overridden',
        'created_at',
    ]
    list_filter = ['recommendation', 'is_overridden', 'created_at']
    search_fields = ['customer__user__first_name', 'customer__user__last_name']
    readonly_fields = ['created_at', 'calculation_details']

    fieldsets = (
        ('Score Details', {
            'fields': (
                'customer',
                'loan_application',
                'income_score',
                'employment_score',
                'credit_history_score',
                'existing_obligations_score',
                'age_score',
                'total_score',
                'recommendation',
            )
        }),
        ('Override', {
            'fields': ('is_overridden', 'override_reason', 'overridden_by', 'overridden_at'),
            'classes': ('collapse',)
        }),
        ('Calculation', {
            'fields': ('calculation_details', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'application_number',
        'customer_name',
        'loan_product',
        'requested_amount',
        'tenure_months',
        'status_badge',
        'submitted_at',
        'created_at',
    ]
    list_filter = ['status', 'loan_product', 'submitted_at', 'created_at']
    search_fields = [
        'application_number',
        'customer__user__first_name',
        'customer__user__last_name',
        'customer__user__email',
    ]
    readonly_fields = [
        'application_number',
        'created_at',
        'updated_at',
        'submitted_at',
        'reviewed_at',
        'approved_at',
        'disbursed_at',
        'rejected_at',
    ]
    
    fieldsets = (
        ('Application Details', {
            'fields': (
                'application_number',
                'customer',
                'loan_product',
                'requested_amount',
                'tenure_months',
                'repayment_frequency',
                'purpose',
            )
        }),
        ('Status & Workflow', {
            'fields': (
                'status',
                'approved_amount',
                'submitted_at',
                'reviewed_at',
                'approved_at',
                'disbursed_at',
                'rejected_at',
            )
        }),
        ('Approval/Rejection', {
            'fields': ('reviewed_by', 'approved_by', 'rejection_reason')
        }),
        ('Notes', {
            'fields': ('internal_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def customer_name(self, obj):
        return obj.customer.user.get_full_name()
    customer_name.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'DRAFT': '#6c757d',
            'SUBMITTED': '#0dcaf0',
            'UNDER_REVIEW': '#0d6efd',
            'CREDIT_ANALYSIS': '#6610f2',
            'PENDING_APPROVAL': '#fd7e14',
            'APPROVED': '#20c997',
            'EMPLOYER_VERIFICATION': '#17a2b8',
            'GUARANTOR_CONFIRMATION': '#ffc107',
            'DISBURSED': '#198754',
            'REJECTED': '#dc3545',
            'CANCELLED': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = [
        'loan_number',
        'customer_name',
        'loan_product',
        'principal_amount',
        'outstanding_balance',
        'status_badge',
        'disbursement_date',
        'next_payment_date',
    ]
    list_filter = ['status', 'loan_product', 'disbursement_date']
    search_fields = [
        'loan_number',
        'customer__user__first_name',
        'customer__user__last_name',
    ]
    readonly_fields = [
        'loan_number',
        'application',
        'created_at',
        'updated_at',
        'get_payment_progress_percentage',
    ]
    
    fieldsets = (
        ('Loan Details', {
            'fields': (
                'loan_number',
                'application',
                'customer',
                'loan_product',
                'status',
            )
        }),
        ('Amount Breakdown', {
            'fields': (
                'principal_amount',
                'interest_amount',
                'fees',
                'total_amount',
                'outstanding_balance',
                'get_payment_progress_percentage',
            )
        }),
        ('Repayment Details', {
            'fields': (
                'installment_amount',
                'repayment_frequency',
                'tenure_months',
            )
        }),
        ('Dates', {
            'fields': (
                'disbursement_date',
                'first_payment_date',
                'maturity_date',
                'next_payment_date',
                'last_payment_date',
            )
        }),
        ('Status & Penalties', {
            'fields': ('days_overdue', 'penalty_charged')
        }),
        ('Disbursement', {
            'fields': (
                'disbursed_by',
                'disbursement_method',
                'disbursement_reference',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    def customer_name(self, obj):
        return obj.customer.user.get_full_name()
    customer_name.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'ACTIVE': '#198754',
            'PAID': '#0d6efd',
            'OVERDUE': '#ffc107',
            'DEFAULTED': '#dc3545',
            'WRITTEN_OFF': '#6c757d',
            'RESTRUCTURED': '#0dcaf0',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = [
        'receipt_number',
        'loan_link',
        'payment_date',
        'amount',
        'payment_method',
        'payment_type',
        'created_at',
    ]
    list_filter = ['payment_method', 'payment_type', 'payment_date']
    search_fields = ['receipt_number', 'loan__loan_number', 'reference_number']
    readonly_fields = ['receipt_number', 'created_at']
    
    fieldsets = (
        ('Payment Details', {
            'fields': (
                'receipt_number',
                'loan',
                'payment_date',
                'amount',
                'payment_type',
                'payment_method',
                'reference_number',
            )
        }),
        ('Allocation', {
            'fields': ('principal_paid', 'interest_paid', 'penalty_paid')
        }),
        ('Processing', {
            'fields': ('processed_by', 'notes'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def loan_link(self, obj):
        url = reverse('admin:loans_loan_change', args=[obj.loan.pk])
        return format_html('<a href="{}">{}</a>', url, obj.loan.loan_number)
    loan_link.short_description = 'Loan'


@admin.register(EmployerVerification)
class EmployerVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'application_link',
        'employer_name',
        'employment_confirmed',
        'income_confirmed',
        'status',
        'verified_at',
    ]
    list_filter = ['status', 'employment_confirmed', 'income_confirmed']
    search_fields = ['application__application_number', 'employer_name']
    readonly_fields = ['created_at', 'updated_at', 'sent_at', 'verified_at']
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    fieldsets = (
        ('Application', {
            'fields': ('application',)
        }),
        ('Employer Details', {
            'fields': (
                'employer_name',
                'contact_person',
                'contact_email',
                'contact_phone',
            )
        }),
        ('Verification', {
            'fields': (
                'employment_confirmed',
                'income_confirmed',
                'verified_income',
                'status',
            )
        }),
        ('Process', {
            'fields': ('sent_at', 'verified_at', 'verified_by', 'verification_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'


@admin.register(GuarantorVerification)
class GuarantorVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'application_link',
        'phone',
        'relationship',
        'status',
        'confirmed_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'full_name',
        'id_number',
        'phone',
        'email',
        'application__application_number',
    ]
    readonly_fields = ['confirmation_code', 'created_at', 'updated_at', 'sent_at', 'confirmed_at']
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    fieldsets = (
        ('Application', {
            'fields': ('application',)
        }),
        ('Guarantor Details', {
            'fields': (
                'full_name',
                'id_number',
                'phone',
                'email',
                'relationship',
            )
        }),
        ('Financial Information', {
            'fields': ('employer', 'monthly_income')
        }),
        ('Verification', {
            'fields': (
                'status',
                'confirmation_code',
                'sent_at',
                'confirmed_at',
            )
        }),
        ('Notes', {
            'fields': ('guarantor_notes', 'internal_notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'


@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'application_link',
        'document_type',
        'description',
        'is_validated',
        'validated_by',
        'created_at',
    ]
    list_filter = ['document_type', 'is_validated', 'created_at']
    search_fields = ['application__application_number', 'description']
    readonly_fields = ['created_at', 'validated_at']
    
    def __copy__(self):
        """Fix Django template context copying issue"""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result
    
    fieldsets = (
        ('Document Details', {
            'fields': (
                'application',
                'document_type',
                'document_file',
                'description',
            )
        }),
        ('Validation', {
            'fields': ('is_validated', 'validated_by', 'validated_at')
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def application_link(self, obj):
        url = reverse('admin:loans_loanapplication_change', args=[obj.application.pk])
        return format_html('<a href="{}">{}</a>', url, obj.application.application_number)
    application_link.short_description = 'Application'

