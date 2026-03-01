"""
Forms for authentication and user management
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import User


class LoginForm(AuthenticationForm):
    """Custom login form with email as username"""
    
    username = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
            'placeholder': 'Enter your email',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )
    
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded text-alba-orange focus:ring-alba-orange',
        })
    )


class UserRegistrationForm(UserCreationForm):
    """User registration form for customer portal"""
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'password1', 'password2']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
                'placeholder': 'your.email@example.com',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
                'placeholder': 'Last name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
                'placeholder': '+254...',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
            'placeholder': 'Create a strong password',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-alba-orange focus:ring-2 focus:ring-alba-orange/20 outline-none transition',
            'placeholder': 'Confirm your password',
        })
