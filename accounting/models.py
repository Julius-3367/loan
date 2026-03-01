"""
Financial Management & Accounting Models

Implements a comprehensive double-entry accounting system with:
- Chart of Accounts
- Journal Entries with automatic balancing validation
- Financial reports (P&L, Balance Sheet, Trial Balance)
- Bank reconciliation
- Full audit trail
"""

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import datetime


class AccountType(models.TextChoices):
    """Account types following standard accounting principles"""
    # Balance Sheet Accounts
    ASSET = 'ASSET', 'Asset'
    LIABILITY = 'LIABILITY', 'Liability'
    EQUITY = 'EQUITY', 'Equity'
    # Income Statement Accounts
    REVENUE = 'REVENUE', 'Revenue'
    EXPENSE = 'EXPENSE', 'Expense'


class Account(models.Model):
    """
    Chart of Accounts - Master list of all accounting accounts
    
    Implements a hierarchical account structure with validation
    to ensure accounting integrity.
    """
    
    # Account identification
    code = models.CharField(
        'Account Code',
        max_length=20,
        unique=True,
        help_text='Unique identifier (e.g., 1010, 2100, 4010)'
    )
    name = models.CharField(
        'Account Name',
        max_length=200,
        help_text='Descriptive account name'
    )
    
    # Account classification
    account_type = models.CharField(
        'Account Type',
        max_length=20,
        choices=AccountType.choices,
        help_text='Primary classification for financial reporting'
    )
    
    # Hierarchical structure
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        help_text='Parent account for hierarchical reporting'
    )
    
    # Account properties
    is_active = models.BooleanField(
        'Active',
        default=True,
        help_text='Inactive accounts cannot be used in new transactions'
    )
    is_control = models.BooleanField(
        'Control Account',
        default=False,
        help_text='Control accounts cannot have direct postings (summary only)'
    )
    
    # Balance tracking
    current_balance = models.DecimalField(
        'Current Balance',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Real-time account balance (updated on transaction posting)'
    )
    
    # Metadata
    description = models.TextField('Description', blank=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)
    created_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        related_name='created_accounts',
        null=True
    )
    
    class Meta:
        db_table = 'accounting_accounts'
        ordering = ['code']
        verbose_name = 'Account'
        verbose_name_plural = 'Chart of Accounts'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['account_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def clean(self):
        """Validate account configuration"""
        if self.parent:
            # Prevent circular references
            if self.parent == self:
                raise ValidationError("Account cannot be its own parent")
            
            # Parent must be same account type
            if self.parent.account_type != self.account_type:
                raise ValidationError(
                    f"Parent account must be of type {self.get_account_type_display()}"
                )
        
        # Control accounts cannot have direct postings
        if self.is_control and self.journal_lines.exists():
            raise ValidationError("Cannot make control account - has existing transactions")
    
    def get_balance(self, as_of_date=None):
        """
        Calculate account balance up to a specific date
        
        Args:
            as_of_date: Date to calculate balance as of (None = current)
        
        Returns:
            Decimal: Account balance
        """
        lines = self.journal_lines.filter(
            journal_entry__status=JournalEntry.Status.POSTED
        )
        
        if as_of_date:
            lines = lines.filter(journal_entry__date__lte=as_of_date)
        
        debits = lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0.00')
        credits = lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0.00')
        
        # Calculate balance based on account type
        if self.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
            # Normal debit balance
            return debits - credits
        else:
            # Normal credit balance (Liability, Equity, Revenue)
            return credits - debits
    
    def update_balance(self):
        """Recalculate and update current_balance field"""
        self.current_balance = self.get_balance()
        self.save(update_fields=['current_balance', 'updated_at'])


class FiscalPeriod(models.Model):
    """
    Accounting periods for financial reporting
    """
    
    name = models.CharField('Period Name', max_length=100)
    start_date = models.DateField('Start Date')
    end_date = models.DateField('End Date')
    
    is_closed = models.BooleanField(
        'Closed',
        default=False,
        help_text='Closed periods cannot have new transactions'
    )
    
    closed_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='closed_periods'
    )
    closed_at = models.DateTimeField('Closed At', null=True, blank=True)
    
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_fiscal_periods'
        ordering = ['-start_date']
        verbose_name = 'Fiscal Period'
        verbose_name_plural = 'Fiscal Periods'
        unique_together = [['start_date', 'end_date']]
    
    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"
    
    def clean(self):
        """Validate period dates"""
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError("Start date must be before end date")
            
            # Check for overlapping periods
            overlapping = FiscalPeriod.objects.filter(
                models.Q(start_date__lte=self.end_date, end_date__gte=self.start_date)
            ).exclude(pk=self.pk)
            
            if overlapping.exists():
                raise ValidationError("Period overlaps with existing period")


