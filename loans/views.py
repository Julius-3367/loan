"""
Loan Management Views — Customer Portal
Handles: customer dashboard, profile, loan application, documents, guarantors
Staff/admin processing is handled in Odoo.
"""

from decimal import Decimal

from core.views import create_audit_log  # noqa: PLC0415
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    CustomerProfileForm,
    GuarantorForm,
    LoanApplicationForm,
    LoanDocumentForm,
)
from .models import (
    Customer,
    GuarantorVerification,
    Loan,
    LoanApplication,
    LoanDocument,
    LoanProduct,
)

# ---------------------------------------------------------------------------
# Customer dashboard
# ---------------------------------------------------------------------------


@login_required
def customer_loan_dashboard(request):
    """Main customer loan dashboard"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    applications = LoanApplication.objects.filter(customer=customer)
    active_loans = Loan.objects.filter(customer=customer, status="ACTIVE")

    from django.db.models import Sum

    total_borrowed = active_loans.aggregate(total=Sum("principal_amount"))[
        "total"
    ] or Decimal("0")
    total_outstanding = active_loans.aggregate(total=Sum("outstanding_balance"))[
        "total"
    ] or Decimal("0")

    context = {
        "customer": customer,
        "applications_count": applications.count(),
        "active_loans_count": active_loans.count(),
        "total_borrowed": total_borrowed,
        "total_outstanding": total_outstanding,
        "recent_applications": applications.order_by("-created_at")[:5],
        "my_loans": active_loans.order_by("-disbursement_date")[:5],
        "kyc_complete": customer.kyc_verified,
    }

    create_audit_log(
        request.user, "VIEW", "LoanDashboard", None, "Viewed customer loan dashboard"
    )
    return render(request, "loans/customer/dashboard.html", context)


# ---------------------------------------------------------------------------
# Customer profile / KYC
# ---------------------------------------------------------------------------


@login_required
def customer_profile(request):
    """View and update customer profile / KYC documents"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = CustomerProfileForm(request.POST, request.FILES, instance=customer)
        if form.is_valid():
            form.save()
            if customer.is_kyc_fully_uploaded() and not customer.kyc_verified:
                messages.info(
                    request,
                    "All KYC documents uploaded. Your account will be verified within 24 hours.",
                )
            messages.success(request, "Profile updated successfully.")
            create_audit_log(
                request.user,
                "UPDATE",
                "Customer",
                customer.pk,
                "Updated customer profile",
            )
            return redirect("loans:customer_dashboard")
    else:
        form = CustomerProfileForm(instance=customer)

    return render(
        request,
        "loans/customer/profile.html",
        {"form": form, "customer": customer},
    )


# ---------------------------------------------------------------------------
# Loan application
# ---------------------------------------------------------------------------


@login_required
def apply_for_loan(request):
    """Customer loan application form"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    # Require minimal profile before applying
    if not all(
        [customer.id_number, customer.monthly_income, customer.employment_status]
    ):
        messages.warning(
            request, "Please complete your profile before applying for a loan."
        )
        return redirect("loans:customer_profile")

    # Seed default products if none exist
    if not LoanProduct.objects.filter(is_active=True).exists():
        _seed_loan_products()

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.customer = customer
            application.status = LoanApplication.SUBMITTED
            application.submitted_at = timezone.now()
            application.save()

            messages.success(
                request,
                (
                    f"Application {application.application_number} submitted successfully! "
                    "Our team will review it within 24 hours."
                ),
            )
            create_audit_log(
                request.user,
                "CREATE",
                "LoanApplication",
                application.pk,
                f"Submitted loan application {application.application_number}",
            )
            return redirect("loans:application_detail", pk=application.pk)
    else:
        form = LoanApplicationForm()

    return render(
        request,
        "loans/customer/apply.html",
        {
            "form": form,
            "products": LoanProduct.objects.filter(is_active=True),
            "customer": customer,
        },
    )


@login_required
def application_detail(request, pk):
    """Detail view for a single loan application (customer)"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    documents = LoanDocument.objects.filter(application=application)
    guarantors = GuarantorVerification.objects.filter(loan_application=application)

    return render(
        request,
        "loans/application_detail.html",
        {
            "application": application,
            "documents": documents,
            "guarantors": guarantors,
        },
    )


@login_required
def my_applications(request):
    """List all of the customer's loan applications"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    applications = LoanApplication.objects.filter(customer=customer).order_by(
        "-created_at"
    )
    return render(
        request,
        "loans/customer/my_applications.html",
        {"applications": applications},
    )


@login_required
def submit_application(request, pk):
    """Final submission of a draft application"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    if application.status != LoanApplication.DRAFT:
        messages.info(request, "This application has already been submitted.")
        return redirect("loans:application_detail", pk=pk)

    application.status = LoanApplication.SUBMITTED
    application.submitted_at = timezone.now()
    application.save()

    messages.success(
        request,
        (
            f"Application {application.application_number} submitted. "
            "You will be notified once it is reviewed."
        ),
    )
    create_audit_log(
        request.user,
        "UPDATE",
        "LoanApplication",
        application.pk,
        f"Submitted application {application.application_number}",
    )
    return redirect("loans:application_detail", pk=pk)


