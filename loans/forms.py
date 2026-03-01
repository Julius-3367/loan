"""
Loan Application Forms
Forms for customer loan applications and staff processing
"""

from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import (
    LoanApplication,
    LoanProduct,
    Customer,
    GuarantorVerification,
    EmployerVerification,
    LoanDocument,
)


class CustomerProfileForm(forms.ModelForm):
    """
    Form for updating customer profile
    Required before loan application
    """
    
    class Meta:
        model = Customer
        fields = [
            'date_of_birth',
            'id_number',
            'address',
            'county',
            'city',
            'employment_status',
            'employer_name',
            'employer_contact',
            'employer_email',
            'monthly_income',
            'employment_date',
            'existing_loans',
            'bank_name',
            'bank_account',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'id_number': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'ID or Passport Number'
            }),
            'address': forms.Textarea(attrs={
                'rows': 2,
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'Physical address'
            }),
            'county': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'city': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'employment_status': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'employer_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'employer_contact': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '0712345678'
            }),
            'employer_email': forms.EmailInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'monthly_income': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '50000.00',
                'step': '0.01'
            }),
            'employment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'existing_loans': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'bank_account': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
        }


class LoanApplicationForm(forms.ModelForm):
    """
    Form for customer to apply for a loan
    """
    
    class Meta:
        model = LoanApplication
        fields = [
            'loan_product',
            'requested_amount',
            'tenure_months',
            'repayment_frequency',
            'purpose',
        ]
        widgets = {
            'loan_product': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'onchange': 'updateLoanCalculator()'
            }),
            'requested_amount': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '10000.00',
                'step': '0.01',
                'onchange': 'updateLoanCalculator()'
            }),
            'tenure_months': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '12',
                'onchange': 'updateLoanCalculator()'
            }),
            'repayment_frequency': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'purpose': forms.Textarea(attrs={
                'rows': 3,
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'Briefly describe the purpose of this loan'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active loan products
        self.fields['loan_product'].queryset = LoanProduct.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        loan_product = cleaned_data.get('loan_product')
        requested_amount = cleaned_data.get('requested_amount')
        tenure_months = cleaned_data.get('tenure_months')
        
        if loan_product and requested_amount:
            # Validate amount is within product limits
            if requested_amount < loan_product.min_amount:
                raise ValidationError({
                    'requested_amount': f'Minimum loan amount for {loan_product.name} is KES {loan_product.min_amount:,.2f}'
                })
            
            if requested_amount > loan_product.max_amount:
                raise ValidationError({
                    'requested_amount': f'Maximum loan amount for {loan_product.name} is KES {loan_product.max_amount:,.2f}'
                })
        
        if loan_product and tenure_months:
            # Validate tenure is within product limits
            if tenure_months < loan_product.min_tenure_months:
                raise ValidationError({
                    'tenure_months': f'Minimum tenure for {loan_product.name} is {loan_product.min_tenure_months} months'
                })
            
            if tenure_months > loan_product.max_tenure_months:
                raise ValidationError({
                    'tenure_months': f'Maximum tenure for {loan_product.name} is {loan_product.max_tenure_months} months'
                })
        
        return cleaned_data


class GuarantorForm(forms.ModelForm):
    """
    Form for adding guarantor information
    """
    
    class Meta:
        model = GuarantorVerification
        fields = [
            'full_name',
            'id_number',
            'phone',
            'email',
            'relationship',
            'employer',
            'monthly_income',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'Full Name'
            }),
            'id_number': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'ID Number'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '0712345678'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'guarantor@example.com'
            }),
            'relationship': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'e.g., Friend, Colleague, Relative'
            }),
            'employer': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'Employer Name'
            }),
            'monthly_income': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': '50000.00',
                'step': '0.01'
            }),
        }


class LoanDocumentForm(forms.ModelForm):
    """
    Form for uploading loan documents
    """
    
    class Meta:
        model = LoanDocument
        fields = ['document_type', 'document_file', 'description']
        widgets = {
            'document_type': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'document_file': forms.FileInput(attrs={
                'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-alba-orange file:text-white hover:file:bg-opacity-90',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'description': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'placeholder': 'Brief description (optional)'
            }),
        }


# Staff Forms

class ApplicationReviewForm(forms.Form):
    """
    Form for credit officers to review applications
    """
    action = forms.ChoiceField(
        choices=[
            ('approve', 'Approve Application'),
            ('reject', 'Reject Application'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'focus:ring-alba-orange h-4 w-4 text-alba-orange border-gray-300'
        })
    )
    
    approved_amount = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Approved amount (if different from requested)'
        })
    )
    
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Reason for rejection'
        })
    )
    
    internal_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Internal notes (optional)'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        
        if action == 'approve':
            # Approved amount is optional (defaults to requested)
            pass
        elif action == 'reject':
            if not cleaned_data.get('rejection_reason'):
                raise ValidationError({
                    'rejection_reason': 'Rejection reason is required'
                })
        
        return cleaned_data


class CreditScoreOverrideForm(forms.Form):
    """
    Form for overriding credit score recommendation
    """
    new_recommendation = forms.ChoiceField(
        label='Override Recommendation',
        choices=[
            ('APPROVED', 'Approved'),
            ('CONDITIONAL', 'Conditional Approval'),
            ('REJECTED', 'Rejected'),
        ],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
        })
    )
    
    override_reason = forms.CharField(
        label='Justification for Override',
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Provide detailed justification for overriding the automated credit score'
        })
    )
    
    def clean_override_reason(self):
        reason = self.cleaned_data.get('override_reason')
        if len(reason.strip()) < 20:
            raise ValidationError('Override justification must be at least 20 characters')
        return reason


class LoanDisbursementForm(forms.ModelForm):
    """
    Form for disbursing approved loans
    """
    
    class Meta:
        model = LoanApplication
        fields = []
    
    disbursement_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
        })
    )
    
    disbursement_method = forms.ChoiceField(
        choices=[
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('M_PESA', 'M-Pesa'),
            ('CHEQUE', 'Cheque'),
        ],
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
        })
    )
    
    disbursement_reference = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Transaction reference number'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
            'placeholder': 'Additional notes (optional)'
        })
    )


class EmployerVerificationForm(forms.ModelForm):
    """
    Form for employer verification
    """
    
    class Meta:
        model = EmployerVerification
        fields = [
            'employment_confirmed',
            'income_confirmed',
            'verified_income',
            'verification_notes',
            'status',
        ]
        widgets = {
            'employment_confirmed': forms.CheckboxInput(attrs={
                'class': 'focus:ring-alba-orange h-4 w-4 text-alba-orange border-gray-300 rounded'
            }),
            'income_confirmed': forms.CheckboxInput(attrs={
                'class': 'focus:ring-alba-orange h-4 w-4 text-alba-orange border-gray-300 rounded'
            }),
            'verified_income': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm',
                'step': '0.01'
            }),
            'verification_notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
            'status': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-alba-orange focus:ring-alba-orange sm:text-sm'
            }),
        }