class JournalEntry(models.Model):
    """
    Journal Entry - Container for double-entry accounting transactions
    
    Implements automatic validation to ensure:
    - Debits always equal credits
    - Entries are immutable once posted
    - Full audit trail maintained
    """
    
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        POSTED = 'POSTED', 'Posted'
        REVERSED = 'REVERSED', 'Reversed'
    
    class EntryType(models.TextChoices):
        STANDARD = 'STANDARD', 'Standard Entry'
        LOAN_DISBURSEMENT = 'LOAN_DISBURSEMENT', 'Loan Disbursement'
        LOAN_REPAYMENT = 'LOAN_REPAYMENT', 'Loan Repayment'
        INTEREST_ACCRUAL = 'INTEREST_ACCRUAL', 'Interest Accrual'
        FEE_RECOGNITION = 'FEE_RECOGNITION', 'Fee Recognition'
        PENALTY_ACCRUAL = 'PENALTY_ACCRUAL', 'Penalty Accrual'
        WRITE_OFF = 'WRITE_OFF', 'Loan Write-Off'
        PAYROLL = 'PAYROLL', 'Payroll Entry'
        DEPRECIATION = 'DEPRECIATION', 'Depreciation'
        BANK_TRANSACTION = 'BANK_TRANSACTION', 'Bank Transaction'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment Entry'
    
    # Entry identification
    entry_number = models.CharField(
        'Entry Number',
        max_length=50,
        unique=True,
        help_text='Auto-generated unique identifier'
    )
    
    # Entry classification
    entry_type = models.CharField(
        'Entry Type',
        max_length=30,
        choices=EntryType.choices,
        default=EntryType.STANDARD
    )
    
    status = models.CharField(
        'Status',
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Transaction details
    date = models.DateField(
        'Transaction Date',
        default=timezone.now,
        help_text='Date when transaction occurred'
    )
    
    reference = models.CharField(
        'Reference',
        max_length=200,
        blank=True,
        help_text='External reference (invoice number, loan ID, etc.)'
    )
    
    description = models.TextField(
        'Description',
        help_text='Detailed explanation of the transaction'
    )
    
    # Related objects (for automated entries)
    loan = models.ForeignKey(
        'loans.Loan',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_entries'
    )
    
    loan_repayment = models.ForeignKey(
        'loans.LoanRepayment',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_entries'
    )
    
    # Financial period
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_entries'
    )
    
    # Balance validation
    total_debit = models.DecimalField(
        'Total Debit',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    total_credit = models.DecimalField(
        'Total Credit',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    
    # Reversal tracking
    reversed_entry = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversing_entries',
        help_text='Original entry that this entry reverses'
    )
    
    # Audit fields
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    created_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        related_name='created_journal_entries'
    )
    
    posted_at = models.DateTimeField('Posted At', null=True, blank=True)
    posted_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_journal_entries'
    )
    
    class Meta:
        db_table = 'accounting_journal_entries'
        ordering = ['-date', '-created_at']
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        indexes = [
            models.Index(fields=['entry_number']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['entry_type']),
        ]
    
    def __str__(self):
        return f"{self.entry_number} - {self.description[:50]}"
    
    def clean(self):
        """Validate journal entry"""
        # Posted entries are immutable
        if self.pk and self.status == self.Status.POSTED:
            old_entry = JournalEntry.objects.get(pk=self.pk)
            if old_entry.status == self.Status.POSTED and self._state.adding == False:
                raise ValidationError("Posted entries cannot be modified")
        
        # Check period is not closed
        if self.fiscal_period and self.fiscal_period.is_closed:
            raise ValidationError(f"Cannot post to closed period: {self.fiscal_period}")
    
    def calculate_totals(self):
        """Calculate total debits and credits from lines"""
        lines = self.lines.all()
        self.total_debit = sum(line.debit for line in lines)
        self.total_credit = sum(line.credit for line in lines)
    
    def is_balanced(self):
        """Check if debits equal credits"""
        self.calculate_totals()
        return self.total_debit == self.total_credit
    
    @transaction.atomic
    def post(self, user):
        """
        Post journal entry to the ledger
        
        Validates balance and updates account balances.
        Once posted, entry becomes immutable.
        """
        if self.status == self.Status.POSTED:
            raise ValidationError("Entry is already posted")
        
        if not self.is_balanced():
            raise ValidationError(
                f"Entry is not balanced. Debits: {self.total_debit}, Credits: {self.total_credit}"
            )
        
        if not self.lines.exists():
            raise ValidationError("Cannot post entry with no lines")
        
        # Update status
        self.status = self.Status.POSTED
        self.posted_at = timezone.now()
        self.posted_by = user
        self.save()
        
        # Update account balances
        for line in self.lines.all():
            line.account.update_balance()
    
    @transaction.atomic
    def reverse(self, user, description=None):
        """
        Create a reversing entry
        
        Creates a new journal entry with opposite debits/credits
        to reverse the effect of this entry.
        """
        if self.status != self.Status.POSTED:
            raise ValidationError("Can only reverse posted entries")
        
        if self.reversing_entries.exists():
            raise ValidationError("Entry has already been reversed")
        
        # Create reversing entry
        reversing_entry = JournalEntry.objects.create(
            entry_type=self.EntryType.ADJUSTMENT,
            status=self.Status.DRAFT,
            date=timezone.now().date(),
            reference=self.reference,
            description=description or f"Reversal of {self.entry_number}: {self.description}",
            reversed_entry=self,
            created_by=user
        )
        
        # Create reversed lines
        for line in self.lines.all():
            JournalLine.objects.create(
                journal_entry=reversing_entry,
                account=line.account,
                debit=line.credit,  # Swap debit and credit
                credit=line.debit,
                description=f"Reversal: {line.description}"
            )
        
        # Post reversing entry
        reversing_entry.post(user)
        
        # Mark original as reversed
        self.status = self.Status.REVERSED
        self.save()
        
        return reversing_entry
    
    def save(self, *args, **kwargs):
        """Auto-generate entry number and calculate totals"""
        if not self.entry_number:
            # Generate entry number: JE-YYYYMMDD-XXXX
            today = timezone.now().date()
            prefix = f"JE-{today.strftime('%Y%m%d')}-"
            
            last_entry = JournalEntry.objects.filter(
                entry_number__startswith=prefix
            ).order_by('-entry_number').first()
            
            if last_entry:
                last_num = int(last_entry.entry_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.entry_number = f"{prefix}{new_num:04d}"
        
        # Calculate totals
        if self.pk:
            self.calculate_totals()
        
        super().save(*args, **kwargs)


class JournalLine(models.Model):
    """
    Journal Line - Individual debit or credit in a journal entry
    
    Each line represents one side of a double-entry transaction.
    """
    
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='journal_lines',
        help_text='Account to be debited or credited'
    )
    
    debit = models.DecimalField(
        'Debit Amount',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Amount to debit (increase assets/expenses)'
    )
    
    credit = models.DecimalField(
        'Credit Amount',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Amount to credit (increase liabilities/equity/revenue)'
    )
    
    description = models.CharField(
        'Line Description',
        max_length=500,
        blank=True
    )
    
    # Cost tracking dimensions
    cost_center_code = models.CharField(
        'Cost Center',
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='Cost center code for departmental tracking'
    )
    project_code = models.CharField(
        'Project Code',
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='Project code for job costing'
    )
    
    # Metadata
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_journal_lines'
        ordering = ['journal_entry', 'id']
        verbose_name = 'Journal Line'
        verbose_name_plural = 'Journal Lines'
        indexes = [
            models.Index(fields=['journal_entry', 'account']),
        ]
    
    def __str__(self):
        if self.debit > 0:
            return f"DR {self.account.code} - {self.debit}"
        else:
            return f"CR {self.account.code} - {self.credit}"
    
    def clean(self):
        """Validate journal line"""
        # Line must have either debit or credit, not both
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("Line cannot have both debit and credit")
        
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Line must have either debit or credit amount")
        
        # Cannot post to control accounts
        if self.account and self.account.is_control:
            raise ValidationError(f"Cannot post to control account: {self.account}")
        
        # Cannot post to inactive accounts
        if self.account and not self.account.is_active:
            raise ValidationError(f"Cannot post to inactive account: {self.account}")
    
    def save(self, *args, **kwargs):
        """Validate before saving"""
        # Ensure defaults for tracking codes
        if not self.cost_center_code:
            self.cost_center_code = ''
        if not self.project_code:
            self.project_code = ''
            
        self.full_clean()
        super().save(*args, **kwargs)
        
        # Update journal entry totals
        if self.journal_entry_id:
            self.journal_entry.calculate_totals()
            self.journal_entry.save(update_fields=['total_debit', 'total_credit'])


