"""
Loan Application Forms — Customer Portal
Handles: customer profile/KYC, loan application, guarantors, document uploads.
Staff-side forms (review, credit score override, disbursement) are handled in Odoo.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Customer,
    GuarantorVerification,
    LoanApplication,
    LoanDocument,
    LoanProduct,
)


class CustomerProfileForm(forms.ModelForm):
    """
    Form for updating customer KYC profile.
    Must be completed before a loan application can be submitted.
    """

    class Meta:
        model = Customer
        fields = [
            "date_of_birth",
            "id_number",
            "address",
            "county",
            "city",
            "employment_status",
            "employer_name",
            "employer_contact",
            "employer_email",
            "monthly_income",
            "employment_date",
            "existing_loans",
            "bank_name",
            "bank_account",
            "national_id_file",
            "bank_statement_file",
            "face_recognition_photo",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "id_number": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "ID or Passport Number",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Physical address",
                }
            ),
            "county": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employment_status": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employer_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "employer_contact": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0712345678",
                }
            ),
            "employer_email": forms.EmailInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "monthly_income": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "50000.00",
                    "step": "0.01",
                }
            ),
            "employment_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "existing_loans": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "bank_account": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "national_id_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*,.pdf",
                }
            ),
            "bank_statement_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*,.pdf",
                }
            ),
            "face_recognition_photo": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-alba-navy"
                    ),
                    "accept": "image/*",
                    "capture": "camera",
                }
            ),
        }


class LoanApplicationForm(forms.ModelForm):
    """
    Form for a customer to apply for a loan product.
    Validates amount and tenure against the selected product's limits.
    """

    class Meta:
        model = LoanApplication
        fields = [
            "loan_product",
            "requested_amount",
            "tenure_months",
            "repayment_frequency",
            "purpose",
        ]
        widgets = {
            "loan_product": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "onchange": "updateLoanCalculator()",
                    "required": True,
                }
            ),
            "requested_amount": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "10000.00",
                    "step": "0.01",
                    "onchange": "updateLoanCalculator()",
                }
            ),
            "tenure_months": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "12",
                    "onchange": "updateLoanCalculator()",
                }
            ),
            "repayment_frequency": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "purpose": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Briefly describe the purpose of this loan",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Build descriptive labels for each active product
        choices = [("", "---------")]
        for product in LoanProduct.objects.filter(is_active=True):
            label = (
                f"{product.name} — {product.get_category_display()} "
                f"| KES {product.min_amount:,.0f}–{product.max_amount:,.0f} "
                f"| {product.interest_rate}% p.a."
            )
            choices.append((product.pk, label))
        self.fields["loan_product"].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("loan_product")
        amount = cleaned_data.get("requested_amount")
        tenure = cleaned_data.get("tenure_months")

        if product and amount:
            if amount < product.min_amount:
                raise ValidationError(
                    {
                        "requested_amount": (
                            f"Minimum loan amount for {product.name} is "
                            f"KES {product.min_amount:,.2f}."
                        )
                    }
                )
            if amount > product.max_amount:
                raise ValidationError(
                    {
                        "requested_amount": (
                            f"Maximum loan amount for {product.name} is "
                            f"KES {product.max_amount:,.2f}."
                        )
                    }
                )

        if product and tenure:
            if tenure < product.min_tenure_months:
                raise ValidationError(
                    {
                        "tenure_months": (
                            f"Minimum tenure for {product.name} is "
                            f"{product.min_tenure_months} months."
                        )
                    }
                )
            if tenure > product.max_tenure_months:
                raise ValidationError(
                    {
                        "tenure_months": (
                            f"Maximum tenure for {product.name} is "
                            f"{product.max_tenure_months} months."
                        )
                    }
                )

        return cleaned_data


class GuarantorForm(forms.ModelForm):
    """Form for adding a guarantor to a loan application."""

    class Meta:
        model = GuarantorVerification
        fields = [
            "full_name",
            "id_number",
            "phone",
            "email",
            "relationship",
            "employer",
            "monthly_income",
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Full Name",
                }
            ),
            "id_number": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "ID Number",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "0712345678",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "guarantor@example.com",
                }
            ),
            "relationship": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "e.g. Friend, Colleague, Relative",
                }
            ),
            "employer": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Employer Name",
                }
            ),
            "monthly_income": forms.NumberInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "50000.00",
                    "step": "0.01",
                }
            ),
        }


class LoanDocumentForm(forms.ModelForm):
    """Form for uploading a supporting document to a loan application."""

    class Meta:
        model = LoanDocument
        fields = ["document_type", "document_file", "description"]
        widgets = {
            "document_type": forms.Select(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                }
            ),
            "document_file": forms.FileInput(
                attrs={
                    "class": (
                        "mt-1 block w-full text-sm text-gray-500 "
                        "file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 "
                        "file:text-sm file:font-semibold file:bg-alba-orange file:text-white "
                        "hover:file:bg-opacity-90"
                    ),
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "class": (
                        "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                        "focus:border-alba-orange focus:ring-alba-orange sm:text-sm"
                    ),
                    "placeholder": "Brief description (optional)",
                }
            ),
        }
