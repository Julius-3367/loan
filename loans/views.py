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