class BankStatement(models.Model):
    """
    Bank Statement for reconciliation
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Reconciliation'
        RECONCILED = 'RECONCILED', 'Reconciled'
        PARTIAL = 'PARTIAL', 'Partially Reconciled'
    
    bank_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='bank_statements',
        limit_choices_to={'account_type': AccountType.ASSET},
        help_text='Bank account from Chart of Accounts'
    )
    
    statement_number = models.CharField('Statement Number', max_length=100, unique=True)
    statement_date = models.DateField('Statement Date')
    
    opening_balance = models.DecimalField(
        'Opening Balance',
        max_digits=15,
        decimal_places=2
    )
    
    closing_balance = models.DecimalField(
        'Closing Balance',
        max_digits=15,
        decimal_places=2
    )
    
    status = models.CharField(
        'Status',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Import details
    import_file = models.CharField('Import File', max_length=500, blank=True)
    imported_at = models.DateTimeField('Imported At', auto_now_add=True)
    imported_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        related_name='imported_statements'
    )
    
    # Reconciliation details
    reconciled_at = models.DateTimeField('Reconciled At', null=True, blank=True)
    reconciled_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reconciled_statements'
    )
    
    class Meta:
        db_table = 'accounting_bank_statements'
        ordering = ['-statement_date']
        verbose_name = 'Bank Statement'
        verbose_name_plural = 'Bank Statements'
    
    def __str__(self):
        return f"{self.bank_account.name} - {self.statement_number}"
    
    def calculate_reconciliation_status(self):
        """Calculate reconciliation status based on matched transactions"""
        total = self.transactions.count()
        if total == 0:
            return self.Status.PENDING
        
        matched = self.transactions.filter(is_reconciled=True).count()
        
        if matched == 0:
            return self.Status.PENDING
        elif matched == total:
            return self.Status.RECONCILED
        else:
            return self.Status.PARTIAL


class BankTransaction(models.Model):
    """
    Individual transaction from bank statement
    """
    
    class TransactionType(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Deposit'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        FEE = 'FEE', 'Bank Fee'
        INTEREST = 'INTEREST', 'Interest'
        TRANSFER = 'TRANSFER', 'Transfer'
    
    bank_statement = models.ForeignKey(
        BankStatement,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    
    transaction_date = models.DateField('Transaction Date')
    transaction_type = models.CharField(
        'Type',
        max_length=20,
        choices=TransactionType.choices
    )
    
    reference = models.CharField('Reference', max_length=200, blank=True)
    description = models.CharField('Description', max_length=500)
    
    amount = models.DecimalField(
        'Amount',
        max_digits=15,
        decimal_places=2,
        help_text='Positive for deposits, negative for withdrawals'
    )
    
    # Reconciliation
    is_reconciled = models.BooleanField('Reconciled', default=False)
    matched_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matched_bank_transactions'
    )
    
    reconciled_at = models.DateTimeField('Reconciled At', null=True, blank=True)
    reconciled_by = models.ForeignKey(
        'core.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reconciled_transactions'
    )
    
    class Meta:
        db_table = 'accounting_bank_transactions'
        ordering = ['transaction_date', 'id']
        verbose_name = 'Bank Transaction'
        verbose_name_plural = 'Bank Transactions'
    
    def __str__(self):
        return f"{self.transaction_date} - {self.description} - {self.amount}"


# =======================================================================================
# ADVANCED COST ACCOUNTING & MULTI-CURRENCY SUPPORT
# =======================================================================================

class CostCenter(models.Model):
    """
    Cost Center / Department / Branch
    Enables departmental profitability analysis
    """
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Hierarchy
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    
    # Management
    manager = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='managed_cost_centers')
    
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='created_cost_centers')
    
    class Meta:
        db_table = 'accounting_cost_centers'
        ordering = ['code']
        
    def __str__(self):
        return f"{self.code} - {self.name}"


class Project(models.Model):
    """
    Project / Job Costing
    Track costs and revenues by project
    """
    STATUS_CHOICES = [
        ('PLANNING', 'Planning'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNING', db_index=True)
    
    budgeted_cost = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    budgeted_revenue = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, null=True, blank=True, related_name='projects')
    manager = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='managed_projects')
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='created_projects')
    
    class Meta:
        db_table = 'accounting_projects'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.code} - {self.name}"


class Currency(models.Model):
    """
    Multi-currency support
    """
    code = models.CharField(max_length=3, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    is_base = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_currencies'
        ordering = ['code']
        
    def __str__(self):
        return f"{self.code} - {self.name}"


class ExchangeRate(models.Model):
    """
    Daily exchange rates for currency conversion
    """
    from_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='rates_from')
    to_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='rates_to')
    rate = models.DecimalField(max_digits=20, decimal_places=6)
    date = models.DateField(db_index=True)
    
    SOURCE_CHOICES = [
        ('CBK', 'Central Bank of Kenya'),
        ('MANUAL', 'Manual Entry'),
        ('API', 'External API'),
    ]
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='created_exchange_rates')
    
    class Meta:
        db_table = 'accounting_exchange_rates'
        ordering = ['-date']
        unique_together = [['from_currency', 'to_currency', 'date']]
        
    def __str__(self):
        return f"{self.from_currency.code}/{self.to_currency.code} = {self.rate} on {self.date}"


class FixedAsset(models.Model):
    """
    Fixed Asset Register with depreciation tracking
    """
    CATEGORY_CHOICES = [
        ('LAND', 'Land'),
        ('BUILDINGS', 'Buildings'),
        ('VEHICLES', 'Vehicles'),
        ('EQUIPMENT', 'Equipment'),
        ('FURNITURE', 'Furniture & Fixtures'),
        ('COMPUTERS', 'Computers & IT Equipment'),
    ]
    
    DEPRECIATION_METHOD_CHOICES = [
        ('STRAIGHT_LINE', 'Straight Line'),
        ('DECLINING_BALANCE', 'Declining Balance'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('DISPOSED', 'Disposed'),
        ('FULLY_DEPRECIATED', 'Fully Depreciated'),
    ]
    
    asset_number = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, db_index=True)
    
    purchase_date = models.DateField(db_index=True)
    purchase_cost = models.DecimalField(max_digits=20, decimal_places=2)
    salvage_value = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    useful_life_years = models.DecimalField(max_digits=5, decimal_places=1)
    depreciation_method = models.CharField(max_length=30, choices=DEPRECIATION_METHOD_CHOICES, default='STRAIGHT_LINE')
    
    asset_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='fixed_assets')
    accumulated_depreciation_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='accumulated_depreciation_assets')
    depreciation_expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='depreciation_expense_assets')
    
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, null=True, blank=True, related_name='fixed_assets')
    location = models.CharField(max_length=200, blank=True)
    custodian = models.ForeignKey('core.User', on_delete=models.PROTECT, null=True, blank=True, related_name='custodian_assets')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    disposal_date = models.DateField(null=True, blank=True)
    disposal_proceeds = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='created_fixed_assets')
    
    class Meta:
        db_table = 'accounting_fixed_assets'
        ordering = ['asset_number']
        
    def __str__(self):
        return f"{self.asset_number} - {self.name}"
    
    def get_depreciable_amount(self):
        """Calculate depreciable amount"""
        return self.purchase_cost - self.salvage_value
    
    def calculate_annual_depreciation(self):
        """Calculate annual depreciation"""
        if self.depreciation_method == 'STRAIGHT_LINE':
            return self.get_depreciable_amount() / self.useful_life_years
        return Decimal('0.00')


class DepreciationSchedule(models.Model):
    """
    Depreciation schedule tracking
    """
    fixed_asset = models.ForeignKey(FixedAsset, on_delete=models.CASCADE, related_name='depreciation_schedules')
    period_start_date = models.DateField()
    period_end_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2)
    depreciation_expense = models.DecimalField(max_digits=20, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=20, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=20, decimal_places=2)
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='depreciation_schedules')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounting_depreciation_schedules'
        ordering = ['fixed_asset', 'period_end_date']
        unique_together = [['fixed_asset', 'period_end_date']]
        
    def __str__(self):
        return f"{self.fixed_asset.asset_number} - {self.period_end_date}"

