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
