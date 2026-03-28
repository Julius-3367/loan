"""
Loan Management Views — Customer Portal
Handles: customer dashboard, profile, loan application, documents, guarantors,
         repayment schedule, in-portal notifications, PDF statement download.
Staff/admin processing is handled in Odoo.
"""

from decimal import Decimal
from io import BytesIO

from core.views import create_audit_log  # noqa: PLC0415
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
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
    Investment,
    InvestmentTransaction,
    InvestorProfile,
    Loan,
    LoanApplication,
    LoanDocument,
    LoanProduct,
    Notification,
    RepaymentSchedule,
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

    kyc_completion = int(customer.get_kyc_completion_percentage())
    return render(
        request,
        "loans/customer/profile.html",
        {
            "form": form,
            "customer": customer,
            "kyc_completion": kyc_completion,
            "kyc_verified": customer.kyc_verified,
        },
    )


# ---------------------------------------------------------------------------
# Loan application
# ---------------------------------------------------------------------------


@login_required
def apply_for_loan(request):
    """Customer loan application form"""
    customer, _ = Customer.objects.get_or_create(user=request.user)

    # Warn but don't block — let them start Draft and complete profile later
    profile_incomplete = not all(
        [customer.id_number, customer.monthly_income, customer.employment_status]
    )

    # Seed default products if none exist
    if not LoanProduct.objects.filter(is_active=True).exists():
        _seed_loan_products()

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            # Block submission (not draft) if profile incomplete
            action = request.POST.get("action", "submit")
            application = form.save(commit=False)
            application.customer = customer

            if action == "draft":
                application.status = LoanApplication.DRAFT
            else:
                if profile_incomplete:
                    messages.error(
                        request,
                        "Please complete your profile (ID number, income, employment) before submitting.",
                    )
                    return render(
                        request,
                        "loans/customer/apply.html",
                        {
                            "form": form,
                            "products": LoanProduct.objects.filter(is_active=True),
                            "customer": customer,
                            "profile_incomplete": profile_incomplete,
                        },
                    )
                application.status = LoanApplication.SUBMITTED
                application.submitted_at = timezone.now()

            application.save()

            if application.status == LoanApplication.DRAFT:
                messages.success(
                    request,
                    f"Application {application.application_number} saved as draft. "
                    "Complete your profile and submit when ready.",
                )
            else:
                messages.success(
                    request,
                    f"Application {application.application_number} submitted successfully! "
                    "Our team will review it within 24 hours.",
                )
                Notification.objects.create(
                    user=request.user,
                    notification_type="APPLICATION_SUBMITTED",
                    priority="MEDIUM",
                    title="Application Submitted",
                    message=f"Your loan application {application.application_number} has been received and is under review.",
                    loan_application=application,
                )
                from core.services.notifications import NotificationService
                NotificationService.application_submitted(application)

            create_audit_log(
                request.user,
                "CREATE",
                "LoanApplication",
                application.pk,
                f"Created loan application {application.application_number} (status={application.status})",
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
            "profile_incomplete": profile_incomplete,
        },
    )


@login_required
def application_detail(request, pk):
    """Detail view for a single loan application (customer)"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    application = get_object_or_404(LoanApplication, pk=pk, customer=customer)

    documents = LoanDocument.objects.filter(application=application)
    guarantors = GuarantorVerification.objects.filter(application=application)

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
            guarantor.application = application
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


@login_required
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
# Repayment schedule
# ---------------------------------------------------------------------------


@login_required
def repayment_schedule(request, loan_pk):
    """Full repayment schedule for a single active loan"""
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=loan_pk, customer=customer)
    schedule = RepaymentSchedule.objects.filter(loan=loan).order_by(
        "installment_number"
    )

    # If no schedule rows exist yet, generate a projected one on the fly
    if not schedule.exists():
        schedule = _build_projected_schedule(loan)
        persisted = False
    else:
        persisted = True

    return render(
        request,
        "loans/customer/repayment_schedule.html",
        {
            "loan": loan,
            "schedule": schedule,
            "persisted": persisted,
        },
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@login_required
def notifications_list(request):
    """List all in-portal notifications for the logged-in user"""
    notifications = Notification.objects.filter(user=request.user).order_by(
        "-created_at"
    )
    unread_count = notifications.filter(is_read=False).count()
    return render(
        request,
        "loans/customer/notifications.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@login_required
def mark_notification_read(request, pk):
    """Mark a single notification as read (POST only)"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_read()
    return JsonResponse({"status": "ok"})


