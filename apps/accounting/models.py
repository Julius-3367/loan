"""
Accounting Models: Chart of Accounts, Journal Entries, Financial Reports
Implements double-entry bookkeeping with audit trail
"""
from decimal import Decimal
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.models import User


class FiscalYear(models.Model):
    """
    Fiscal Year configuration
    """
    name = models.CharField(max_length=50, unique=True)  # e.g., "FY 2026"
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_fiscal_years')
    
    class Meta:
        db_table = 'accounting_fiscal_years'
        verbose_name = 'Fiscal Year'
        verbose_name_plural = 'Fiscal Years'
        ordering = ['-start_date']
    
    def __str__(self):
        return self.name
    
    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError('Start date must be before end date')


class AccountType(models.Model):
    """
    Chart of Accounts - Account Types
    Defines the five fundamental account types in double-entry bookkeeping
    
    Balance Sheet:
    - Asset: Resources owned (Normal Balance: Debit)
    - Liability: Obligations owed (Normal Balance: Credit)
    - Equity: Owner's interest (Normal Balance: Credit)
    
    Income Statement:
    - Income/Revenue: Earnings (Normal Balance: Credit)
    - Expense: Costs (Normal Balance: Debit)
    """
    # Account type constants
    ASSET = 'ASSET'
    LIABILITY = 'LIABILITY'
    EQUITY = 'EQUITY'
    INCOME = 'INCOME'
    EXPENSE = 'EXPENSE'
    
    TYPE_CHOICES = [
        (ASSET, 'Asset'),
        (LIABILITY, 'Liability'),
        (EQUITY, 'Equity'),
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]
    
    NORMAL_BALANCE_CHOICES = [
        ('DEBIT', 'Debit'),
        ('CREDIT', 'Credit'),
    ]
    
    # Fields
    name = models.CharField(
        max_length=50,
        unique=True,
        choices=TYPE_CHOICES,
        db_index=True,
        help_text='Account type classification'
    )
    description = models.TextField(
        blank=True,
        help_text='Detailed description of this account type'
    )
    normal_balance = models.CharField(
        max_length=10,
        choices=NORMAL_BALANCE_CHOICES,
        db_index=True,
        help_text='Normal balance side for this account type'
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounting_account_types'
        verbose_name = 'Account Type'
        verbose_name_plural = 'Account Types'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['normal_balance']),
        ]
    
    def __str__(self):
        return self.get_name_display()
    
    def clean(self):
        """Validate account type configuration"""
        # Validate normal balance based on account type
        if self.name in [self.ASSET, self.EXPENSE]:
            if self.normal_balance != 'DEBIT':
                raise ValidationError(
                    f"{self.get_name_display()} accounts must have a DEBIT normal balance"
                )
        elif self.name in [self.LIABILITY, self.EQUITY, self.INCOME]:
            if self.normal_balance != 'CREDIT':
                raise ValidationError(
                    f"{self.get_name_display()} accounts must have a CREDIT normal balance"
                )