# ---------------------------------------------------------------------------
# Active loans
# ---------------------------------------------------------------------------


@login_required
def my_loans(request):
    """List all active/past loans for the customer"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loans = Loan.objects.filter(customer=customer).order_by("-disbursement_date")
    return render(request, "loans/customer/my_loans.html", {"loans": loans})


@login_required
def loan_detail(request, pk):
    """Detail view for a single active loan"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=pk, customer=customer)
    repayments = loan.repayments.order_by("-payment_date")
    return render(
        request,
        "loans/loan_detail.html",
        {"loan": loan, "repayments": repayments},
    )


# ---------------------------------------------------------------------------
# Documents & guarantors
# ---------------------------------------------------------------------------


@login_required
def upload_document(request, application_pk):
    """Upload a supporting document for an application"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(
        LoanApplication, pk=application_pk, customer=customer
    )

    if request.method == "POST":
        form = LoanDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.application = application
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, "Document uploaded successfully.")
            create_audit_log(
                request.user,
                "CREATE",
                "LoanDocument",
                doc.pk,
                f"Uploaded document for application {application.application_number}",
            )
            return redirect("loans:application_detail", pk=application_pk)
    else:
        form = LoanDocumentForm()

    return render(
        request,
        "loans/customer/upload_document.html",
        {"form": form, "application": application},
    )


@login_required
def add_guarantor(request, application_pk):
    """Add a guarantor to a loan application"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(
        LoanApplication, pk=application_pk, customer=customer
    )

    if request.method == "POST":
        form = GuarantorForm(request.POST)
        if form.is_valid():
            guarantor = form.save(commit=False)
            guarantor.loan_application = application
            guarantor.save()
            messages.success(request, "Guarantor added successfully.")
            create_audit_log(
                request.user,
                "CREATE",
                "GuarantorVerification",
                guarantor.pk,
                f"Added guarantor for application {application.application_number}",
            )
            return redirect("loans:application_detail", pk=application_pk)
    else:
        form = GuarantorForm()

    return render(
        request,
        "loans/customer/add_guarantor.html",
        {"form": form, "application": application},
    )


# ---------------------------------------------------------------------------
# AJAX
# ---------------------------------------------------------------------------


def calculate_loan(request):
    """AJAX endpoint — returns loan cost breakdown for the calculator widget"""
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    try:
        product_id = request.GET.get("product_id")
        amount = Decimal(request.GET.get("amount", "0"))
        tenure = int(request.GET.get("tenure", 12))

        product = LoanProduct.objects.get(pk=product_id, is_active=True)

        interest = product.calculate_total_interest(amount, tenure)
        fees = product.calculate_total_fees(amount)
        total = amount + interest + fees
        installment = total / Decimal(str(tenure)) if tenure > 0 else Decimal("0")

        return JsonResponse(
            {
                "principal": str(amount),
                "interest": str(interest),
                "fees": str(fees),
                "total": str(total),
                "installment": str(installment),
            }
        )
    except LoanProduct.DoesNotExist:
        return JsonResponse({"error": "Loan product not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seed_loan_products():
    """Create default loan products if the table is empty"""
    from django.db import transaction

    products = [
        {
            "code": "QSAL001",
            "name": "Quick Salary Advance",
            "category": "SALARY_ADVANCE",
            "description": "Fast salary advance for employed individuals.",
            "min_amount": Decimal("10000"),
            "max_amount": Decimal("50000"),
            "interest_rate": 15.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 1,
            "max_tenure_months": 6,
            "origination_fee_percentage": 5.0,
            "processing_fee": Decimal("500"),
            "is_active": True,
        },
        {
            "code": "BIZ001",
            "name": "Business Expansion Loan",
            "category": "BUSINESS_LOAN",
            "description": "Flexible financing for business growth.",
            "min_amount": Decimal("50000"),
            "max_amount": Decimal("500000"),
            "interest_rate": 18.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 6,
            "max_tenure_months": 36,
            "origination_fee_percentage": 3.0,
            "processing_fee": Decimal("1500"),
            "is_active": True,
        },
        {
            "code": "ASSET001",
            "name": "Asset Finance — Vehicle",
            "category": "ASSET_FINANCING",
            "description": "Financing for new and used vehicle purchases.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("1000000"),
            "interest_rate": 12.0,
            "interest_method": "REDUCING_BALANCE",
            "min_tenure_months": 12,
            "max_tenure_months": 48,
            "origination_fee_percentage": 2.0,
            "processing_fee": Decimal("2000"),
            "is_active": True,
        },
    ]

    with transaction.atomic():
        for data in products:
            LoanProduct.objects.update_or_create(code=data["code"], defaults=data)
