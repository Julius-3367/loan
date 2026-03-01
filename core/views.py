"""
Views for authentication and dashboard
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from .forms import LoginForm, UserRegistrationForm
from .models import User, AuditLog


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def create_audit_log(user, action, model_name, object_id='', description='', request=None):
    """Helper function to create audit log entries"""
    log = AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        description=description,
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT', '') if request else ''
    )
    return log


def landing_page(request):
    """Landing page view - public homepage"""
    # Redirect authenticated users to their appropriate dashboard
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('dashboard')
        else:
            return redirect('customer_dashboard')
    
    return render(request, 'landing.html')


class LoginView(FormView):
    """Login view with email-based authentication"""
    
    template_name = 'core/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('dashboard')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        user = form.get_user()
        
        login(self.request, user)
        
        # Create audit log
        create_audit_log(
            user=user,
            action='LOGIN',
            model_name='User',
            object_id=user.id,
            description=f'User logged in: {user.email}',
            request=self.request
        )
        
        # Remember me functionality
        if not form.cleaned_data.get('remember_me'):
            self.request.session.set_expiry(0)
        
        messages.success(self.request, f'Welcome back, {user.get_full_name()}!')
        
        # Redirect based on role
        if user.role == User.CUSTOMER:
            return redirect('customer_dashboard')
        return redirect('dashboard')
    
    def form_invalid(self, form):
        # Check if the user exists but is inactive (pending approval)
        email = form.data.get('username')  # LoginForm uses 'username' field for email
        if email:
            try:
                user = User.objects.get(email=email)
                if not user.is_active:
                    messages.error(
                        self.request,
                        'Your account is pending approval. Please wait for an administrator to approve your account before you can login.'
                    )
                    return super().form_invalid(form)
            except User.DoesNotExist:
                pass
        
        messages.error(self.request, 'Invalid email or password. Please try again.')
        return super().form_invalid(form)


class RegisterView(FormView):
    """Customer registration view"""
    
    template_name = 'core/register.html'
    form_class = UserRegistrationForm
    success_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        user = form.save(commit=False)
        user.role = User.CUSTOMER  # All registrations are customers
        user.is_active = False  # Require admin approval before login
        user.save()
        
        # Create audit log
        create_audit_log(
            user=user,
            action='CREATE',
            model_name='User',
            object_id=user.id,
            description=f'New customer registered: {user.email} (pending approval)',
            request=self.request
        )
        
        messages.success(
            self.request,
            'Registration successful! Your account is pending approval. You will be notified when an admin approves your account.'
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Registration failed. Please check the form and try again.')
        return super().form_invalid(form)


@login_required
def logout_view(request):
    """Logout view"""
    
    # Create audit log before logout
    create_audit_log(
        user=request.user,
        action='LOGOUT',
        model_name='User',
        object_id=request.user.id,
        description=f'User logged out: {request.user.email}',
        request=request
    )
    
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view - role-based access"""
    
    template_name = 'core/dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Redirect customers to customer portal
        if request.user.is_authenticated and request.user.role == User.CUSTOMER:
            return redirect('customer_dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Basic dashboard stats
        context['total_users'] = User.objects.count()
        context['staff_users'] = User.objects.filter(
            role__in=[
                User.ADMIN,
                User.CREDIT_OFFICER,
                User.FINANCE_OFFICER,
                User.HR_OFFICER,
                User.MANAGEMENT
            ]
        ).count()
        context['customers'] = User.objects.filter(role=User.CUSTOMER).count()
        context['recent_audit_logs'] = AuditLog.objects.select_related('user')[:10]
        
        return context


class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    """Customer portal dashboard"""
    
    template_name = 'core/customer_dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Only customers can access this
        if request.user.is_authenticated and request.user.role != User.CUSTOMER:
            messages.warning(request, 'Access denied. This is the customer portal.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Customer-specific stats (will expand when loan module is added)
        context['user_name'] = user.get_full_name()
        context['user_email'] = user.email
        context['member_since'] = user.date_joined
        
        return context