@login_required
def mark_all_notifications_read(request):
    """Mark every unread notification as read for the current user (POST only)"""
    if request.method == "POST":
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
    return redirect("loans:notifications")


# ---------------------------------------------------------------------------
# PDF Statement
# ---------------------------------------------------------------------------


@login_required
def download_statement(request, loan_pk):
    """
    Generate and stream a PDF loan statement — SRS Section 3.5
    Uses ReportLab; covers the full repayment history for the loan.
    """
    customer, _ = Customer.objects.get_or_create(user=request.user)
    loan = get_object_or_404(Loan, pk=loan_pk, customer=customer)
    repayments = loan.repayments.order_by("payment_date")
    schedule = RepaymentSchedule.objects.filter(loan=loan).order_by(
        "installment_number"
    )

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return HttpResponse(
            "ReportLab is not installed. Run: pip install reportlab",
            status=500,
        )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    NAVY = colors.HexColor("#1e3a5f")
    ORANGE = colors.HexColor("#ff6b35")
    LIGHT_GRAY = colors.HexColor("#f3f4f6")

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        textColor=NAVY,
        fontSize=18,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        textColor=colors.HexColor("#6b7280"),
        fontSize=9,
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        textColor=NAVY,
        fontSize=11,
        spaceBefore=8,
        spaceAfter=4,
    )
    normal = styles["Normal"]
    normal.fontSize = 9

    elements = []

    # ── Header ──────────────────────────────────────────────────────────────
    elements.append(Paragraph("Alba Capital", title_style))
    elements.append(Paragraph("Loan Statement", sub_style))
    elements.append(
        Paragraph(
            f"Generated: {timezone.now().strftime('%d %B %Y, %H:%M')}",
            sub_style,
        )
    )
    elements.append(Spacer(1, 6 * mm))

    # ── Loan Summary ────────────────────────────────────────────────────────
    elements.append(Paragraph("Loan Summary", section_style))
    summary_data = [
        ["Loan Number", loan.loan_number, "Status", loan.get_status_display()],
        ["Product", loan.loan_product.name, "Tenure", f"{loan.tenure_months} months"],
        [
            "Principal",
            f"KES {loan.principal_amount:,.2f}",
            "Interest",
            f"KES {loan.interest_amount:,.2f}",
        ],
        [
            "Total Payable",
            f"KES {loan.total_amount:,.2f}",
            "Outstanding",
            f"KES {loan.outstanding_balance:,.2f}",
        ],
        [
            "Disbursement Date",
            loan.disbursement_date.strftime("%d %b %Y"),
            "Maturity Date",
            loan.maturity_date.strftime("%d %b %Y"),
        ],
        [
            "Next Payment",
            loan.next_payment_date.strftime("%d %b %Y")
            if loan.next_payment_date
            else "—",
            "Installment",
            f"KES {loan.installment_amount:,.2f}",
        ],
    ]
    summary_table = Table(summary_data, colWidths=[45 * mm, 55 * mm, 40 * mm, 45 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BACKGROUND", (0, 0), (0, -1), NAVY),
                ("BACKGROUND", (2, 0), (2, -1), NAVY),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, LIGHT_GRAY]),
                ("ROWBACKGROUNDS", (3, 0), (3, -1), [colors.white, LIGHT_GRAY]),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 6 * mm))

    # ── Repayment Schedule ──────────────────────────────────────────────────
    if schedule.exists():
        elements.append(Paragraph("Repayment Schedule", section_style))
        sched_headers = [
            "#",
            "Due Date",
            "Principal",
            "Interest",
            "Total Due",
            "Paid",
            "Balance",
            "Status",
        ]
        sched_rows = [sched_headers]
        for row in schedule:
            sched_rows.append(
                [
                    str(row.installment_number),
                    row.due_date.strftime("%d %b %Y"),
                    f"{row.principal_due:,.2f}",
                    f"{row.interest_due:,.2f}",
                    f"{row.total_due:,.2f}",
                    f"{row.amount_paid:,.2f}",
                    f"{row.balance:,.2f}",
                    "Paid"
                    if row.is_paid
                    else (
                        "Overdue" if row.due_date < timezone.now().date() else "Pending"
                    ),
                ]
            )
        col_w = [10 * mm, 25 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm]
        sched_table = Table(sched_rows, colWidths=col_w, repeatRows=1)
        sched_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("PADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                    ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        elements.append(sched_table)
        elements.append(Spacer(1, 6 * mm))

    # ── Payment History ──────────────────────────────────────────────────────
    elements.append(Paragraph("Payment History", section_style))
    if repayments.exists():
        pay_headers = [
            "Receipt #",
            "Date",
            "Method",
            "Amount Paid",
            "Principal",
            "Interest",
            "Penalty",
        ]
        pay_rows = [pay_headers]
        for p in repayments:
            pay_rows.append(
                [
                    p.receipt_number,
                    p.payment_date.strftime("%d %b %Y"),
                    p.get_payment_method_display(),
                    f"KES {p.amount:,.2f}",
                    f"{p.principal_paid:,.2f}",
                    f"{p.interest_paid:,.2f}",
                    f"{p.penalty_paid:,.2f}",
                ]
            )
        col_w2 = [32 * mm, 22 * mm, 22 * mm, 28 * mm, 22 * mm, 22 * mm, 22 * mm]
        pay_table = Table(pay_rows, colWidths=col_w2, repeatRows=1)
        pay_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("PADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        elements.append(pay_table)
    else:
        elements.append(Paragraph("No payments recorded yet.", normal))

    # ── Footer ───────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 8 * mm))
    elements.append(
        Paragraph(
            "This statement is generated automatically by the Alba Capital Customer Portal. "
            "For queries, please contact your Alba Capital account manager.",
            ParagraphStyle(
                "Footer",
                parent=normal,
                textColor=colors.HexColor("#9ca3af"),
                fontSize=7,
            ),
        )
    )

    doc.build(elements)
    buffer.seek(0)

    filename = f"AlbaCapital_Statement_{loan.loan_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    create_audit_log(
        request.user,
        "VIEW",
        "Loan",
        loan.pk,
        f"Downloaded PDF statement for loan {loan.loan_number}",
    )
    return response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_projected_schedule(loan):
    """
    Build a projected repayment schedule list (not saved to DB) for display
    when Odoo has not yet pushed the confirmed schedule rows.
    Returns a list of dict-like objects that the template can iterate over.
    """
    from dateutil.relativedelta import relativedelta

    schedule = []
    principal = loan.principal_amount
    total_interest = loan.interest_amount
    tenure = loan.tenure_months

    if tenure <= 0:
        return schedule

    installment = loan.installment_amount
    principal_per_installment = (principal / Decimal(tenure)).quantize(Decimal("0.01"))
    interest_per_installment = (total_interest / Decimal(tenure)).quantize(
        Decimal("0.01")
    )

    running_balance = loan.total_amount
    due_date = loan.first_payment_date

    today = timezone.now().date()

    for i in range(1, tenure + 1):
        running_balance -= installment
        if running_balance < Decimal("0"):
            running_balance = Decimal("0")

        schedule.append(
            {
                "installment_number": i,
                "due_date": due_date,
                "principal_due": principal_per_installment,
                "interest_due": interest_per_installment,
                "fees_due": Decimal("0"),
                "penalty_due": Decimal("0"),
                "total_due": installment,
                "amount_paid": Decimal("0"),
                "balance": running_balance,
                "is_paid": False,
                "paid_date": None,
                # helper flags for template
                "is_overdue": due_date < today,
            }
        )
        due_date = due_date + relativedelta(months=1)

    return schedule


def _seed_loan_products():
    """
    Create all 8 loan products per Alba Capital questionnaire (Section C1).
    Safe to run multiple times — uses update_or_create.
    """
    from django.db import transaction

    products = [
        # -- Salary Advance: 10% fees + 3.5% processing + 1.5% insurance, flat, monthly, 15% penalty, 0–1 month grace
        {
            "code": "SAL001",
            "name": "Salary Advance",
            "category": "salary_advance",
            "description": "Short-term advance for employed individuals backed by payslip.",
            "min_amount": Decimal("5000"),
            "max_amount": Decimal("100000"),
            "interest_rate": Decimal("10.0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("10.0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("15.0"),
            "grace_period_days": 30,
            "min_tenure_months": 1,
            "max_tenure_months": 1,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": True,
            "requires_guarantor": False,
            "is_active": True,
        },
        # -- Business Loan: 10% fees, flat, monthly, 15% penalty, 1 month grace
        {
            "code": "BIZ001",
            "name": "Business Loan",
            "category": "business_loan",
            "description": "Working capital and growth financing for SMEs and individuals.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("500000"),
            "interest_rate": Decimal("10.0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("10.0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("15.0"),
            "grace_period_days": 30,
            "min_tenure_months": 1,
            "max_tenure_months": 12,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": True,
            "is_active": True,
        },
        # -- Personal Loan: 10% fees + 3.5% processing + 1.5% insurance, flat, monthly, 15% penalty, 1 month grace
        {
            "code": "PERS001",
            "name": "Personal Loan",
            "category": "personal_loan",
            "description": "Consumer loans for personal use e.g. school fees, medical.",
            "min_amount": Decimal("10000"),
            "max_amount": Decimal("100000"),
            "interest_rate": Decimal("10.0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("10.0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("15.0"),
            "grace_period_days": 30,
            "min_tenure_months": 1,
            "max_tenure_months": 12,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": False,
            "is_active": True,
        },
        # -- IPF Loan: 10% per annum reducing balance
        {
            "code": "IPF001",
            "name": "IPF Loan",
            "category": "ipf_loan",
            "description": "Insurance Premium Financing — spread insurance premiums over time.",
            "min_amount": Decimal("50000"),
            "max_amount": Decimal("2000000"),
            "interest_rate": Decimal("10.0"),
            "interest_method": "REDUCING_BALANCE",
            "origination_fee_percentage": Decimal("0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("5.0"),
            "grace_period_days": 7,
            "min_tenure_months": 1,
            "max_tenure_months": 12,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": False,
            "is_active": True,
        },
        # -- Bid Bond: fee-based 1.5%, no interest, no grace
        {
            "code": "BID001",
            "name": "Bid Bond",
            "category": "bid_bond",
            "description": "Bid bond financing for contractors and businesses.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("10000000"),
            "interest_rate": Decimal("0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("1.5"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("0"),
            "grace_period_days": 0,
            "min_tenure_months": 1,
            "max_tenure_months": 12,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": False,
            "is_fee_based": True,
            "is_active": True,
        },
        # -- Performance Bond: fee-based 1%
        {
            "code": "PERF001",
            "name": "Performance Bond",
            "category": "performance_bond",
            "description": "Performance bond financing for contractors.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("10000000"),
            "interest_rate": Decimal("0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("1.0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("0"),
            "grace_period_days": 0,
            "min_tenure_months": 1,
            "max_tenure_months": 12,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": False,
            "is_fee_based": True,
            "is_active": True,
        },
        # -- Staff Loan: 5% reducing balance
        {
            "code": "STAFF001",
            "name": "Staff Loan",
            "category": "staff_loan",
            "description": "Employee loans deducted directly from payroll.",
            "min_amount": Decimal("5000"),
            "max_amount": Decimal("500000"),
            "interest_rate": Decimal("5.0"),
            "interest_method": "REDUCING_BALANCE",
            "origination_fee_percentage": Decimal("0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("0"),
            "grace_period_days": 0,
            "min_tenure_months": 1,
            "max_tenure_months": 24,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": False,
            "is_active": True,
        },
        # -- Asset Financing: staff 5% reducing, client 10% flat
        {
            "code": "ASSET001",
            "name": "Asset Finance",
            "category": "asset_financing",
            "description": "Vehicle, equipment, and asset-backed loan facilities.",
            "min_amount": Decimal("100000"),
            "max_amount": Decimal("5000000"),
            "interest_rate": Decimal("10.0"),
            "interest_method": "FLAT_RATE",
            "origination_fee_percentage": Decimal("3.0"),
            "processing_fee": Decimal("0"),
            "penalty_rate": Decimal("5.0"),
            "grace_period_days": 0,
            "min_tenure_months": 6,
            "max_tenure_months": 48,
            "default_repayment_frequency": "MONTHLY",
            "requires_employer_verification": False,
            "requires_guarantor": True,
            "is_active": True,
        },
    ]

    with transaction.atomic():
        for data in products:
            code = data.pop("code")
            LoanProduct.objects.update_or_create(code=code, defaults={**data, "code": code})


# ─────────────────────────────────────────────────────────────────────────────
# INVESTOR PORTAL VIEWS
# ─────────────────────────────────────────────────────────────────────────────


def investor_required(view_func):
    """Decorator: must be logged in with INVESTOR role."""
    from functools import wraps

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if request.user.role != "INVESTOR":
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Access restricted to investors.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _get_or_create_investor_profile(user):
    """Return the InvestorProfile for an investor user, creating if needed."""
    profile, _ = InvestorProfile.objects.get_or_create(user=user)
    return profile


@investor_required
def investor_dashboard(request):
    """Main investor dashboard — portfolio summary."""
    profile = _get_or_create_investor_profile(request.user)
    investments = profile.investments.all()

    active_investments = investments.filter(state=Investment.ACTIVE)
    active_count = active_investments.count()
    total_balance = profile.get_active_balance()
    total_interest = profile.get_total_interest_earned()
    total_invested = sum(inv.principal_amount for inv in active_investments)

    # Recent 5 transactions across all investments
    recent_transactions = InvestmentTransaction.objects.filter(
        investment__investor=profile
    ).order_by("-transaction_date", "-created_at")[:5]

    context = {
        "profile": profile,
        "active_count": active_count,
        "total_balance": total_balance,
        "total_invested": total_invested,
        "total_interest": total_interest,
        "recent_transactions": recent_transactions,
        "investments": active_investments[:5],  # top 5 active
    }
    return render(request, "loans/investor/dashboard.html", context)


@investor_required
def investor_profile(request):
    """Investor KYC profile view & edit."""
    from django import forms as dj_forms

    profile = _get_or_create_investor_profile(request.user)

    class InvestorProfileForm(dj_forms.ModelForm):
        class Meta:
            model = InvestorProfile
            fields = [
                "id_type", "id_number", "date_of_birth", "gender", "nationality",
                "physical_address", "county",
                "bank_name", "bank_account_number", "bank_branch",
                "mpesa_number", "preferred_payment_method",
            ]
            widgets = {
                "date_of_birth": dj_forms.DateInput(attrs={"type": "date"}),
                "physical_address": dj_forms.Textarea(attrs={"rows": 3}),
            }

    if request.method == "POST":
        form = InvestorProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated = form.save(commit=False)
            # Mark partial if at least ID number filled
            if updated.id_number and updated.date_of_birth and updated.county:
                if updated.kyc_status == InvestorProfile.KYC_PENDING:
                    updated.kyc_status = InvestorProfile.KYC_PARTIAL
            if (updated.id_number and updated.date_of_birth and updated.physical_address
                    and updated.county and (updated.bank_account_number or updated.mpesa_number)):
                if updated.kyc_status in (InvestorProfile.KYC_PENDING, InvestorProfile.KYC_PARTIAL):
                    updated.kyc_status = InvestorProfile.KYC_COMPLETE
            updated.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("loans:investor_profile")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = InvestorProfileForm(instance=profile)

    context = {"profile": profile, "form": form}
    return render(request, "loans/investor/profile.html", context)


@investor_required
def my_investments(request):
    """List all investments for the logged-in investor."""
    profile = _get_or_create_investor_profile(request.user)
    investments = profile.investments.all()

    state_filter = request.GET.get("state", "")
    if state_filter:
        investments = investments.filter(state=state_filter)

    total_balance = profile.get_active_balance()
    total_interest = profile.get_total_interest_earned()

    context = {
        "profile": profile,
        "investments": investments,
        "state_filter": state_filter,
        "total_balance": total_balance,
        "total_interest": total_interest,
        "state_choices": Investment.STATE_CHOICES,
    }
    return render(request, "loans/investor/my_investments.html", context)


@investor_required
def investment_detail(request, pk):
    """Detail view for a single investment including transaction history."""
    profile = _get_or_create_investor_profile(request.user)
    investment = get_object_or_404(Investment, pk=pk, investor=profile)

    transactions = investment.transactions.all()
    tx_type_filter = request.GET.get("type", "")
    if tx_type_filter:
        transactions = transactions.filter(transaction_type=tx_type_filter)

    context = {
        "profile": profile,
        "investment": investment,
        "transactions": transactions,
        "tx_type_filter": tx_type_filter,
        "tx_type_choices": InvestmentTransaction.TYPE_CHOICES,
    }
    return render(request, "loans/investor/investment_detail.html", context)


@investor_required
def download_investment_statement(request, pk):
    """Generate and download a PDF investment statement."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    profile = _get_or_create_investor_profile(request.user)
    investment = get_object_or_404(Investment, pk=pk, investor=profile)
    transactions = investment.transactions.filter(
        status=InvestmentTransaction.COMPLETED
    ).order_by("transaction_date")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    brand_green = colors.HexColor("#1a5276")
    brand_light = colors.HexColor("#d6eaf8")
    story = []

    # Header
    story.append(Paragraph("Alba Capital Ltd", styles["Title"]))
    story.append(Paragraph("Investment Account Statement", styles["Heading2"]))
    story.append(Spacer(1, 6 * mm))

    # Investor & investment info table
    info = [
        ["Investor Name", profile.full_name, "Investment No.", investment.investment_number],
        ["Investor ID", profile.investor_number, "Product Type", investment.get_investment_type_display()],
        ["Date of Birth", str(profile.date_of_birth or "—"), "Start Date", str(investment.start_date)],
        ["ID Number", profile.id_number or "—", "Maturity Date", str(investment.maturity_date or "Open Ended")],
    ]
    info_table = Table(info, colWidths=[45 * mm, 55 * mm, 45 * mm, 45 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), brand_light),
        ("BACKGROUND", (2, 0), (2, -1), brand_light),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))

    # Summary
    story.append(Paragraph("Account Summary", styles["Heading3"]))
    summary = [
        ["Principal Amount", f"KES {investment.principal_amount:,.2f}"],
        ["Current Balance", f"KES {investment.current_balance:,.2f}"],
        ["Interest Rate", f"{investment.interest_rate}% p.a."],
        ["Total Interest Earned", f"KES {investment.total_interest_earned:,.2f}"],
        ["Status", investment.get_state_display()],
    ]
    summary_table = Table(summary, colWidths=[80 * mm, 80 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), brand_light),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8 * mm))

    # Transaction history
    story.append(Paragraph("Transaction History", styles["Heading3"]))
    tx_data = [["Date", "Type", "Reference", "Amount (KES)", "Balance (KES)", "Status"]]
    for tx in transactions:
        tx_data.append([
            str(tx.transaction_date),
            tx.get_transaction_type_display(),
            tx.reference or "—",
            f"{tx.amount:,.2f}",
            f"{tx.balance_after:,.2f}",
            tx.get_status_display(),
        ])

    if len(tx_data) > 1:
        tx_table = Table(tx_data, colWidths=[28 * mm, 30 * mm, 35 * mm, 30 * mm, 30 * mm, 25 * mm])
        tx_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), brand_green),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ("PADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ]))
        story.append(tx_table)
    else:
        story.append(Paragraph("No transactions recorded.", styles["Normal"]))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"Statement generated on {timezone.now().strftime('%d %b %Y %H:%M')} "
        "| Alba Capital Ltd | Regulated by Central Bank of Kenya",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(story)
    buffer.seek(0)
    filename = f"statement_{investment.investment_number}_{timezone.now().strftime('%Y%m%d')}.pdf"
    resp = HttpResponse(buffer, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@investor_required
def investor_notifications(request):
    """Notifications for investor users (reuse the Notification model)."""
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
    unread_count = notifications.filter(is_read=False).count()
    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }
    return render(request, "loans/investor/notifications.html", context)


@investor_required
def investor_mark_notification_read(request, pk):
    """Mark a single investor notification as read."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.read_at = timezone.now()
    notif.save(update_fields=["is_read", "read_at"])
    return redirect(request.META.get("HTTP_REFERER", "loans:investor_notifications"))
