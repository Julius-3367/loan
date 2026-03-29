"""
Core views for Alba Capital ERP System
Handles: landing page, authentication, customer dashboard, user approval
"""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import TemplateView

from .forms import LoginForm, UserRegistrationForm
from .models import AuditLog, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_client_ip(request):
    """Extract client IP from request headers"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_audit_log(user, action, model_name, object_id, description, request=None):
    """Create an immutable audit log entry"""
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id) if object_id else "",
        description=description,
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
    )


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------


def landing_page(request):
    """Public landing / marketing page"""
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "landing.html")


def csrf_failure(request, reason=""):
    """Custom CSRF failure page"""
    return render(
        request,
        "core/login.html",
        {
            "error": "Security token expired. Please try again.",
        },
        status=403,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class LoginView(TemplateView):
    template_name = "core/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = LoginForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            email = form.cleaned_data["username"]  # AuthenticationForm uses 'username'
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)

            if user is not None:
                if not user.is_active:
                    messages.error(
                        request,
                        "Your account has been deactivated. Please contact support.",
                    )
                    return render(request, self.template_name, {"form": form})

                if not user.is_approved and user.role == User.CUSTOMER:
                    messages.warning(
                        request,
                        "Your account is pending approval. You will be notified once approved.",
                    )
                    return render(request, self.template_name, {"form": form})

                login(request, user)

                if not form.cleaned_data.get("remember_me"):
                    request.session.set_expiry(0)

                create_audit_log(
                    user,
                    "LOGIN",
                    "User",
                    user.pk,
                    f"User {user.email} logged in",
                    request,
                )
                messages.success(request, f"Welcome back, {user.get_short_name()}!")
                return redirect("dashboard")
            else:
                messages.error(request, "Invalid email or password.")
        else:
            messages.error(request, "Please correct the errors below.")

        return render(request, self.template_name, {"form": form})


class RegisterView(TemplateView):
    template_name = "core/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = UserRegistrationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = User.CUSTOMER
            user.is_approved = False
            user.save()
            create_audit_log(
                user,
                "CREATE",
                "User",
                user.pk,
                f"New customer registered: {user.email}",
                request,
            )
            messages.success(
                request,
                (
                    "Registration successful! Your account is pending approval. "
                    "You will receive a notification once approved."
                ),
            )
            return redirect("login")
        return render(request, self.template_name, {"form": form})


def logout_view(request):
    """Log the user out and redirect to landing page"""
    if request.user.is_authenticated:
        create_audit_log(
            request.user,
            "LOGOUT",
            "User",
            request.user.pk,
            f"User {request.user.email} logged out",
            request,
        )
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("landing")


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


class DashboardView(LoginRequiredMixin, TemplateView):
    """Entry-point dashboard — routes by role"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")

        user = request.user

        if user.role == User.CUSTOMER:
            return redirect("customer_dashboard")

        if user.role == User.INVESTOR:
            return redirect("loans:investor_dashboard")

        # All staff/admin roles go to admin dashboard
        if user.is_superuser or user.role in [
            User.ADMIN,
            User.CREDIT_OFFICER,
            User.FINANCE_OFFICER,
            User.HR_OFFICER,
            User.MANAGEMENT,
        ]:
            return redirect("admin_dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return redirect("login")


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    """Admin / staff overview dashboard"""

    template_name = "core/admin_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or request.user.role
            in [
                User.ADMIN,
                User.CREDIT_OFFICER,
                User.FINANCE_OFFICER,
                User.HR_OFFICER,
                User.MANAGEMENT,
            ]
        ):
            messages.error(request, "Access denied.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_users"] = User.objects.count()
        context["customer_count"] = User.objects.filter(role=User.CUSTOMER).count()
        context["pending_approvals"] = User.objects.filter(
            is_approved=False, role=User.CUSTOMER
        ).count()
        context["staff_count"] = User.objects.exclude(role=User.CUSTOMER).count()
        context["recent_audit_logs"] = AuditLog.objects.select_related("user").order_by(
            "-timestamp"
        )[:10]

        from datetime import timedelta

        from django.utils import timezone

        this_month = timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        last_month_end = this_month - timedelta(seconds=1)
        last_month_start = last_month_end.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        context["this_month_users"] = User.objects.filter(
            date_joined__gte=this_month
        ).count()
        context["last_month_users"] = User.objects.filter(
            date_joined__gte=last_month_start, date_joined__lt=this_month
        ).count()

        last_month_count = context["last_month_users"]
        this_month_count = context["this_month_users"]
        if last_month_count > 0:
            context["growth_rate"] = round(
                ((this_month_count - last_month_count) / last_month_count) * 100, 1
            )
        else:
            context["growth_rate"] = 100 if this_month_count > 0 else 0

        context["recent_registrations"] = User.objects.order_by("-date_joined")[:5]
        return context