class Account(models.Model):
    """
    Chart of Accounts
    Hierarchical account structure for double-entry bookkeeping
    
    Represents individual accounts in the general ledger. Supports hierarchical
    structure through parent_account relationship.
    
    Examples:
        - 1000: Assets (parent)
        - 1100: Current Assets (parent: 1000)
        - 1110: Cash (parent: 1100)
    """
    code = models.CharField(
        max_length=20, 
        unique=True, 
        db_index=True,
        help_text="Unique account code (e.g., 1000, 2100, 4050)"
    )
    name = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Account name (e.g., 'Cash', 'Accounts Receivable')"
    )
    account_type = models.ForeignKey(
        AccountType, 
        on_delete=models.PROTECT, 
        related_name='accounts',
        help_text="Type of account (Asset, Liability, etc.)"
    )
    parent_account = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sub_accounts',
        help_text="Parent account for hierarchical structure"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of account purpose"
    )
    
    # Account properties
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this account is currently active"
    )
    is_system_account = models.BooleanField(
        default=False,
        help_text="System accounts cannot be deleted"
    )
    allow_manual_entries = models.BooleanField(
        default=True,
        help_text="Whether manual journal entries are allowed"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_accounts'
    )
    
    class Meta:
        db_table = 'accounting_accounts'
        verbose_name = 'Account'
        verbose_name_plural = 'Chart of Accounts'
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['account_type', 'is_active']),
            models.Index(fields=['parent_account']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def clean(self):
        """Validate account configuration"""
        super().clean()
        
        # Validate code format (alphanumeric only)
        if not self.code.replace('-', '').replace('_', '').isalnum():
            raise ValidationError({
                'code': 'Account code must contain only alphanumeric characters, hyphens, and underscores'
            })
        
        # Validate parent account type matches
        if self.parent_account:
            if self.parent_account.account_type != self.account_type:
                raise ValidationError({
                    'parent_account': f'Parent account must be of the same type ({self.account_type.get_name_display()})'
                })
            
            # Prevent circular references
            if self.pk and self._is_circular_reference(self.parent_account):
                raise ValidationError({
                    'parent_account': 'Circular reference detected in account hierarchy'
                })
        
        # Validate system accounts
        if self.pk and self.is_system_account:
            # Check if trying to deactivate a system account
            old_instance = Account.objects.get(pk=self.pk)
            if old_instance.is_active and not self.is_active:
                raise ValidationError({
                    'is_active': 'System accounts cannot be deactivated'
                })
    
    def _is_circular_reference(self, parent):
        """Check for circular references in parent hierarchy"""
        current = parent
        max_depth = 100  # Prevent infinite loops
        depth = 0
        
        while current and depth < max_depth:
            if current.pk == self.pk:
                return True
            current = current.parent_account
            depth += 1
        
        return False
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_balance(self, as_of_date=None):
        """
        Calculate account balance as of a specific date
        Uses normal balance convention:
        - Asset/Expense: Debit increases, Credit decreases
        - Liability/Equity/Revenue: Credit increases, Debit decreases
        """
        entries = self.journal_entry_lines.filter(
            journal_entry__status='POSTED'
        )
        
        if as_of_date:
            entries = entries.filter(journal_entry__date__lte=as_of_date)
        
        total_debit = entries.aggregate(
            total=models.Sum('debit_amount')
        )['total'] or Decimal('0.00')
        
        total_credit = entries.aggregate(
            total=models.Sum('credit_amount')
        )['total'] or Decimal('0.00')
        
        # Calculate balance based on normal balance type
        if self.account_type.normal_balance == 'DEBIT':
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    def get_full_path(self):
        """Get full account path for display"""
        if self.parent_account:
            return f"{self.parent_account.get_full_path()} > {self.name}"
        return self.name


class JournalEntry(models.Model):
    """
    Journal Entry Header
    Double-entry bookkeeping transactions
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
        ('REVERSED', 'Reversed'),
    ]
    
    entry_number = models.CharField(max_length=50, unique=True, db_index=True)
    date = models.DateField(db_index=True)
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name='journal_entries')
    
    # Transaction details
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True)  # External reference
    
    # Source tracking
    source_module = models.CharField(max_length=50, blank=True)  # e.g., 'loans', 'payroll'
    source_document = models.CharField(max_length=50, blank=True)  # e.g., 'LOAN-001'
    
    # Status and approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    is_auto_generated = models.BooleanField(default=False)
    
    # Reversal tracking
    reversed_entry = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversing_entries'
    )
    reversal_reason = models.TextField(blank=True)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_journal_entries'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_journal_entries'
    )
    
    class Meta:
        db_table = 'accounting_journal_entries'
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        ordering = ['-date', '-entry_number']
        indexes = [
            models.Index(fields=['-date', 'status']),
            models.Index(fields=['source_module', 'source_document']),
        ]
        permissions = [
            ('can_post_journal_entries', 'Can post journal entries'),
            ('can_reverse_journal_entries', 'Can reverse journal entries'),
        ]
    
    def __str__(self):
        return f"{self.entry_number} - {self.date} - {self.description}"
    
    def clean(self):
        """Validate journal entry before saving"""
        super().clean()
        
        # Validate fiscal year is active and not closed
        if self.fiscal_year and self.fiscal_year.is_closed:
            raise ValidationError({
                'fiscal_year': 'Cannot create or modify entries in a closed fiscal year'
            })
        
        # Validate date is within fiscal year
        if self.fiscal_year and self.date:
            if not (self.fiscal_year.start_date <= self.date <= self.fiscal_year.end_date):
                raise ValidationError({
                    'date': f'Date must be within fiscal year {self.fiscal_year.name} '
                            f'({self.fiscal_year.start_date} to {self.fiscal_year.end_date})'
                })
        
        # Validate posted entries are balanced
        if self.status == 'POSTED':
            if not self.is_balanced():
                raise ValidationError('Journal entry must be balanced before posting')
            
            # Validate has lines
            if not self.lines.exists():
                raise ValidationError('Journal entry must have at least one line before posting')
    
    def is_balanced(self):
        """
        Check if debits equal credits
        This is critical for double-entry accounting integrity
        """
        total_debits = self.lines.aggregate(
            total=models.Sum('debit_amount')
        )['total'] or Decimal('0.00')
        
        total_credits = self.lines.aggregate(
            total=models.Sum('credit_amount')
        )['total'] or Decimal('0.00')
        
        return total_debits == total_credits
    
    def get_total_debit(self):
        """Get total debit amount"""
        return self.lines.aggregate(
            total=models.Sum('debit_amount')
        )['total'] or Decimal('0.00')
    
    def get_total_credit(self):
        """Get total credit amount"""
        return self.lines.aggregate(
            total=models.Sum('credit_amount')
        )['total'] or Decimal('0.00')
    
    def get_difference(self):
        """Get difference between debits and credits (should be 0 when balanced)"""
        return self.get_total_debit() - self.get_total_credit()
    
    @transaction.atomic
    def post(self, user):
        """
        Post journal entry with database transaction protection
        
        Args:
            user: User posting the entry
            
        Raises:
            ValidationError: If entry is already posted, unbalanced, or has no lines
        """
        if self.status == 'POSTED':
            raise ValidationError('Journal entry is already posted')
        
        if self.status == 'REVERSED':
            raise ValidationError('Cannot post a reversed entry')
        
        if not self.lines.exists():
            raise ValidationError('Cannot post journal entry with no lines')
        
        if not self.is_balanced():
            debit_total = self.get_total_debit()
            credit_total = self.get_total_credit()
            difference = debit_total - credit_total
            raise ValidationError(
                f'Cannot post unbalanced journal entry. '
                f'Debits: {debit_total}, Credits: {credit_total}, Difference: {difference}'
            )
        
        # Validate fiscal year is not closed
        if self.fiscal_year.is_closed:
            raise ValidationError('Cannot post entries to a closed fiscal year')
        
        # Validate all accounts allow manual entries if not auto-generated
        if not self.is_auto_generated:
            for line in self.lines.all():
                if not line.account.allow_manual_entries:
                    raise ValidationError(
                        f'Account {line.account.code} - {line.account.name} does not allow manual entries'
                    )
        
        # Post the entry
        self.status = 'POSTED'
        self.posted_at = timezone.now()
        self.posted_by = user
        self.save()
    
    @transaction.atomic
    def reverse(self, user, reason):
        """
        Reverse a posted journal entry with database transaction protection
        
        Creates a new journal entry with opposite debit/credit amounts
        
        Args:
            user: User reversing the entry
            reason: Reason for reversal
            
        Returns:
            JournalEntry: The newly created reversing entry
            
        Raises:
            ValidationError: If entry is not posted or already reversed
        """
        if self.status != 'POSTED':
            raise ValidationError('Only posted entries can be reversed')
        
        if self.status == 'REVERSED':
            raise ValidationError('Entry has already been reversed')
        
        # Validate fiscal year is not closed
        if self.fiscal_year.is_closed:
            raise ValidationError('Cannot reverse entries in a closed fiscal year')
        
        # Generate entry number for reversing entry
        reversal_number = f"{self.entry_number}-REV"
        
        # Create reversing entry
        reversing_entry = JournalEntry.objects.create(
            entry_number=reversal_number,
            date=timezone.now().date(),
            fiscal_year=self.fiscal_year,
            description=f"REVERSAL: {self.description}",
            reference=self.reference,
            source_module=self.source_module,
            source_document=self.source_document,
            reversed_entry=self,
            reversal_reason=reason,
            created_by=user,
            status='POSTED',
            posted_at=timezone.now(),
            posted_by=user,
            is_auto_generated=True,
        )
        
        # Create reversing lines (swap debits and credits)
        for line in self.lines.all():
            JournalEntryLine.objects.create(
                journal_entry=reversing_entry,
                account=line.account,
                description=f"Reversal: {line.description}",
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
                cost_center=line.cost_center,
                department=line.department,
            )
        
        # Mark original entry as reversed
        self.status = 'REVERSED'
        self.save()
        
        return reversing_entry


class JournalEntryLine(models.Model):
    """
    Journal Entry Line Items
    Individual debit/credit entries for double-entry bookkeeping
    
    Each line represents either a debit or credit to a specific account.
    The sum of all debits must equal the sum of all credits in each journal entry.
    """
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines',
        help_text="Parent journal entry"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='journal_entry_lines',
        help_text="Account to debit or credit"
    )
    description = models.CharField(
        max_length=200,
        help_text="Line item description"
    )
    
    # Amounts - one must be zero, one must be positive
    debit_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Debit amount (increases Assets/Expenses)"
    )
    credit_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Credit amount (increases Liabilities/Equity/Income)"
    )
    
    # Optional tracking dimensions
    cost_center = models.CharField(
        max_length=50, 
        blank=True,
        db_index=True,
        help_text="Cost center code for reporting"
    )
    department = models.CharField(
        max_length=50, 
        blank=True,
        db_index=True,
        help_text="Department code for reporting"
    )
    project_code = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Project code for job costing"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounting_journal_entry_lines'
        verbose_name = 'Journal Entry Line'
        verbose_name_plural = 'Journal Entry Lines'
        ordering = ['id']
        indexes = [
            models.Index(fields=['journal_entry', 'account']),
            models.Index(fields=['account', 'journal_entry']),
            models.Index(fields=['cost_center']),
            models.Index(fields=['department']),
            models.Index(fields=['project_code']),
        ]
    
    def __str__(self):
        return f"{self.account.code} - Dr: {self.debit_amount} Cr: {self.credit_amount}"
    
    def clean(self):
        """
        Validate line item rules:
        1. Cannot have both debit and credit amounts
        2. Must have at least one non-zero amount
        3. Account must be active
        4. Cannot modify line on posted entries
        """
        super().clean()
        
        # Validate only one side has an amount
        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValidationError(
                'A line cannot have both debit and credit amounts. '
                'Use separate lines for debits and credits.'
            )
        
        # Validate at least one amount is greater than zero
        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValidationError(
                'Either debit or credit amount must be greater than zero'
            )
        
        # Validate account is active
        if self.account and not self.account.is_active:
            raise ValidationError({
                'account': f'Account {self.account.code} - {self.account.name} is inactive'
            })
        
        # Prevent modification of posted entries
        if self.pk and self.journal_entry_id:
            if self.journal_entry.status == 'POSTED':
                raise ValidationError(
                    'Cannot modify lines on a posted journal entry. '
                    'Reverse the entry instead.'
                )
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_amount(self):
        """Get the non-zero amount (debit or credit)"""
        return self.debit_amount if self.debit_amount > 0 else self.credit_amount
    
    def get_side(self):
        """Get the side of the entry (DEBIT or CREDIT)"""
        return 'DEBIT' if self.debit_amount > 0 else 'CREDIT'


class Budget(models.Model):
    """
    Budget management for departments and cost centers
    """
    name = models.CharField(max_length=200)
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='budgets')
    department = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='budgets')
    
    budgeted_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('DRAFT', 'Draft'),
            ('APPROVED', 'Approved'),
            ('ACTIVE', 'Active'),
            ('CLOSED', 'Closed'),
        ],
        default='DRAFT'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_budgets')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_budgets'
    )
    
    class Meta:
        db_table = 'accounting_budgets'
        verbose_name = 'Budget'
        verbose_name_plural = 'Budgets'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.department}"
    
    def get_actual_amount(self):
        """Get actual expenses against this budget"""
        return self.account.journal_entry_lines.filter(
            journal_entry__status='POSTED',
            journal_entry__fiscal_year=self.fiscal_year,
            department=self.department
        ).aggregate(
            total=models.Sum('debit_amount') - models.Sum('credit_amount')
        )['total'] or Decimal('0.00')
    
    def get_variance(self):
        """Get budget variance"""
        return self.budgeted_amount - self.get_actual_amount()
    
    def get_utilization_percentage(self):
        """Get budget utilization percentage"""
        actual = self.get_actual_amount()
        if self.budgeted_amount == 0:
            return Decimal('0.00')
        return (actual / self.budgeted_amount) * 100


class BankAccount(models.Model):
    """
    Bank Account Management
    """
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50, unique=True)
    bank_name = models.CharField(max_length=200)
    branch = models.CharField(max_length=200)
    currency = models.CharField(max_length=10, default='KES')
    
    # Link to GL account
    gl_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='bank_accounts'
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        db_table = 'accounting_bank_accounts'
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'
    
    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"
    
    def get_balance(self):
        """Get current bank account balance from GL"""
        return self.gl_account.get_balance()


class BankReconciliation(models.Model):
    """
    Bank Reconciliation Management
    """
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='reconciliations')
    reconciliation_date = models.DateField()
    statement_balance = models.DecimalField(max_digits=20, decimal_places=2)
    book_balance = models.DecimalField(max_digits=20, decimal_places=2)
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('IN_PROGRESS', 'In Progress'),
            ('COMPLETED', 'Completed'),
        ],
        default='IN_PROGRESS'
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_reconciliations')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='completed_reconciliations'
    )
    
    class Meta:
        db_table = 'accounting_bank_reconciliations'
        verbose_name = 'Bank Reconciliation'
        verbose_name_plural = 'Bank Reconciliations'
        ordering = ['-reconciliation_date']
    
    def __str__(self):
        return f"{self.bank_account} - {self.reconciliation_date}"
    
    def get_variance(self):
        """Get reconciliation variance"""
        return self.statement_balance - self.book_balance


# =============================================================================
# ADVANCED COST ACCOUNTING MODELS
# =============================================================================

class CostCenter(models.Model):
    """
    Cost Center / Department / Branch / Division
    Enables departmental profitability analysis and budget tracking
    
    Supports hierarchical structure (e.g., Sales → East Region → Nairobi Branch)
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text='Unique cost center code (e.g., CC-SALES-001)'
    )
    name = models.CharField(
        max_length=200,
        help_text='Cost center name (e.g., Nairobi Branch)'
    )
    description = models.TextField(
        blank=True,
        help_text='Detailed description of cost center purpose'
    )
    
    # Hierarchy support
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        help_text='Parent cost center for hierarchical reporting'
    )
    
    # Management
    manager = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='managed_cost_centers',
        help_text='Manager responsible for this cost center'
    )
    
    # Budget tracking
    default_budget_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cost_center_budgets',
        help_text='Default expense account for budget tracking'
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether cost center is currently active'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_cost_centers'
    )
    
    class Meta:
        db_table = 'accounting_cost_centers'
        verbose_name = 'Cost Center'
        verbose_name_plural = 'Cost Centers'
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['parent', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_full_path(self):
        """Get hierarchical path (e.g., 'Sales > East Region > Nairobi Branch')"""
        path = [self.name]
        current = self
        while current.parent:
            current = current.parent
            path.insert(0, current.name)
        return ' > '.join(path)
    
    def get_total_expenses(self, fiscal_year, as_of_date=None):
        """Get total expenses for this cost center in fiscal year"""
        from django.db.models import Sum, Q
        
        filters = Q(
            journal_entry__fiscal_year=fiscal_year,
            journal_entry__status='POSTED',
            cost_center=self.code
        )
        
        if as_of_date:
            filters &= Q(journal_entry__date__lte=as_of_date)
        
        result = JournalEntryLine.objects.filter(filters).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        )
        
        total_debit = result['total_debit'] or Decimal('0.00')
        total_credit = result['total_credit'] or Decimal('0.00')
        
        return total_debit - total_credit


