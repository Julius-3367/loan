"""
Loan Management Models for Alba Capital ERP
SRS Section 3.1 - Loan Management System

Models include:
- LoanProduct: Configurable loan products (SRS 3.1.1)
- Customer: Customer profile linked to User
- LoanApplication: Loan application workflow (SRS 3.1.2)
- Loan: Active loans
- LoanRepayment: Repayment tracking
- CreditScore: Credit evaluation (SRS 3.1.3)
- EmployerVerification: Employer verification (SRS 3.1.4)
- GuarantorVerification: Guarantor verification (SRS 3.1.4)
- LoanDocument: Document management
"""

from decimal import Decimal

from core.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class LoanProduct(models.Model):
    """
    Loan Product Configuration Model - SRS 3.1.1
    Supports: Salary Advances, Business Loans, Asset Financing
    """

    # Product Categories as per SRS
    SALARY_ADVANCE = "SALARY_ADVANCE"
    BUSINESS_LOAN = "BUSINESS_LOAN"
    ASSET_FINANCING = "ASSET_FINANCING"

    PRODUCT_CATEGORY_CHOICES = [
        (SALARY_ADVANCE, "Salary Advance"),
        (BUSINESS_LOAN, "Business Loan"),
        (ASSET_FINANCING, "Asset Financing"),
    ]

    # Interest Rate Methodology
    FLAT_RATE = "FLAT_RATE"
    REDUCING_BALANCE = "REDUCING_BALANCE"

    INTEREST_METHOD_CHOICES = [
        (FLAT_RATE, "Flat Rate"),
        (REDUCING_BALANCE, "Reducing Balance"),
    ]

    # Repayment Frequency
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"

    FREQUENCY_CHOICES = [
        (WEEKLY, "Weekly"),
        (FORTNIGHTLY, "Fortnightly"),
        (MONTHLY, "Monthly"),
    ]

    # Basic Fields
    name = models.CharField("Product Name", max_length=100, unique=True)
    code = models.CharField("Product Code", max_length=20, unique=True)
    category = models.CharField(
        "Category", max_length=20, choices=PRODUCT_CATEGORY_CHOICES
    )
    description = models.TextField("Description", blank=True)

    # Loan Amount Limits
    min_amount = models.DecimalField(
        "Minimum Loan Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    max_amount = models.DecimalField(
        "Maximum Loan Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # Interest Configuration
    interest_rate = models.DecimalField(
        "Interest Rate (%)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    interest_method = models.CharField(
        "Interest Calculation Method",
        max_length=20,
        choices=INTEREST_METHOD_CHOICES,
        default=REDUCING_BALANCE,
    )

    # Fees Configuration
    origination_fee_percentage = models.DecimalField(
        "Origination Fee (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    origination_fee_fixed = models.DecimalField(
        "Origination Fee (Fixed Amount)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    processing_fee = models.DecimalField(
        "Processing Fee",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Penalty Configuration
    penalty_rate = models.DecimalField(
        "Penalty Rate (% per month on overdue amount)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("2"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("50"))],
    )
    grace_period_days = models.PositiveIntegerField(
        "Grace Period (Days)",
        default=0,
        help_text="Days before penalties start accruing",
    )

    # Repayment Terms
    min_tenure_months = models.PositiveIntegerField(
        "Minimum Tenure (Months)", default=1
    )
    max_tenure_months = models.PositiveIntegerField(
        "Maximum Tenure (Months)", default=12
    )
    default_repayment_frequency = models.CharField(
        "Default Repayment Frequency",
        max_length=15,
        choices=FREQUENCY_CHOICES,
        default=MONTHLY,
    )

    # Status and Tracking
    is_active = models.BooleanField("Active", default=True)
    requires_guarantor = models.BooleanField("Requires Guarantor", default=False)
    requires_employer_verification = models.BooleanField(
        "Requires Employer Verification", default=False
    )
    min_credit_score = models.PositiveIntegerField(
        "Minimum Credit Score",
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="Minimum credit score required (0-100)",
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_loan_products"
    )

    class Meta:
        db_table = "loan_products"
        verbose_name = "Loan Product"
        verbose_name_plural = "Loan Products"
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def calculate_total_fees(self, loan_amount):
        """Calculate total fees for a loan amount"""
        from decimal import Decimal

        # Ensure all values are Decimal
        loan_amount = Decimal(str(loan_amount))
        origination_fee_percentage = Decimal(str(self.origination_fee_percentage))

        percentage_fee = (loan_amount * origination_fee_percentage) / Decimal("100")
        return percentage_fee + self.origination_fee_fixed + self.processing_fee

    def calculate_total_interest(self, principal, tenure_months):
        """Calculate total interest based on method"""
        from decimal import Decimal

        # Ensure all values are Decimal
        principal = Decimal(str(principal))
        tenure_months = Decimal(str(tenure_months))
        rate = Decimal(str(self.interest_rate)) / Decimal("100")

        if self.interest_method == self.FLAT_RATE:
            # Flat rate: simple interest on principal
            total_interest = principal * rate * tenure_months
        else:
            # Reducing balance: more complex calculation
            # Simplified formula for monthly payments
            monthly_rate = (
                rate / Decimal("12") if tenure_months > Decimal("1") else rate
            )
            total_interest = (
                principal * monthly_rate * tenure_months * Decimal("0.5")
            )  # Approximate

        return total_interest


class Customer(models.Model):
    """
    Customer Profile Model
    Extends User model with customer-specific information
    """

    # Employment Status
    EMPLOYED = "EMPLOYED"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    UNEMPLOYED = "UNEMPLOYED"
    RETIRED = "RETIRED"

    EMPLOYMENT_STATUS_CHOICES = [
        (EMPLOYED, "Employed"),
        (SELF_EMPLOYED, "Self Employed"),
        (UNEMPLOYED, "Unemployed"),
        (RETIRED, "Retired"),
    ]

    # Link to User
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        primary_key=True,
    )

    # Personal Information
    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    id_number = models.CharField(
        "ID/Passport Number", max_length=50, unique=True, null=True, blank=True
    )
    address = models.TextField("Physical Address", blank=True)
    county = models.CharField("County", max_length=100, blank=True)
    city = models.CharField("City/Town", max_length=100, blank=True)

    # Employment Information
    employment_status = models.CharField(
        "Employment Status",
        max_length=20,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default=EMPLOYED,
    )
    employer_name = models.CharField("Employer Name", max_length=200, blank=True)
    employer_contact = models.CharField("Employer Contact", max_length=15, blank=True)
    employer_email = models.EmailField("Employer Email", blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    employment_date = models.DateField("Date of Employment", null=True, blank=True)

    # Financial Information
    existing_loans = models.DecimalField(
        "Existing Loan Obligations",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    bank_name = models.CharField("Bank Name", max_length=100, blank=True)
    bank_account = models.CharField("Bank Account Number", max_length=50, blank=True)

    # KYC Status
    kyc_verified = models.BooleanField("KYC Verified", default=False)
    kyc_verified_at = models.DateTimeField("KYC Verified At", null=True, blank=True)
    kyc_verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_customers",
    )

    # KYC Documents
    national_id_file = models.FileField(
        "National ID Document",
        upload_to="kyc_documents/national_id/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    bank_statement_file = models.FileField(
        "Bank Statement",
        upload_to="kyc_documents/bank_statements/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    face_recognition_photo = models.FileField(
        "Face Recognition Photo",
        upload_to="kyc_documents/face_photos/%Y/%m/%d/",
        null=True,
        blank=True,
    )

    # Document Verification Status
    national_id_verified = models.BooleanField("National ID Verified", default=False)
    bank_statement_verified = models.BooleanField(
        "Bank Statement Verified", default=False
    )
    face_recognition_verified = models.BooleanField(
        "Face Recognition Verified", default=False
    )

    # Face Recognition Data
    face_encoding_data = models.TextField("Face Encoding Data", null=True, blank=True)
    face_scan_date = models.DateTimeField("Face Scan Date", null=True, blank=True)

    # Status
    is_blacklisted = models.BooleanField("Blacklisted", default=False)
    blacklist_reason = models.TextField("Blacklist Reason", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "customers"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kyc_verified", "-created_at"]),
            models.Index(fields=["is_blacklisted"]),
            models.Index(fields=["id_number"]),
            models.Index(
                fields=[
                    "national_id_verified",
                    "bank_statement_verified",
                    "face_recognition_verified",
                ]
            ),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.id_number or 'No ID'}"

    @property
    def total_applications(self):
        """Calculate total number of loan applications for this customer"""
        return self.loan_applications.count()

    @property
    def last_application_date(self):
        """Get the date of the last loan application"""
        last_app = self.loan_applications.order_by("-created_at").first()
        return last_app.created_at if last_app else None

    @property
    def active_loans_count(self):
        """Get count of active loans"""
        return self.loans.filter(status="ACTIVE").count()

    @property
    def total_loans_borrowed(self):
        """Get total amount borrowed across all loans"""
        from django.db.models import Sum

        total = self.loans.aggregate(total=Sum("principal_amount"))["total"]
        return total or Decimal("0")

    def get_age(self):
        """Calculate customer age"""
        if self.date_of_birth:
            today = timezone.now().date()
            return (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
        return None

    def get_total_active_loans(self):
        """Get total outstanding balance on active loans"""
        from django.db.models import Sum

        total = self.loans.filter(status="ACTIVE").aggregate(
            total=Sum("outstanding_balance")
        )["total"]
        return total or Decimal("0")

    def get_kyc_completion_percentage(self):
        """Calculate KYC completion percentage across all 8 required fields."""
        fields = [
            bool(self.id_number),
            bool(self.date_of_birth),
            bool(self.address),
            bool(self.monthly_income),
            bool(self.employer_name),
            bool(self.national_id_file),
            bool(self.bank_statement_file),
            bool(self.face_recognition_photo),
        ]
        completed = sum(fields)
        total = len(fields)
        return round((completed / total) * 100) if total > 0 else 0

    def is_kyc_fully_uploaded(self):
        """Check if all KYC documents are uploaded"""
        return all(
            [
                self.national_id_file,
                self.bank_statement_file,
                self.face_recognition_photo,
            ]
        )

    def is_kyc_fully_verified(self):
        """Check if all KYC documents are verified"""
        return all(
            [
                self.national_id_verified,
                self.bank_statement_verified,
                self.face_recognition_verified,
            ]
        )


class CreditScore(models.Model):
    """
    Credit Score Model - SRS 3.1.3
    Automated credit evaluation engine
    """

    # Score Categories
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"

    RECOMMENDATION_CHOICES = [
        (APPROVED, "Approved"),
        (CONDITIONAL, "Conditional Approval"),
        (REJECTED, "Rejected"),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="credit_scores"
    )
    loan_application = models.OneToOneField(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="credit_score",
        null=True,
        blank=True,
    )

    # Scoring Parameters (each out of specific points)
    income_score = models.DecimalField(
        "Income Score", max_digits=5, decimal_places=2, default=0
    )
    employment_score = models.DecimalField(
        "Employment Score", max_digits=5, decimal_places=2, default=0
    )
    credit_history_score = models.DecimalField(
        "Credit History Score", max_digits=5, decimal_places=2, default=0
    )
    existing_obligations_score = models.DecimalField(
        "Existing Obligations Score", max_digits=5, decimal_places=2, default=0
    )
    age_score = models.DecimalField(
        "Age Score", max_digits=5, decimal_places=2, default=0
    )

    # Total Score (0-100)
    total_score = models.DecimalField(
        "Total Score",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # Recommendation
    recommendation = models.CharField(
        "Recommendation", max_length=15, choices=RECOMMENDATION_CHOICES
    )

    # Override Capability (SRS requirement)
    is_overridden = models.BooleanField("Score Overridden", default=False)
    override_reason = models.TextField("Override Justification", blank=True)
    overridden_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="score_overrides",
    )
    overridden_at = models.DateTimeField("Overridden At", null=True, blank=True)

    # Calculation Details
    calculation_details = models.JSONField(
        "Calculation Details", default=dict, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "credit_scores"
        verbose_name = "Credit Score"
        verbose_name_plural = "Credit Scores"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["recommendation"]),
            models.Index(fields=["is_overridden"]),
        ]

    def __str__(self):
        return f"{self.customer} - Score: {self.total_score} ({self.recommendation})"


class LoanApplication(models.Model):
    """
    Loan Application Model - SRS 3.1.2
    Manages 9-stage loan application workflow
    """

    # Application Status - 9 Stages per SRS
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CREDIT_ANALYSIS = "CREDIT_ANALYSIS"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EMPLOYER_VERIFICATION = "EMPLOYER_VERIFICATION"
    GUARANTOR_CONFIRMATION = "GUARANTOR_CONFIRMATION"
    DISBURSED = "DISBURSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    APPLICATION_STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (UNDER_REVIEW, "Under Review"),
        (CREDIT_ANALYSIS, "Credit Analysis"),
        (PENDING_APPROVAL, "Pending Approval"),
        (APPROVED, "Approved"),
        (EMPLOYER_VERIFICATION, "Employer Verification"),
        (GUARANTOR_CONFIRMATION, "Guarantor Confirmation"),
        (DISBURSED, "Disbursed"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    ]

    # Basic Information
    application_number = models.CharField(
        "Application Number", max_length=50, unique=True, editable=False
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="loan_applications"
    )
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.PROTECT, related_name="applications"
    )

    # Loan Details
    requested_amount = models.DecimalField(
        "Requested Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    approved_amount = models.DecimalField(
        "Approved Amount",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    tenure_months = models.PositiveIntegerField("Loan Tenure (Months)")
    repayment_frequency = models.CharField(
        "Repayment Frequency", max_length=15, choices=LoanProduct.FREQUENCY_CHOICES
    )
    purpose = models.TextField("Loan Purpose")

    # Status and Workflow
    status = models.CharField(
        "Application Status",
        max_length=25,
        choices=APPLICATION_STATUS_CHOICES,
        default=DRAFT,
    )

    # Dates
    submitted_at = models.DateTimeField("Submitted At", null=True, blank=True)
    reviewed_at = models.DateTimeField("Reviewed At", null=True, blank=True)
    approved_at = models.DateTimeField("Approved At", null=True, blank=True)
    disbursed_at = models.DateTimeField("Disbursed At", null=True, blank=True)
    rejected_at = models.DateTimeField("Rejected At", null=True, blank=True)

    # Approval/Rejection
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_applications",
    )
    rejection_reason = models.TextField("Rejection Reason", blank=True)

    # Notes
    internal_notes = models.TextField("Internal Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "loan_applications"
        verbose_name = "Loan Application"
        verbose_name_plural = "Loan Applications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["application_number"]),
            models.Index(fields=["loan_product", "status"]),
        ]

    def __str__(self):
        return f"{self.application_number} - {self.customer.user.get_full_name()}"

    def save(self, *args, **kwargs):
        """Generate application number on creation"""
        if not self.application_number:
            # Generate unique application number: LA-YYYYMMDD-XXXX
            from django.utils import timezone

            date_str = timezone.now().strftime("%Y%m%d")
            last_app = (
                LoanApplication.objects.filter(
                    application_number__startswith=f"LA-{date_str}"
                )
                .order_by("-application_number")
                .first()
            )

            if last_app:
                last_number = int(last_app.application_number.split("-")[-1])
                new_number = last_number + 1
            else:
                new_number = 1

            self.application_number = f"LA-{date_str}-{new_number:04d}"

        super().save(*args, **kwargs)

    def can_transition_to(self, new_status):
        """Validate status transitions"""
        valid_transitions = {
            self.DRAFT: [self.SUBMITTED, self.CANCELLED],
            self.SUBMITTED: [self.UNDER_REVIEW, self.CANCELLED],
            self.UNDER_REVIEW: [self.CREDIT_ANALYSIS, self.REJECTED],
            self.CREDIT_ANALYSIS: [self.PENDING_APPROVAL, self.REJECTED],
            self.PENDING_APPROVAL: [self.APPROVED, self.REJECTED],
            self.APPROVED: [self.EMPLOYER_VERIFICATION, self.DISBURSED],
            self.EMPLOYER_VERIFICATION: [
                self.GUARANTOR_CONFIRMATION,
                self.DISBURSED,
                self.REJECTED,
            ],
            self.GUARANTOR_CONFIRMATION: [self.DISBURSED, self.REJECTED],
        }

        return new_status in valid_transitions.get(self.status, [])


class Loan(models.Model):
    """
    Active Loan Model
    Created when loan application is disbursed
    """

    # Loan Status
    ACTIVE = "ACTIVE"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    DEFAULTED = "DEFAULTED"
    WRITTEN_OFF = "WRITTEN_OFF"
    RESTRUCTURED = "RESTRUCTURED"

    LOAN_STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PAID, "Fully Paid"),
        (OVERDUE, "Overdue"),
        (DEFAULTED, "Defaulted"),
        (WRITTEN_OFF, "Written Off"),
        (RESTRUCTURED, "Restructured"),
    ]

    # Basic Information
    loan_number = models.CharField(
        "Loan Number", max_length=50, unique=True, editable=False
    )
    application = models.OneToOneField(
        LoanApplication, on_delete=models.PROTECT, related_name="disbursed_loan"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="loans"
    )
    loan_product = models.ForeignKey(
        LoanProduct, on_delete=models.PROTECT, related_name="active_loans"
    )

    # Loan Amount Breakdown
    principal_amount = models.DecimalField(
        "Principal Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    interest_amount = models.DecimalField(
        "Total Interest",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    fees = models.DecimalField(
        "Total Fees",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_amount = models.DecimalField(
        "Total Amount Payable",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    outstanding_balance = models.DecimalField(
        "Outstanding Balance",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Repayment Details
    installment_amount = models.DecimalField(
        "Installment Amount",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    repayment_frequency = models.CharField(
        "Repayment Frequency", max_length=15, choices=LoanProduct.FREQUENCY_CHOICES
    )
    tenure_months = models.PositiveIntegerField("Tenure (Months)")

    # Dates
    disbursement_date = models.DateField("Disbursement Date")
    first_payment_date = models.DateField("First Payment Date")
    maturity_date = models.DateField("Maturity Date")
    next_payment_date = models.DateField("Next Payment Date", null=True, blank=True)
    last_payment_date = models.DateField("Last Payment Date", null=True, blank=True)

    # Status
    status = models.CharField(
        "Loan Status", max_length=15, choices=LOAN_STATUS_CHOICES, default=ACTIVE
    )
    days_overdue = models.PositiveIntegerField("Days Overdue", default=0)

    # Penalties
    penalty_charged = models.DecimalField(
        "Total Penalties Charged",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Disbursement Details
    disbursed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="disbursed_loans"
    )
    disbursement_method = models.CharField(
        "Disbursement Method",
        max_length=50,
        blank=True,
        help_text="e.g., Bank Transfer, M-Pesa, Cheque",
    )
    disbursement_reference = models.CharField(
        "Disbursement Reference", max_length=100, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "loans"
        verbose_name = "Loan"
        verbose_name_plural = "Loans"
        ordering = ["-disbursement_date"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "-disbursement_date"]),
            models.Index(fields=["loan_number"]),
            models.Index(fields=["next_payment_date"]),
        ]

    def __str__(self):
        return f"{self.loan_number} - {self.customer.user.get_full_name()}"

    def save(self, *args, **kwargs):
        """Generate loan number on creation"""
        if not self.loan_number:
            from django.utils import timezone

            date_str = timezone.now().strftime("%Y%m%d")
            last_loan = (
                Loan.objects.filter(loan_number__startswith=f"LN-{date_str}")
                .order_by("-loan_number")
                .first()
            )

            if last_loan:
                last_number = int(last_loan.loan_number.split("-")[-1])
                new_number = last_number + 1
            else:
                new_number = 1

            self.loan_number = f"LN-{date_str}-{new_number:04d}"

        super().save(*args, **kwargs)

    def get_payment_progress_percentage(self):
        """Calculate payment progress"""
        if self.total_amount > 0:
            paid = self.total_amount - self.outstanding_balance
            return (paid / self.total_amount) * 100
        return 0


class LoanRepayment(models.Model):
    """
    Loan Repayment Tracking Model
    Records all payments made against loans
    """

    # Payment Type
    REGULAR_PAYMENT = "REGULAR_PAYMENT"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    FULL_SETTLEMENT = "FULL_SETTLEMENT"
    PENALTY_PAYMENT = "PENALTY_PAYMENT"

    PAYMENT_TYPE_CHOICES = [
        (REGULAR_PAYMENT, "Regular Payment"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (FULL_SETTLEMENT, "Full Settlement"),
        (PENALTY_PAYMENT, "Penalty Payment"),
    ]

    # Payment Method
    BANK_TRANSFER = "BANK_TRANSFER"
    M_PESA = "M_PESA"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    DIRECT_DEBIT = "DIRECT_DEBIT"

    PAYMENT_METHOD_CHOICES = [
        (BANK_TRANSFER, "Bank Transfer"),
        (M_PESA, "M-Pesa"),
        (CASH, "Cash"),
        (CHEQUE, "Cheque"),
        (DIRECT_DEBIT, "Direct Debit"),
    ]

    # Basic Information
    receipt_number = models.CharField(
        "Receipt Number", max_length=50, unique=True, editable=False
    )
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="repayments")

    # Payment Details
    payment_date = models.DateField("Payment Date")
    amount = models.DecimalField(
        "Amount Paid",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_type = models.CharField(
        "Payment Type",
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default=REGULAR_PAYMENT,
    )
    payment_method = models.CharField(
        "Payment Method", max_length=20, choices=PAYMENT_METHOD_CHOICES
    )
    reference_number = models.CharField(
        "Reference Number",
        max_length=100,
        blank=True,
        help_text="Transaction reference from payment provider",
    )

    # Allocation Breakdown
    principal_paid = models.DecimalField(
        "Principal Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    interest_paid = models.DecimalField(
        "Interest Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    penalty_paid = models.DecimalField(
        "Penalty Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Processing
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="processed_repayments"
    )
    notes = models.TextField("Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "loan_repayments"
        verbose_name = "Loan Repayment"
        verbose_name_plural = "Loan Repayments"
        ordering = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(fields=["loan", "-payment_date"]),
            models.Index(fields=["receipt_number"]),
            models.Index(fields=["payment_date"]),
        ]

    def __str__(self):
        return f"{self.receipt_number} - {self.loan.loan_number} - KES {self.amount}"

    def save(self, *args, **kwargs):
        """Generate receipt number on creation"""
        if not self.receipt_number:
            from django.utils import timezone

            date_str = timezone.now().strftime("%Y%m%d")
            last_receipt = (
                LoanRepayment.objects.filter(
                    receipt_number__startswith=f"RCP-{date_str}"
                )
                .order_by("-receipt_number")
                .first()
            )

            if last_receipt:
                last_number = int(last_receipt.receipt_number.split("-")[-1])
                new_number = last_number + 1
            else:
                new_number = 1

            self.receipt_number = f"RCP-{date_str}-{new_number:04d}"

        super().save(*args, **kwargs)


class EmployerVerification(models.Model):
    """
    Employer Verification Model - SRS 3.1.4
    Third-party validation of employment details
    """

    # Verification Status
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    WAIVED = "WAIVED"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (VERIFIED, "Verified"),
        (FAILED, "Failed"),
        (WAIVED, "Waived"),
    ]

    application = models.OneToOneField(
        LoanApplication, on_delete=models.CASCADE, related_name="employer_verification"
    )

    # Employer Details
    employer_name = models.CharField("Employer Name", max_length=200)
    contact_person = models.CharField("Contact Person", max_length=100, blank=True)
    contact_email = models.EmailField("Contact Email", blank=True)
    contact_phone = models.CharField("Contact Phone", max_length=15, blank=True)

    # Verification Details
    employment_confirmed = models.BooleanField("Employment Confirmed", default=False)
    income_confirmed = models.BooleanField("Stated Income Confirmed", default=False)
    verified_income = models.DecimalField(
        "Verified Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Status
    status = models.CharField(
        "Verification Status", max_length=10, choices=STATUS_CHOICES, default=PENDING
    )

    # Verification Process
    sent_at = models.DateTimeField(
        "Verification Request Sent At", null=True, blank=True
    )
    verified_at = models.DateTimeField("Verified At", null=True, blank=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employer_verifications",
    )

    # Notes
    verification_notes = models.TextField("Verification Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "employer_verifications"
        verbose_name = "Employer Verification"
        verbose_name_plural = "Employer Verifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["application"]),
        ]

    def __str__(self):
        return f"Employer Verification - {self.application.application_number} - {self.status}"


class GuarantorVerification(models.Model):
    """
    Guarantor Verification Model - SRS 3.1.4
    Third-party guarantor confirmation
    """

    # Verification Status
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    WAIVED = "WAIVED"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
        (DECLINED, "Declined"),
        (WAIVED, "Waived"),
    ]

    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name="guarantors"
    )

    # Guarantor Details
    full_name = models.CharField("Full Name", max_length=200)
    id_number = models.CharField("ID/Passport Number", max_length=50)
    phone = models.CharField("Phone Number", max_length=15)
    email = models.EmailField("Email", blank=True)
    relationship = models.CharField(
        "Relationship to Applicant",
        max_length=100,
        help_text="e.g., Friend, Colleague, Relative",
    )

    # Financial Information
    employer = models.CharField("Employer", max_length=200, blank=True)
    monthly_income = models.DecimalField(
        "Monthly Income",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Verification
    status = models.CharField(
        "Status", max_length=10, choices=STATUS_CHOICES, default=PENDING
    )
    confirmation_code = models.CharField(
        "Confirmation Code", max_length=10, unique=True, editable=False, blank=True
    )
    sent_at = models.DateTimeField(
        "Confirmation Request Sent At", null=True, blank=True
    )
    confirmed_at = models.DateTimeField("Confirmed At", null=True, blank=True)

    # Notes
    guarantor_notes = models.TextField("Guarantor Notes", blank=True)
    internal_notes = models.TextField("Internal Notes", blank=True)

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "guarantor_verifications"
        verbose_name = "Guarantor Verification"
        verbose_name_plural = "Guarantor Verifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["application", "status"]),
            models.Index(fields=["confirmation_code"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"Guarantor: {self.full_name} for {self.application.application_number}"

    def save(self, *args, **kwargs):
        """Generate confirmation code on creation"""
        if not self.confirmation_code:
            import random
            import string

            self.confirmation_code = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=8)
            )
        super().save(*args, **kwargs)


class RepaymentSchedule(models.Model):
    """
    Repayment Schedule Model
    Generated at disbursement; each row is one expected installment.
    Odoo will update is_paid / paid_date when payments are recorded.
    """

    loan = models.ForeignKey("Loan", on_delete=models.CASCADE, related_name="schedule")
    installment_number = models.PositiveIntegerField("Installment #")
    due_date = models.DateField("Due Date")

    # Amounts expected for this installment
    principal_due = models.DecimalField(
        "Principal Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    interest_due = models.DecimalField(
        "Interest Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    fees_due = models.DecimalField(
        "Fees Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    penalty_due = models.DecimalField(
        "Penalty Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_due = models.DecimalField(
        "Total Due",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Payment state
    amount_paid = models.DecimalField(
        "Amount Paid",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_paid = models.BooleanField("Paid", default=False)
    paid_date = models.DateField("Date Paid", null=True, blank=True)

    # Outstanding on this row
    balance = models.DecimalField(
        "Balance", max_digits=12, decimal_places=2, default=Decimal("0")
    )

    # Odoo sync
    odoo_id = models.CharField(
        "Odoo Record ID",
        max_length=50,
        blank=True,
        help_text="ID of the corresponding record in Odoo",
    )

    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        db_table = "repayment_schedule"
        verbose_name = "Repayment Schedule"
        verbose_name_plural = "Repayment Schedules"
        ordering = ["loan", "installment_number"]
        unique_together = [["loan", "installment_number"]]
        indexes = [
            models.Index(fields=["loan", "due_date"]),
            models.Index(fields=["is_paid", "due_date"]),
        ]

    def __str__(self):
        return (
            f"{self.loan.loan_number} — Installment {self.installment_number} "
            f"(Due: {self.due_date})"
        )

    def save(self, *args, **kwargs):
        """Keep balance in sync"""
        self.balance = self.total_due - self.amount_paid
        if self.balance < Decimal("0"):
            self.balance = Decimal("0")
        super().save(*args, **kwargs)


class Notification(models.Model):
    """
    In-portal notification model — SRS Section 3.5 (push notifications & in-portal alerts)
    Notifications are created by the system or pushed from Odoo via webhook.
    """

    # Notification Types
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_UNDER_REVIEW = "APPLICATION_UNDER_REVIEW"
    APPLICATION_APPROVED = "APPLICATION_APPROVED"
    APPLICATION_REJECTED = "APPLICATION_REJECTED"
    LOAN_DISBURSED = "LOAN_DISBURSED"
    PAYMENT_DUE = "PAYMENT_DUE"
    PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    KYC_VERIFIED = "KYC_VERIFIED"
    KYC_REJECTED = "KYC_REJECTED"
    ACCOUNT_APPROVED = "ACCOUNT_APPROVED"
    GENERAL = "GENERAL"

    NOTIFICATION_TYPE_CHOICES = [
        (APPLICATION_SUBMITTED, "Application Submitted"),
        (APPLICATION_UNDER_REVIEW, "Application Under Review"),
        (APPLICATION_APPROVED, "Application Approved"),
        (APPLICATION_REJECTED, "Application Rejected"),
        (LOAN_DISBURSED, "Loan Disbursed"),
        (PAYMENT_DUE, "Payment Due"),
        (PAYMENT_OVERDUE, "Payment Overdue"),
        (PAYMENT_RECEIVED, "Payment Received"),
        (KYC_VERIFIED, "KYC Verified"),
        (KYC_REJECTED, "KYC Rejected"),
        (ACCOUNT_APPROVED, "Account Approved"),
        (GENERAL, "General"),
    ]

    # Priority
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    PRIORITY_CHOICES = [
        (LOW, "Low"),
        (MEDIUM, "Medium"),
        (HIGH, "High"),
        (CRITICAL, "Critical"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        "Type", max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default=GENERAL
    )
    priority = models.CharField(
        "Priority", max_length=10, choices=PRIORITY_CHOICES, default=MEDIUM
    )
    title = models.CharField("Title", max_length=200)
    message = models.TextField("Message")

    # Optional links to related objects
    loan_application = models.ForeignKey(
        "LoanApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    loan = models.ForeignKey(
        "Loan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # State
    is_read = models.BooleanField("Read", default=False)
    read_at = models.DateTimeField("Read At", null=True, blank=True)

    # Source — helpful for Odoo-pushed notifications
    source = models.CharField(
        "Source",
        max_length=20,
        choices=[("SYSTEM", "System"), ("ODOO", "Odoo")],
        default="SYSTEM",
    )

    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "notification_type"]),
        ]

    def __str__(self):
        return (
            f"{self.user.email} — {self.title} ({'Read' if self.is_read else 'Unread'})"
        )

    def mark_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    @classmethod
    def create_for_user(
        cls,
        user,
        notification_type,
        title,
        message,
        priority=None,
        loan_application=None,
        loan=None,
        source="SYSTEM",
    ):
        """Convenience factory used across the codebase"""
        return cls.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority or cls.MEDIUM,
            loan_application=loan_application,
            loan=loan,
            source=source,
        )


class LoanDocument(models.Model):
    """
    Loan Document Model
    Manages uploaded documents for loan applications
    """

    # Document Types
    ID_CARD = "ID_CARD"
    PAYSLIP = "PAYSLIP"
    BANK_STATEMENT = "BANK_STATEMENT"
    EMPLOYMENT_LETTER = "EMPLOYMENT_LETTER"
    GUARANTOR_ID = "GUARANTOR_ID"
    OTHER = "OTHER"

    DOCUMENT_TYPE_CHOICES = [
        (ID_CARD, "ID Card/Passport"),
        (PAYSLIP, "Payslip"),
        (BANK_STATEMENT, "Bank Statement"),
        (EMPLOYMENT_LETTER, "Employment Letter"),
        (GUARANTOR_ID, "Guarantor ID"),
        (OTHER, "Other"),
    ]

    application = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(
        "Document Type", max_length=20, choices=DOCUMENT_TYPE_CHOICES
    )
    document_file = models.FileField(
        "Document File", upload_to="loan_documents/%Y/%m/%d/"
    )
    description = models.CharField("Description", max_length=200, blank=True)

    # Validation
    is_validated = models.BooleanField("Validated", default=False)
    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_documents",
    )
    validated_at = models.DateTimeField("Validated At", null=True, blank=True)

    # Upload Details
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="uploaded_documents"
    )

    # Timestamps
    created_at = models.DateTimeField("Created At", auto_now_add=True)

    class Meta:
        db_table = "loan_documents"
        verbose_name = "Loan Document"
        verbose_name_plural = "Loan Documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["application", "document_type"]),
            models.Index(fields=["is_validated"]),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.application.application_number}"
