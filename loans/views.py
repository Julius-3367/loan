"""
Loan Management Views
Customer and Staff views for loan management workflow
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.http import JsonResponse
from decimal import Decimal

from .models import (
    LoanProduct,
    Customer,
    LoanApplication,
    Loan,
    CreditScore,
    GuarantorVerification,
    EmployerVerification,
    LoanDocument,
)
from .forms import (
    CustomerProfileForm,
    LoanApplicationForm,
   GuarantorForm,
    LoanDocumentForm,
    ApplicationReviewForm,
    CreditScoreOverrideForm,
    LoanDisbursementForm,
    EmployerVerificationForm,
)
from .credit_scoring_service import run_credit_score, CreditScoringEngine
from core.views import create_audit_log


# Customer Views

@login_required
def customer_loan_dashboard(request):
    """
    Customer dashboard for loan management
    """
    # Ensure customer profile exists
    customer, created = Customer.objects.get_or_create(user=request.user)
    
    # Get statistics
    applications = LoanApplication.objects.filter(customer=customer)
    active_loans = Loan.objects.filter(customer=customer, status='ACTIVE')
    
    total_borrowed = active_loans.aggregate(
        total=Sum('principal_amount')
    )['total'] or Decimal('0')
    
    total_outstanding = active_loans.aggregate(
        total=Sum('outstanding_balance')
    )['total'] or Decimal('0')
    
    # Recent applications
    recent_applications = applications.order_by('-created_at')[:5]
    
    # Active loans
    my_loans = active_loans.order_by('-disbursement_date')[:5]
    
    context = {
        'customer': customer,
        'applications_count': applications.count(),
        'active_loans_count': active_loans.count(),
        'total_borrowed': total_borrowed,
        'total_outstanding': total_outstanding,
        'recent_applications': recent_applications,
        'my_loans': my_loans,
        'kyc_complete': customer.kyc_verified,
    }
    
    create_audit_log(request.user, 'VIEW', 'LoanDashboard', None, 'Viewed customer loan dashboard')
    
    return render(request, 'loans/customer/dashboard.html', context)


@login_required
def customer_profile(request):
    """
    Customer profile update
    """
    customer, created = Customer.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully')
            create_audit_log(request.user, 'UPDATE', 'Customer', customer.pk, 'Updated customer profile')
            return redirect('loans:customer_dashboard')
    else:
        form = CustomerProfileForm(instance=customer)
    
    context = {
        'form': form,
        'customer': customer,
    }
    
    return render(request, 'loans/customer/profile.html', context)


@login_required
def apply_for_loan(request):
    """
    Customer loan application form
    """
    customer, created = Customer.objects.get_or_create(user=request.user)
    
    # Check if profile is complete
    if not all([customer.id_number, customer.monthly_income, customer.employment_status]):
        messages.warning(request, 'Please complete your profile before applying for a loan')
        return redirect('loans:customer_profile')
    
    if request.method == 'POST':
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.customer = customer
            application.status = LoanApplication.DRAFT
            application.save()
            
            messages.success(request, f'Application {application.application_number} created successfully')
            create_audit_log(request.user, 'CREATE', 'LoanApplication', application.pk, f'Created loan application {application.application_number}')
            
            return redirect('loans:application_detail', pk=application.pk)
    else:
        form = LoanApplicationForm()
    
    # Get active loan products
    products = LoanProduct.objects.filter(is_active=True)
    
    context = {
        'form': form,
        'products': products,
        'customer': customer,
    }
    
    return render(request, 'loans/customer/apply.html', context)


@login_required
def application_detail(request, pk):
    """
    View loan application details
    """
    application = get_object_or_404(LoanApplication, pk=pk)
    
    # Check authorization
    customer = getattr(request.user, 'customer_profile', None)
    is_customer_owner = customer and application.customer == customer
    is_staff = request.user.is_staff_user()
    
    if not (is_customer_owner or is_staff):
        messages.error(request, 'You do not have permission to view this application')
        return redirect('loans:customer_dashboard')
    
    # Get related data
    guarantors = application.guarantors.all()
    documents = application.documents.all()
    credit_score = getattr(application, 'credit_score', None)
    employer_verification = getattr(application, 'employer_verification', None)
    
    # Calculate loan details
    product = application.loan_product
    interest = product.calculate_total_interest(
        application.requested_amount,
        application.tenure_months
    )
    fees = product.calculate_total_fees(application.requested_amount)
    total_repayment = application.requested_amount + interest + fees
    monthly_installment = total_repayment / application.tenure_months
    
    context = {
        'application': application,
        'guarantors': guarantors,
        'documents': documents,
        'credit_score': credit_score,
        'employer_verification': employer_verification,
        'is_customer_owner': is_customer_owner,
        'is_staff': is_staff,
        'loan_details': {
            'principal': application.requested_amount,
            'interest': interest,
            'fees': fees,
            'total': total_repayment,
            'installment': monthly_installment,
        },
    }
    
    return render(request, 'loans/application_detail.html', context)


@login_required
def add_guarantor(request, application_pk):
    """
    Add guarantor to loan application
    """
    application = get_object_or_404(LoanApplication, pk=application_pk)
    
    # Check if customer owns this application
    customer = getattr(request.user, 'customer_profile', None)
    if not customer or application.customer != customer:
        messages.error(request, 'You do not have permission to modify this application')
        return redirect('loans:customer_dashboard')
    
    # Check if application allows modifications
    if application.status not in [LoanApplication.DRAFT, LoanApplication.SUBMITTED]:
        messages.error(request, 'Cannot add guarantors to an application in this status')
        return redirect('loans:application_detail', pk=application_pk)
    
    if request.method == 'POST':
        form = GuarantorForm(request.POST)
        if form.is_valid():
            guarantor = form.save(commit=False)
            guarantor.application = application
            guarantor.save()
            
            messages.success(request, f'Guarantor {guarantor.full_name} added successfully')
            create_audit_log(request.user, 'CREATE', 'GuarantorVerification', guarantor.pk, f'Added guarantor to application {application.application_number}')
            
            return redirect('loans:application_detail', pk=application_pk)
    else:
        form = GuarantorForm()
    
    context = {
        'form': form,
        'application': application,
    }
    
    return render(request, 'loans/customer/add_guarantor.html', context)


@login_required
def upload_document(request, application_pk):
    """
    Upload document for loan application
    """
    application = get_object_or_404(LoanApplication, pk=application_pk)
    
    # Check authorization
    customer = getattr(request.user, 'customer_profile', None)
    if not customer or application.customer != customer:
        messages.error(request, 'You do not have permission to modify this application')
        return redirect('loans:customer_dashboard')
    
    if request.method == 'POST':
        form = LoanDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.application = application
            document.uploaded_by = request.user
            document.save()
            
            messages.success(request, f'{document.get_document_type_display()} uploaded successfully')
            create_audit_log(request.user, 'CREATE', 'LoanDocument', document.pk, f'Uploaded document for application {application.application_number}')
            
            return redirect('loans:application_detail', pk=application_pk)
    else:
        form = LoanDocumentForm()
    
    context = {
        'form': form,
        'application': application,
    }
    
    return render(request, 'loans/customer/upload_document.html', context)


@login_required
def submit_application(request, pk):
    """
    Submit loan application for review
    """
    application = get_object_or_404(LoanApplication, pk=pk)
    
    # Check authorization
    customer = getattr(request.user, 'customer_profile', None)
    if not customer or application.customer != customer:
        messages.error(request, 'You do not have permission to modify this application')
        return redirect('loans:customer_dashboard')
    
    # Check if already submitted
    if application.status != LoanApplication.DRAFT:
        messages.error(request, 'Application has already been submitted')
        return redirect('loans:application_detail', pk=pk)
    
    # Validate application is complete
    errors = []
    
    # Check required documents
    required_docs = [LoanDocument.ID_CARD, LoanDocument.PAYSLIP]
    for doc_type in required_docs:
        if not application.documents.filter(document_type=doc_type).exists():
            errors.append(f'{dict(LoanDocument.DOCUMENT_TYPE_CHOICES)[doc_type]} is required')
    
    # Check guarantor if required
    if application.loan_product.requires_guarantor:
        if not application.guarantors.exists():
            errors.append('At least one guarantor is required for this loan product')
    
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('loans:application_detail', pk=pk)
    
    # Submit application
    application.status = LoanApplication.SUBMITTED
    application.submitted_at = timezone.now()
    application.save()
    
    messages.success(request, f'Application {application.application_number} submitted successfully')
    create_audit_log(request.user, 'UPDATE', 'LoanApplication', application.pk, f'Submitted loan application {application.application_number}')
    
    return redirect('loans:application_detail', pk=pk)


@login_required
def my_applications(request):
    """
    List customer's loan applications
    """
    customer = getattr(request.user, 'customer_profile', None)
    if not customer:
        messages.error(request, 'Customer profile not found')
        return redirect('customer_dashboard')
    
    applications = LoanApplication.objects.filter(customer=customer).order_by('-created_at')
    
    context = {
        'applications': applications,
    }
    
    return render(request, 'loans/customer/my_applications.html', context)


@login_required
def my_loans(request):
    """
    List customer's loans
    """
    customer = getattr(request.user, 'customer_profile', None)
    if not customer:
        messages.error(request, 'Customer profile not found')
        return redirect('customer_dashboard')
    
    loans = Loan.objects.filter(customer=customer).order_by('-disbursement_date')
    
    context = {
        'loans': loans,
    }
    
    return render(request, 'loans/customer/my_loans.html', context)


@login_required
def loan_detail(request, pk):
    """
    View loan details and repayment schedule
    """
    loan = get_object_or_404(Loan, pk=pk)
    
    # Check authorization
    customer = getattr(request.user, 'customer_profile', None)
    is_customer_owner = customer and loan.customer == customer
    is_staff = request.user.is_staff_user()
    
    if not (is_customer_owner or is_staff):
        messages.error(request, 'You do not have permission to view this loan')
        return redirect('loans:customer_dashboard')
    
    # Get repayments
    repayments = loan.repayments.all().order_by('-payment_date')
    
    # Calculate statistics
    total_paid = repayments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    payment_progress = loan.get_payment_progress_percentage()
    
    context = {
        'loan': loan,
        'repayments': repayments,
        'total_paid': total_paid,
        'payment_progress': payment_progress,
        'is_customer_owner': is_customer_owner,
        'is_staff': is_staff,
    }
    
    return render(request, 'loans/loan_detail.html', context)


# Staff Views

@login_required
def staff_loan_dashboard(request):
    """
    Staff dashboard for loan management
    """
    # Check permission
    if not request.user.has_permission('loans', 'view'):
        messages.error(request, 'You do not have permission to access this page')
        return redirect('dashboard')
    
    # Get statistics
    pending_applications = LoanApplication.objects.filter(
        status__in=[
            LoanApplication.SUBMITTED,
            LoanApplication.UNDER_REVIEW,
            LoanApplication.CREDIT_ANALYSIS,
            LoanApplication.PENDING_APPROVAL,
        ]
    ).count()
    
    active_loans = Loan.objects.filter(status='ACTIVE').count()
    overdue_loans = Loan.objects.filter(status='OVERDUE').count()
    
    total_portfolio = Loan.objects.filter(status='ACTIVE').aggregate(
        total=Sum('outstanding_balance')
    )['total'] or Decimal('0')
    
    # Recent applications
    recent_applications = LoanApplication.objects.all().order_by('-created_at')[:10]
    
    # Loans requiring attention
    attention_loans = Loan.objects.filter(
        Q(status='OVERDUE') | Q(days_overdue__gt=0)
    ).order_by('-days_overdue')[:10]
    
    context = {
        'pending_applications': pending_applications,
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'total_portfolio': total_portfolio,
        'recent_applications': recent_applications,
        'attention_loans': attention_loans,
    }
    
    create_audit_log(request.user, 'VIEW', 'StaffLoanDashboard', None, 'Viewed staff loan dashboard')
    
    return render(request, 'loans/staff/dashboard.html', context)


@login_required
def applications_list(request):
    """
    List all loan applications (staff)
    """
    if not request.user.has_permission('loans', 'view'):
        messages.error(request, 'You do not have permission to access this page')
        return redirect('dashboard')
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    
    applications = LoanApplication.objects.all().order_by('-created_at')
    
    if status_filter:
        applications = applications.filter(status=status_filter)
    
    context = {
        'applications': applications,
        'status_filter': status_filter,
        'status_choices': LoanApplication.APPLICATION_STATUS_CHOICES,
    }
    
    return render(request, 'loans/staff/applications_list.html', context)


@login_required
def process_application(request, pk):
    """
    Process loan application (credit analysis and approval)
    """
    if not request.user.has_permission('loans', 'approve'):
        messages.error(request, 'You do not have permission to process applications')
        return redirect('dashboard')
    
    application = get_object_or_404(LoanApplication, pk=pk)
    
    # Run credit score if not done yet
    credit_score = getattr(application, 'credit_score', None)
    if not credit_score and application.status in [
        LoanApplication.UNDER_REVIEW,
        LoanApplication.CREDIT_ANALYSIS,
    ]:
        credit_score = run_credit_score(application)
        messages.info(request, f'Credit score calculated: {credit_score.total_score}/100 - {credit_score.get_recommendation_display()}')
    
    if request.method == 'POST':
        form = ApplicationReviewForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            
            if action == 'approve':
               # Approve application
                application.status = LoanApplication.APPROVED
                application.approved_by = request.user
                application.approved_at = timezone.now()
                application.approved_amount = form.cleaned_data.get('approved_amount') or application.requested_amount
                
                if form.cleaned_data.get('internal_notes'):
                    application.internal_notes += f"\n[{request.user.get_full_name()} - {timezone.now()}]: {form.cleaned_data['internal_notes']}"
                
                application.save()
                
                messages.success(request, f'Application {application.application_number} approved')
                create_audit_log(request.user, 'APPROVE', 'LoanApplication', application.pk, f'Approved loan application {application.application_number}')
                
            elif action == 'reject':
                # Reject application
                application.status = LoanApplication.REJECTED
                application.rejection_reason = form.cleaned_data['rejection_reason']
                application.rejected_at = timezone.now()
                application.reviewed_by = request.user
                
                if form.cleaned_data.get('internal_notes'):
                    application.internal_notes += f"\n[{request.user.get_full_name()} - {timezone.now()}]: {form.cleaned_data['internal_notes']}"
                
                application.save()
                
                messages.success(request, f'Application {application.application_number} rejected')
                create_audit_log(request.user, 'REJECT', 'LoanApplication', application.pk, f'Rejected loan application {application.application_number}')
            
            return redirect('loans:staff_application_detail', pk=pk)
    else:
        form = ApplicationReviewForm()
    
    context = {
        'application': application,
        'form': form,
        'credit_score': credit_score,
    }
    
    return render(request, 'loans/staff/process_application.html', context)


@login_required
def override_credit_score(request, application_pk):
    """
    Override credit score decision
    """
    if not request.user.has_permission('loans', 'approve'):
        messages.error(request, 'You do not have permission to override credit scores')
        return redirect('dashboard')
    
    application = get_object_or_404(LoanApplication, pk=application_pk)
    credit_score = get_object_or_404(CreditScore, loan_application=application)
    
    if request.method == 'POST':
        form = CreditScoreOverrideForm(request.POST)
        if form.is_valid():
            CreditScoringEngine.override_score(
                credit_score,
                form.cleaned_data['new_recommendation'],
                form.cleaned_data['override_reason'],
                request.user
            )
            
            messages.success(request, 'Credit score recommendation overridden')
            create_audit_log(request.user, 'UPDATE', 'CreditScore', credit_score.pk, f'Overrode credit score for application {application.application_number}')
            
            return redirect('loans:staff_application_detail', pk=application_pk)
    else:
        form = CreditScoreOverrideForm()
    
    context = {
        'form': form,
        'application': application,
        'credit_score': credit_score,
    }
    
    return render(request, 'loans/staff/override_credit_score.html', context)


# API endpoint for loan calculator
@login_required
def calculate_loan(request):
    """
    AJAX endpoint to calculate loan details
    """
    if request.method == 'GET':
        product_id = request.GET.get('product_id')
        amount = Decimal(request.GET.get('amount', 0))
        tenure = int(request.GET.get('tenure', 12))
        
        if product_id:
            product = get_object_or_404(LoanProduct, pk=product_id)
            
            interest = product.calculate_total_interest(amount, tenure)
            fees = product.calculate_total_fees(amount)
            total = amount + interest + fees
            installment = total / tenure if tenure > 0 else 0
            
            return JsonResponse({
                'principal': str(amount),
                'interest': str(interest),
                'fees': str(fees),
                'total': str(total),
                'installment': str(installment),
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