class Project(models.Model):
    """
    Project / Job Costing
    Track costs and revenues by project for profitability analysis
    
    Use Cases:
    - Marketing campaigns
    - System implementations
    - Branch openings
    - Loan product launches
    """
    STATUS_CHOICES = [
        ('PLANNING', 'Planning'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text='Unique project code (e.g., PRJ-2026-001)'
    )
    name = models.CharField(
        max_length=200,
        help_text='Project name'
    )
    description = models.TextField(
        blank=True,
        help_text='Detailed project description'
    )
    
    # Dates
    start_date = models.DateField(
        help_text='Project start date'
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text='Expected/actual project end date'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PLANNING',
        db_index=True
    )
    
    # Financial
    budgeted_cost = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total budgeted project cost'
    )
    budgeted_revenue = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Expected project revenue'
    )
    
    # Organizational
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='projects',
        help_text='Cost center responsible for this project'
    )
    manager = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='managed_projects',
        help_text='Project manager'
    )
    
    # Customer (optional - for client projects)
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Customer name if applicable'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_projects'
    )
    
    class Meta:
        db_table = 'accounting_projects'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status', 'start_date']),
            models.Index(fields=['manager', 'status']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_actual_cost(self, as_of_date=None):
        """Calculate total actual costs posted to this project"""
        from django.db.models import Sum, Q
        
        filters = Q(
            journal_entry__status='POSTED',
            project_code=self.code,
            account__account_type__name='EXPENSE'
        )
        
        if as_of_date:
            filters &= Q(journal_entry__date__lte=as_of_date)
        
        result = JournalEntryLine.objects.filter(filters).aggregate(
            total=Sum('debit_amount')
        )
        
        return result['total'] or Decimal('0.00')
    
    def get_actual_revenue(self, as_of_date=None):
        """Calculate total actual revenue posted to this project"""
        from django.db.models import Sum, Q
        
        filters = Q(
            journal_entry__status='POSTED',
            project_code=self.code,
            account__account_type__name='REVENUE'
        )
        
        if as_of_date:
            filters &= Q(journal_entry__date__lte=as_of_date)
        
        result = JournalEntryLine.objects.filter(filters).aggregate(
            total=Sum('credit_amount')
        )
        
        return result['total'] or Decimal('0.00')
    
    def get_variance(self, as_of_date=None):
        """Get budget variance (positive = under budget, negative = over budget)"""
        actual = self.get_actual_cost(as_of_date)
        return self.budgeted_cost - actual
    
    def get_profit(self, as_of_date=None):
        """Calculate project profit/loss"""
        revenue = self.get_actual_revenue(as_of_date)
        cost = self.get_actual_cost(as_of_date)
        return revenue - cost


# =============================================================================
# MULTI-CURRENCY SUPPORT
# =============================================================================

class Currency(models.Model):
    """
    Currency master data for multi-currency support
    """
    code = models.CharField(
        max_length=3,
        unique=True,
        db_index=True,
        help_text='ISO 4217 currency code (e.g., KES, USD, EUR)'
    )
    name = models.CharField(
        max_length=100,
        help_text='Currency name (e.g., Kenyan Shilling)'
    )
    symbol = models.CharField(
        max_length=10,
        help_text='Currency symbol (e.g., KSh, $, €)'
    )
    
    is_base = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Base/functional currency (only one should be True)'
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_currencies'
        verbose_name = 'Currency'
        verbose_name_plural = 'Currencies'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def clean(self):
        """Ensure only one base currency"""
        if self.is_base:
            # Check if another base currency exists
            existing_base = Currency.objects.filter(is_base=True).exclude(pk=self.pk)
            if existing_base.exists():
                raise ValidationError('Only one base currency is allowed')


class ExchangeRate(models.Model):
    """
    Daily exchange rates for currency conversion
    """
    from_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name='rates_from',
        help_text='Source currency'
    )
    to_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name='rates_to',
        help_text='Target currency'
    )
    rate = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text='Exchange rate (1 from_currency = X to_currency)'
    )
    date = models.DateField(
        db_index=True,
        help_text='Rate effective date'
    )
    
    SOURCE_CHOICES = [
        ('CBK', 'Central Bank of Kenya'),
        ('MANUAL', 'Manual Entry'),
        ('API', 'External API'),
    ]
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='MANUAL',
        help_text='Rate source'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_exchange_rates'
    )
    
    class Meta:
        db_table = 'accounting_exchange_rates'
        verbose_name = 'Exchange Rate'
        verbose_name_plural = 'Exchange Rates'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['from_currency', 'to_currency', 'date']),
            models.Index(fields=['date']),
        ]
        unique_together = [['from_currency', 'to_currency', 'date']]
    
    def __str__(self):
        return f"{self.from_currency.code}/{self.to_currency.code} = {self.rate} on {self.date}"
    
    @staticmethod
    def get_rate(from_currency, to_currency, date):
        """Get exchange rate for a specific date"""
        try:
            rate_record = ExchangeRate.objects.get(
                from_currency=from_currency,
                to_currency=to_currency,
                date=date
            )
            return rate_record.rate
        except ExchangeRate.DoesNotExist:
            # Try inverse rate
            try:
                inverse_rate = ExchangeRate.objects.get(
                    from_currency=to_currency,
                    to_currency=from_currency,
                    date=date
                )
                return Decimal('1.0') / inverse_rate.rate
            except ExchangeRate.DoesNotExist:
                raise ValidationError(
                    f'Exchange rate not found for {from_currency.code} to {to_currency.code} on {date}'
                )
    
    @staticmethod
    def convert_amount(amount, from_currency, to_currency, date):
        """Convert amount from one currency to another"""
        if from_currency == to_currency:
            return amount
        
        rate = ExchangeRate.get_rate(from_currency, to_currency, date)
        return amount * rate