class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    """Customer portal dashboard"""

    template_name = "core/customer_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role != User.CUSTOMER:
            messages.warning(request, "Access denied. This is the customer portal.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context["user_name"] = user.get_full_name()
        context["user_email"] = user.email
        context["member_since"] = user.date_joined

        # --- Loan / customer profile data ---
        try:
            from loans.models import (  # noqa: PLC0415
                Customer,
                Loan,
                LoanApplication,
                LoanProduct,
            )

            customer_profile, _ = Customer.objects.get_or_create(user=user)
            context["customer_profile"] = customer_profile
            context["kyc_verified"] = customer_profile.kyc_verified
            context["monthly_income"] = customer_profile.monthly_income or 0
            context["employment_status"] = (
                customer_profile.get_employment_status_display()
            )
            context["employer_name"] = customer_profile.employer_name or ""
            context["has_national_id"] = bool(customer_profile.national_id_file)
            context["has_bank_statement"] = bool(customer_profile.bank_statement_file)
            context["has_face_photo"] = bool(customer_profile.face_recognition_photo)

            kyc_fields = [
                customer_profile.id_number,
                customer_profile.date_of_birth,
                customer_profile.address,
                customer_profile.monthly_income,
                customer_profile.employer_name,
                customer_profile.national_id_file,
                customer_profile.bank_statement_file,
                customer_profile.face_recognition_photo,
            ]
            context["kyc_completion"] = int(
                sum(1 for f in kyc_fields if f) / len(kyc_fields) * 100
            )

            applications = LoanApplication.objects.filter(  # type: ignore[attr-defined]
                customer=customer_profile
            ).order_by("-created_at")
            context["applications_count"] = applications.count()
            context["recent_applications"] = applications[:5]

            active_loans = Loan.objects.filter(  # type: ignore[attr-defined]
                customer=customer_profile, status="ACTIVE"
            )
            context["active_loans_count"] = active_loans.count()
            context["recent_loans"] = active_loans.order_by("-disbursement_date")[:5]
            from django.db.models import Sum

            context["total_borrowed"] = (
                active_loans.aggregate(total=Sum("principal_amount"))["total"] or 0
            )

            context["available_products"] = LoanProduct.objects.filter(  # type: ignore[attr-defined]
                is_active=True
            )[:3]

        except Exception:
            context.update(
                {
                    "customer_profile": None,
                    "kyc_verified": False,
                    "kyc_completion": 0,
                    "monthly_income": 0,
                    "employment_status": "Not Set",
                    "employer_name": "",
                    "has_national_id": False,
                    "has_bank_statement": False,
                    "has_face_photo": False,
                    "applications_count": 0,
                    "recent_applications": [],
                    "active_loans_count": 0,
                    "recent_loans": [],
                    "total_borrowed": 0,
                    "available_products": [],
                }
            )

        return context


# ---------------------------------------------------------------------------
# User approval (admin only)
# ---------------------------------------------------------------------------


def _is_admin(user):
    return user.is_superuser or user.role == User.ADMIN


@login_required
def user_approval_list(request):
    """List customers pending approval"""
    if not _is_admin(request.user):
        messages.error(request, "You do not have permission to access user approval.")
        return redirect("dashboard")

    pending_users = User.objects.filter(is_approved=False, role=User.CUSTOMER).order_by(
        "-date_joined"
    )
    approved_users = User.objects.filter(is_approved=True, role=User.CUSTOMER).order_by(
        "-date_joined"
    )[:20]

    return render(
        request,
        "core/user_approval.html",
        {
            "pending_users": pending_users,
            "approved_users": approved_users,
        },
    )


@login_required
def approve_user(request, user_id):
    """Approve a customer account"""
    if not _is_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect("dashboard")

    user = get_object_or_404(User, pk=user_id)
    user.is_approved = True
    user.save()
    create_audit_log(
        request.user,
        "APPROVE",
        "User",
        user.pk,
        f"Approved user account: {user.email}",
        request,
    )
    messages.success(request, f"{user.get_full_name()} has been approved.")
    return redirect("user_approval_list")


@login_required
def reject_user(request, user_id):
    """Reject / deactivate a customer account"""
    if not _is_admin(request.user):
        messages.error(request, "Permission denied.")
        return redirect("dashboard")

    user = get_object_or_404(User, pk=user_id)
    user.is_active = False
    user.save()
    create_audit_log(
        request.user,
        "REJECT",
        "User",
        user.pk,
        f"Rejected user account: {user.email}",
        request,
    )
    messages.success(request, f"{user.get_full_name()} has been rejected.")
    return redirect("user_approval_list")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


# ─────────────────────────────────────────────────────────────────────────────
# STAFF PORTAL VIEWS
# ─────────────────────────────────────────────────────────────────────────────


def staff_required(view_func):
    """Decorator: must be logged in with a staff role."""
    from functools import wraps

    STAFF_ROLES = {
        User.ADMIN,
        User.CREDIT_OFFICER,
        User.FINANCE_OFFICER,
        User.HR_OFFICER,
        User.MANAGEMENT,
    }

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not (request.user.is_superuser or request.user.role in STAFF_ROLES):
            messages.error(request, "Access denied. Staff access only.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped


@login_required
@staff_required
def staff_loan_applications(request):
    """
    Credit officer / finance officer: view and filter all loan applications.
    """
    from loans.models import LoanApplication, LoanProduct

    qs = LoanApplication.objects.select_related(
        "customer__user", "loan_product"
    ).order_by("-created_at")

    # Filters
    status_filter = request.GET.get("status", "")
    product_filter = request.GET.get("product", "")
    search = request.GET.get("q", "").strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if product_filter:
        qs = qs.filter(loan_product__id=product_filter)
    if search:
        qs = qs.filter(
            application_number__icontains=search
        ) | qs.filter(
            customer__user__first_name__icontains=search
        ) | qs.filter(
            customer__user__last_name__icontains=search
        ) | qs.filter(
            customer__user__email__icontains=search
        )

    # Stats for top cards
    stats = {
        "total": LoanApplication.objects.count(),
        "pending": LoanApplication.objects.filter(status="SUBMITTED").count(),
        "under_review": LoanApplication.objects.filter(status="UNDER_REVIEW").count(),
        "approved": LoanApplication.objects.filter(status="APPROVED").count(),
        "rejected": LoanApplication.objects.filter(status="REJECTED").count(),
    }

    context = {
        "applications": qs[:100],  # Cap at 100 rows; paginate if needed
        "status_filter": status_filter,
        "product_filter": product_filter,
        "search": search,
        "status_choices": LoanApplication.APPLICATION_STATUS_CHOICES,
        "products": LoanProduct.objects.filter(is_active=True),
        "stats": stats,
    }
    return render(request, "core/staff/loan_applications.html", context)


@login_required
@staff_required
def staff_application_detail(request, pk):
    """
    Detailed view of a single loan application for credit officer review.
    Allows status transitions: submit_review, approve, reject, request_info, disburse.
    """
    from loans.models import (
        GuarantorVerification,
        LoanApplication,
        LoanDocument,
        LoanRepayment,
    )

    application = get_object_or_404(
        LoanApplication.objects.select_related("customer__user", "loan_product"), pk=pk
    )
    documents = LoanDocument.objects.filter(application=application)
    guarantors = GuarantorVerification.objects.filter(application=application)

    # Previous repayment history for this customer
    past_repayments = LoanRepayment.objects.filter(
        loan__customer=application.customer
    ).order_by("-payment_date")[:10]

    if request.method == "POST":
        action = request.POST.get("action")
        note = request.POST.get("note", "").strip()
        allowed_transitions = {
            "submit_review": ("SUBMITTED", "UNDER_REVIEW"),
            "approve": ("UNDER_REVIEW", "APPROVED"),
            "reject": ("UNDER_REVIEW", "REJECTED"),
            "request_info": (None, "INFORMATION_REQUIRED"),  # any state
            "disburse": ("APPROVED", "DISBURSED"),
        }

        if action in allowed_transitions:
            required_from, to_status = allowed_transitions[action]
            if required_from is None or application.status == required_from:
                old_status = application.status
                application.status = to_status
                if action == "approve":
                    application.approved_by = request.user
                    from django.utils import timezone
                    application.approved_at = timezone.now()
                if action == "reject" and note:
                    application.rejection_reason = note
                application.save(update_fields=[
                    "status", "approved_by", "approved_at", "rejection_reason"
                ])
                create_audit_log(
                    user=request.user,
                    action=f"APPLICATION_{action.upper()}",
                    model_name="LoanApplication",
                    object_id=application.pk,
                    description=(
                        f"{application.application_number} status changed "
                        f"{old_status} → {to_status}. {note}"
                    ),
                    request=request,
                )
                # Notify customer
                from loans.models import Notification
                notif_type_map = {
                    "approve": Notification.APPLICATION_APPROVED,
                    "reject": Notification.APPLICATION_REJECTED,
                    "submit_review": Notification.APPLICATION_UNDER_REVIEW,
                    "disburse": Notification.LOAN_DISBURSED,
                    "request_info": Notification.GENERAL,
                }
                Notification.create_for_user(
                    user=application.customer.user,
                    notification_type=notif_type_map.get(action, Notification.GENERAL),
                    title=f"Application {application.application_number} Update",
                    message=(
                        f"Your application status has changed to "
                        f"{application.get_status_display()}."
                        + (f" Note: {note}" if note else "")
                    ),
                    loan_application=application,
                )
                # Send email/SMS via notification service
                from core.services.notifications import NotificationService
                if action == "approve":
                    NotificationService.application_approved(application)
                elif action == "reject":
                    NotificationService.application_rejected(application)
                elif action == "disburse":
                    from loans.models import Loan
                    loan_obj = Loan.objects.filter(application=application).first()
                    if loan_obj:
                        NotificationService.loan_disbursed(loan_obj)
                messages.success(
                    request, f"Application {action.replace('_', ' ')} successfully."
                )
            else:
                messages.error(
                    request,
                    f"Cannot {action}: application is in status '{application.get_status_display()}'.",
                )
        else:
            messages.error(request, "Unknown action.")
        return redirect("staff_application_detail", pk=pk)

    context = {
        "application": application,
        "documents": documents,
        "guarantors": guarantors,
        "past_repayments": past_repayments,
        "can_review": application.status == "SUBMITTED",
        "can_approve": application.status == "UNDER_REVIEW",
        "can_reject": application.status == "UNDER_REVIEW",
        "can_disburse": application.status == "APPROVED",
    }
    return render(request, "core/staff/application_detail.html", context)


@login_required
@staff_required
def staff_customers(request):
    """
    Staff list of all customers with KYC status, search, filter.
    """
    from loans.models import Customer

    customers = Customer.objects.select_related("user").order_by("-created_at")

    search = request.GET.get("q", "").strip()
    kyc_filter = request.GET.get("kyc", "")
    employment_filter = request.GET.get("employment", "")

    if search:
        customers = customers.filter(
            user__first_name__icontains=search
        ) | customers.filter(
            user__last_name__icontains=search
        ) | customers.filter(
            user__email__icontains=search
        ) | customers.filter(
            id_number__icontains=search
        )
    if kyc_filter:
        customers = customers.filter(kyc_verified=(kyc_filter == "true"))
    if employment_filter:
        customers = customers.filter(employment_status=employment_filter)

    context = {
        "customers": customers[:200],
        "search": search,
        "kyc_filter": kyc_filter,
        "employment_filter": employment_filter,
        "employment_choices": Customer.EMPLOYMENT_STATUS_CHOICES,
        "total_customers": Customer.objects.count(),
        "kyc_verified_count": Customer.objects.filter(kyc_verified=True).count(),
    }
    return render(request, "core/staff/customers.html", context)


@login_required
@staff_required
def staff_customer_detail(request, pk):
    """
    Staff view of a single customer: KYC info, all applications, active loans.
    """
    from loans.models import Customer, Loan, LoanApplication

    customer = get_object_or_404(Customer.objects.select_related("user"), pk=pk)
    applications = LoanApplication.objects.filter(customer=customer).order_by("-created_at")
    loans = Loan.objects.filter(customer=customer).order_by("-disbursement_date")

    context = {
        "customer": customer,
        "applications": applications,
        "loans": loans,
    }
    return render(request, "core/staff/customer_detail.html", context)


@login_required
@staff_required
def staff_loan_portfolio(request):
    """
    Management / finance officer: portfolio-level stats.
    """
    from decimal import Decimal

    from django.db.models import Count, Sum

    from loans.models import Loan, LoanApplication, LoanRepayment

    # Application pipeline
    pipeline = LoanApplication.objects.values("status").annotate(
        count=Count("id")
    ).order_by("status")

    # Active loan portfolio
    active_loans = Loan.objects.filter(status="ACTIVE")
    portfolio_summary = active_loans.aggregate(
        total_principal=Sum("principal_amount"),
        total_outstanding=Sum("outstanding_balance"),
    )

    # Repayments this month
    from datetime import date
    today = date.today()
    month_start = today.replace(day=1)
    monthly_repayments = LoanRepayment.objects.filter(
        payment_date__gte=month_start
    ).aggregate(total=Sum("amount_paid"))

    # Overdue loans (maturity_date passed but still active)
    overdue_count = Loan.objects.filter(
        status="ACTIVE",
        maturity_date__lt=today,
    ).count()

    context = {
        "pipeline": {item["status"]: item["count"] for item in pipeline},
        "total_principal": portfolio_summary["total_principal"] or Decimal("0"),
        "total_outstanding": portfolio_summary["total_outstanding"] or Decimal("0"),
        "monthly_repayments": monthly_repayments["total"] or Decimal("0"),
        "active_loan_count": active_loans.count(),
        "overdue_count": overdue_count,
    }
    return render(request, "core/staff/loan_portfolio.html", context)