# =============================================================================
# FIXED ASSET MANAGEMENT
# =============================================================================

class FixedAsset(models.Model):
    """
    Fixed Asset Register
    Track fixed assets with depreciation
    """
    CATEGORY_CHOICES = [
        ('LAND', 'Land'),
        ('BUILDINGS', 'Buildings'),
        ('VEHICLES', 'Vehicles'),
        ('EQUIPMENT', 'Equipment'),
        ('FURNITURE', 'Furniture & Fixtures'),
        ('COMPUTERS', 'Computers & IT Equipment'),
        ('SOFTWARE', 'Software'),
        ('LEASEHOLD', 'Leasehold Improvements'),
    ]
    
    DEPRECIATION_METHOD_CHOICES = [
        ('STRAIGHT_LINE', 'Straight Line'),
        ('DECLINING_BALANCE', 'Declining Balance'),
        ('DOUBLE_DECLINING', 'Double Declining Balance'),
        ('UNITS_OF_PRODUCTION', 'Units of Production'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('DISPOSED', 'Disposed'),
        ('FULLY_DEPRECIATED', 'Fully Depreciated'),
        ('WRITTEN_OFF', 'Written Off'),
    ]
    
    # Identification
    asset_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text='Unique asset number (e.g., FA-2026-001)'
    )
    name = models.CharField(
        max_length=200,
        help_text='Asset description'
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        db_index=True
    )
    
    # Purchase details
    purchase_date = models.DateField(
        db_index=True,
        help_text='Date of purchase/acquisition'
    )
    purchase_cost = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Total cost including acquisition costs'
    )
    salvage_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Estimated salvage/residual value'
    )
    
    # Depreciation parameters
    useful_life_years = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(Decimal('0.1'))],
        help_text='Estimated useful life in years'
    )
    depreciation_method = models.CharField(
        max_length=30,
        choices=DEPRECIATION_METHOD_CHOICES,
        default='STRAIGHT_LINE'
    )
    depreciation_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Depreciation rate % (for declining balance methods)'
    )
    
    # GL Accounts
    asset_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='fixed_assets',
        help_text='Asset GL account (e.g., 1500 - Fixed Assets)'
    )
    accumulated_depreciation_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='accumulated_depreciation_assets',
        help_text='Accumulated depreciation account (contra-asset)'
    )
    depreciation_expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='depreciation_expense_assets',
        help_text='Depreciation expense account'
    )
    
    # Cost allocation
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='fixed_assets'
    )
    
    # Physical details
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text='Physical location of asset'
    )
    custodian = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='custodian_assets',
        help_text='Employee responsible for asset'
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Manufacturer serial number'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    disposal_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of disposal/sale'
    )
    disposal_proceeds = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Proceeds from disposal'
    )
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_fixed_assets'
    )
    
    class Meta:
        db_table = 'accounting_fixed_assets'
        verbose_name = 'Fixed Asset'
        verbose_name_plural = 'Fixed Assets'
        ordering = ['asset_number']
        indexes = [
            models.Index(fields=['asset_number']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['purchase_date']),
        ]
    
    def __str__(self):
        return f"{self.asset_number} - {self.name}"
    
    def get_depreciable_amount(self):
        """Calculate depreciable amount (cost - salvage value)"""
        return self.purchase_cost - self.salvage_value
    
    def calculate_annual_depreciation(self):
        """Calculate annual depreciation expense"""
        depreciable_amount = self.get_depreciable_amount()
        
        if self.depreciation_method == 'STRAIGHT_LINE':
            return depreciable_amount / self.useful_life_years
        elif self.depreciation_method == 'DECLINING_BALANCE':
            # Simplified - would need carrying value for accurate calculation
            rate = self.depreciation_rate or (Decimal('100') / self.useful_life_years)
            return self.purchase_cost * (rate / Decimal('100'))
        else:
            return Decimal('0.00')
    
    def get_accumulated_depreciation(self, as_of_date=None):
        """Get total accumulated depreciation"""
        from django.db.models import Sum
        
        schedules = self.depreciation_schedules.filter(
            journal_entry__status='POSTED'
        )
        
        if as_of_date:
            schedules = schedules.filter(period_end_date__lte=as_of_date)
        
        result = schedules.aggregate(total=Sum('depreciation_expense'))
        return result['total'] or Decimal('0.00')
    
    def get_carrying_value(self, as_of_date=None):
        """Get net book value (cost - accumulated depreciation)"""
        accumulated = self.get_accumulated_depreciation(as_of_date)
        return self.purchase_cost - accumulated


class DepreciationSchedule(models.Model):
    """
    Calculated depreciation schedule for fixed assets
    One record per depreciation period (typically monthly)
    """
    fixed_asset = models.ForeignKey(
        FixedAsset,
        on_delete=models.CASCADE,
        related_name='depreciation_schedules'
    )
    
    period_start_date = models.DateField(
        help_text='Period start date'
    )
    period_end_date = models.DateField(
        help_text='Period end date'
    )
    
    opening_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Net book value at period start'
    )
    depreciation_expense = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Depreciation expense for this period'
    )
    accumulated_depreciation = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Total accumulated depreciation'
    )
    closing_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Net book value at period end'
    )
    
    # Link to posted journal entry
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='depreciation_schedules',
        help_text='Posted journal entry for depreciation'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_depreciation_schedules'
        verbose_name = 'Depreciation Schedule'
        verbose_name_plural = 'Depreciation Schedules'
        ordering = ['fixed_asset', 'period_end_date']
        indexes = [
            models.Index(fields=['fixed_asset', 'period_end_date']),
            models.Index(fields=['period_end_date']),
        ]
        unique_together = [['fixed_asset', 'period_end_date']]
    
    def __str__(self):
        return f"{self.fixed_asset.asset_number} - {self.period_end_date}"
