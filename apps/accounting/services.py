"""
Accounting Services: Business logic for double-entry accounting operations

This service layer provides safe, transaction-protected methods for creating
and managing journal entries, ensuring data integrity and business rule compliance.
"""
from decimal import Decimal
from typing import List, Dict, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    FiscalYear,
    AccountType,
    Account,
    JournalEntry,
    JournalEntryLine,
)


class AccountingService:
    """
    Service class for accounting operations
    
    Provides transaction-safe methods for:
    - Creating journal entries
    - Posting journal entries
    - Reversing journal entries
    - Validating account balances
    
    All methods use database transactions to ensure data integrity.
    """
    
    @staticmethod
    def generate_entry_number(prefix: str = "JE") -> str:
        """
        Generate unique journal entry number
        
        Args:
            prefix: Prefix for entry number (default: "JE")
            
        Returns:
            str: Unique entry number (e.g., "JE-2026-00001")
        """
        from django.db.models import Max
        
        year = timezone.now().year
        prefix_with_year = f"{prefix}-{year}"
        
        # Get the highest entry number for this year
        last_entry = JournalEntry.objects.filter(
            entry_number__startswith=prefix_with_year
        ).aggregate(Max('entry_number'))['entry_number__max']
        
        if last_entry:
            # Extract the numeric part and increment
            last_number = int(last_entry.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        
        return f"{prefix_with_year}-{new_number:05d}"
    
    @staticmethod
    @transaction.atomic
    def create_journal_entry(
        date,
        fiscal_year,
        description: str,
        lines: List[Dict],
        created_by,
        entry_number: Optional[str] = None,
        reference: str = "",
        source_module: str = "",
        source_document: str = "",
        auto_post: bool = False,
    ) -> JournalEntry:
        """
        Create a journal entry with lines
        
        Args:
            date: Transaction date
            fiscal_year: FiscalYear instance
            description: Entry description
            lines: List of dicts with keys:
                - account: Account instance or code
                - description: Line description
                - debit_amount: Decimal (optional, default 0)
                - credit_amount: Decimal (optional, default 0)
                - cost_center: str (optional)
                - department: str (optional)
            created_by: User instance
            entry_number: Optional entry number (generated if not provided)
            reference: External reference
            source_module: Source module name
            source_document: Source document reference
            auto_post: Whether to post immediately after creation
            
        Returns:
            JournalEntry: Created journal entry
            
        Raises:
            ValidationError: If entry is unbalanced or validation fails
            
        Example:
            entry = AccountingService.create_journal_entry(
                date=date.today(),
                fiscal_year=fy,
                description="Cash sale",
                lines=[
                    {'account': cash_account, 'debit_amount': Decimal('1000.00'), 'description': 'Cash received'},
                    {'account': revenue_account, 'credit_amount': Decimal('1000.00'), 'description': 'Sale revenue'},
                ],
                created_by=user,
            )
        """
        # Generate entry number if not provided
        if not entry_number:
            entry_number = AccountingService.generate_entry_number()
        
        # Validate lines exist
        if not lines:
            raise ValidationError("Journal entry must have at least one line")
        
        # Validate balanced before creating
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for line in lines:
            debit = line.get('debit_amount', Decimal('0.00'))
            credit = line.get('credit_amount', Decimal('0.00'))
            
            if isinstance(debit, (int, float, str)):
                debit = Decimal(str(debit))
            if isinstance(credit, (int, float, str)):
                credit = Decimal(str(credit))
            
            total_debits += debit
            total_credits += credit
        
        if total_debits != total_credits:
            raise ValidationError(
                f"Journal entry is unbalanced. "
                f"Debits: {total_debits}, Credits: {total_credits}, "
                f"Difference: {total_debits - total_credits}"
            )
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            entry_number=entry_number,
            date=date,
            fiscal_year=fiscal_year,
            description=description,
            reference=reference,
            source_module=source_module,
            source_document=source_document,
            created_by=created_by,
            status='DRAFT',
        )
        
        # Create lines
        for line_data in lines:
            # Get account instance
            account = line_data['account']
            if isinstance(account, str):
                # Assume it's an account code
                account = Account.objects.get(code=account)
            
            # Convert amounts to Decimal
            debit = line_data.get('debit_amount', Decimal('0.00'))
            credit = line_data.get('credit_amount', Decimal('0.00'))
            
            if isinstance(debit, (int, float, str)):
                debit = Decimal(str(debit))
            if isinstance(credit, (int, float, str)):
                credit = Decimal(str(credit))
            
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=account,
                description=line_data['description'],
                debit_amount=debit,
                credit_amount=credit,
                cost_center=line_data.get('cost_center', ''),
                department=line_data.get('department', ''),
            )
        
        # Auto-post if requested
        if auto_post:
            entry.post(created_by)
        
        return entry
    
    @staticmethod
    @transaction.atomic
    def post_journal_entry(entry_id: int, user) -> JournalEntry:
        """
        Post a draft journal entry
        
        Args:
            entry_id: Journal entry ID
            user: User posting the entry
            
        Returns:
            JournalEntry: Posted entry
            
        Raises:
            ValidationError: If entry cannot be posted
        """
        entry = JournalEntry.objects.select_for_update().get(id=entry_id)
        entry.post(user)
        return entry
    
    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(
        entry_id: int,
        user,
        reason: str
    ) -> JournalEntry:
        """
        Reverse a posted journal entry
        
        Args:
            entry_id: Journal entry ID to reverse
            user: User reversing the entry
            reason: Reason for reversal
            
        Returns:
            JournalEntry: Reversing entry
            
        Raises:
            ValidationError: If entry cannot be reversed
        """
        entry = JournalEntry.objects.select_for_update().get(id=entry_id)
        reversing_entry = entry.reverse(user, reason)
        return reversing_entry
    
    @staticmethod
    def validate_account_balance(account, expected_balance: Decimal, as_of_date=None) -> bool:
        """
        Validate account balance matches expected amount
        
        Args:
            account: Account instance
            expected_balance: Expected balance
            as_of_date: Date to check balance as of (default: now)
            
        Returns:
            bool: Whether balance matches
        """
        actual_balance = account.get_balance(as_of_date)
        return actual_balance == expected_balance
    
    @staticmethod
    def get_trial_balance(fiscal_year, as_of_date=None) -> Dict:
        """
        Generate trial balance for a fiscal year
        
        Args:
            fiscal_year: FiscalYear instance
            as_of_date: Date to calculate balance as of (default: fiscal year end)
            
        Returns:
            dict: Trial balance with accounts, debits, credits
        """
        if not as_of_date:
            as_of_date = fiscal_year.end_date
        
        accounts = Account.objects.filter(is_active=True).order_by('code')
        
        trial_balance = {
            'accounts': [],
            'total_debits': Decimal('0.00'),
            'total_credits': Decimal('0.00'),
            'is_balanced': True,
        }
        
        for account in accounts:
            balance = account.get_balance(as_of_date)
            
            if balance != 0:
                # Determine debit or credit side
                if account.account_type.normal_balance == 'DEBIT':
                    debit_balance = balance if balance > 0 else Decimal('0.00')
                    credit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                else:
                    credit_balance = balance if balance > 0 else Decimal('0.00')
                    debit_balance = abs(balance) if balance < 0 else Decimal('0.00')
                
                trial_balance['accounts'].append({
                    'code': account.code,
                    'name': account.name,
                    'type': account.account_type.get_name_display(),
                    'debit_balance': debit_balance,
                    'credit_balance': credit_balance,
                })
                
                trial_balance['total_debits'] += debit_balance
                trial_balance['total_credits'] += credit_balance
        
        trial_balance['is_balanced'] = (
            trial_balance['total_debits'] == trial_balance['total_credits']
        )
        
        return trial_balance
    
    @staticmethod
    @transaction.atomic
    def create_simple_entry(
        date,
        fiscal_year,
        description: str,
        debit_account,
        credit_account,
        amount: Decimal,
        created_by,
        reference: str = "",
        auto_post: bool = False,
    ) -> JournalEntry:
        """
        Create a simple two-line journal entry (debit/credit)
        
        This is a convenience method for common single debit/credit entries.
        
        Args:
            date: Transaction date
            fiscal_year: FiscalYear instance
            description: Entry description
            debit_account: Account to debit (instance or code)
            credit_account: Account to credit (instance or code)
            amount: Transaction amount
            created_by: User instance
            reference: External reference
            auto_post: Whether to post immediately
            
        Returns:
            JournalEntry: Created entry
            
        Example:
            entry = AccountingService.create_simple_entry(
                date=date.today(),
                fiscal_year=fy,
                description="Cash payment for supplies",
                debit_account="5100",  # Supplies Expense
                credit_account="1000",  # Cash
                amount=Decimal('500.00'),
                created_by=user,
                auto_post=True,
            )
        """
        lines = [
            {
                'account': debit_account,
                'description': description,
                'debit_amount': amount,
                'credit_amount': Decimal('0.00'),
            },
            {
                'account': credit_account,
                'description': description,
                'debit_amount': Decimal('0.00'),
                'credit_amount': amount,
            },
        ]
        
        return AccountingService.create_journal_entry(
            date=date,
            fiscal_year=fiscal_year,
            description=description,
            lines=lines,
            created_by=created_by,
            reference=reference,
            auto_post=auto_post,
        )
    
    # =============================================================================
    # CASH FLOW STATEMENT
    # =============================================================================
    
    @staticmethod
    def get_cash_flow_statement(fiscal_year, start_date=None, end_date=None):
        """
        Generate Statement of Cash Flows (Indirect Method)
        
        Classifies cash flows into three categories:
        1. Operating Activities - Day-to-day business operations
        2. Investing Activities - Purchase/sale of long-term assets
        3. Financing Activities - Borrowing and equity transactions
        
        Args:
            fiscal_year: FiscalYear instance
            start_date: Optional start date (defaults to fiscal year start)
            end_date: Optional end date (defaults to fiscal year end or today)
        
        Returns:
            dict with operating, investing, financing cash flows
        """
        from django.db.models import Sum, Q
        from .models import Account
        
        if start_date is None:
            start_date = fiscal_year.start_date
        
        if end_date is None:
            end_date = min(fiscal_year.end_date, timezone.now().date())
        
        # Get all cash and bank accounts (typically 1000-1099)
        cash_accounts = Account.objects.filter(
            Q(code__startswith='1000') | Q(code__startswith='1001') | 
            Q(code__startswith='1002') | Q(code__startswith='1003'),
            account_type__name='ASSET',
            is_active=True
        )
        
        # Calculate opening and closing cash balances
        opening_balance = Decimal('0.00')
        closing_balance = Decimal('0.00')
        
        for account in cash_accounts:
            # Opening balance (as of start_date - 1 day)
            opening_balance += account.get_balance(start_date)
            # Closing balance (as of end_date)
            closing_balance += account.get_balance(end_date)
        
        # =================================================================
        # OPERATING ACTIVITIES (Indirect Method)
        # =================================================================
        
        # Start with net income
        revenue_accounts = Account.objects.filter(
            account_type__name='REVENUE',
            is_active=True
        )
        expense_accounts = Account.objects.filter(
            account_type__name='EXPENSE',
            is_active=True
        )
        
        total_revenue = sum(
            account.get_balance(end_date) 
            for account in revenue_accounts
        )
        total_expenses = sum(
            account.get_balance(end_date) 
            for account in expense_accounts
        )
        net_income = total_revenue - total_expenses
        
        # Non-cash adjustments
        operating_activities = {
            'net_income': net_income,
            'adjustments': [],
            'total_adjustments': Decimal('0.00'),
        }
        
        # Add back depreciation (non-cash expense)
        depreciation_accounts = Account.objects.filter(
            Q(name__icontains='depreciation') | Q(code__startswith='5300'),
            account_type__name='EXPENSE',
            is_active=True
        )
        depreciation_expense = sum(
            account.get_balance(end_date)
            for account in depreciation_accounts
        )
        if depreciation_expense > 0:
            operating_activities['adjustments'].append({
                'description': 'Depreciation expense',
                'amount': depreciation_expense
            })
            operating_activities['total_adjustments'] += depreciation_expense
        
        # Add back bad debt provision (non-cash expense)
        bad_debt_accounts = Account.objects.filter(
            Q(name__icontains='bad debt') | Q(code__startswith='5200'),
            account_type__name='EXPENSE',
            is_active=True
        )
        bad_debt_expense = sum(
            account.get_balance(end_date)
            for account in bad_debt_accounts
        )
        if bad_debt_expense > 0:
            operating_activities['adjustments'].append({
                'description': 'Bad debt provision',
                'amount': bad_debt_expense
            })
            operating_activities['total_adjustments'] += bad_debt_expense
        
        # Changes in working capital (simplified - would need period comparison)
        # For now, we'll leave this as a placeholder
        operating_activities['working_capital_changes'] = []
        
        operating_activities['net_cash_from_operations'] = (
            net_income + operating_activities['total_adjustments']
        )
        
        # =================================================================
        # INVESTING ACTIVITIES
        # =================================================================
        
        investing_activities = {
            'items': [],
            'total': Decimal('0.00')
        }
        
        # Loan disbursements (cash outflow)
        loan_disbursement_entries = JournalEntry.objects.filter(
            fiscal_year=fiscal_year,
            date__gte=start_date,
            date__lte=end_date,
            status='POSTED',
            entry_type='LOAN_DISBURSEMENT'
        )
        
        loan_disbursements_total = Decimal('0.00')
        for entry in loan_disbursement_entries:
            # Get the credit side (cash out)
            credits = entry.lines.filter(credit_amount__gt=0).aggregate(
                total=Sum('credit_amount')
            )
            amount = credits['total'] or Decimal('0.00')
            loan_disbursements_total += amount
        
        if loan_disbursements_total > 0:
            investing_activities['items'].append({
                'description': 'Loan disbursements',
                'amount': -loan_disbursements_total  # Negative = cash outflow
            })
            investing_activities['total'] -= loan_disbursements_total
        
        # Fixed asset purchases
        fixed_asset_accounts = Account.objects.filter(
            Q(code__startswith='15') | Q(name__icontains='fixed asset'),
            account_type__name='ASSET',
            is_active=True
        )
        
        fixed_asset_purchases = Decimal('0.00')
        for account in fixed_asset_accounts:
            # Get debits in period (purchases)
            period_debits = JournalEntryLine.objects.filter(
                journal_entry__fiscal_year=fiscal_year,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date,
                journal_entry__status='POSTED',
                account=account,
                debit_amount__gt=0
            ).aggregate(total=Sum('debit_amount'))
            
            amount = period_debits['total'] or Decimal('0.00')
            fixed_asset_purchases += amount
        
        if fixed_asset_purchases > 0:
            investing_activities['items'].append({
                'description': 'Purchase of fixed assets',
                'amount': -fixed_asset_purchases  # Negative = cash outflow
            })
            investing_activities['total'] -= fixed_asset_purchases
        
        # =================================================================
        # FINANCING ACTIVITIES
        # =================================================================
        
        financing_activities = {
            'items': [],
            'total': Decimal('0.00')
        }
        
        # Loan repayments received (cash inflow)
        loan_repayment_entries = JournalEntry.objects.filter(
            fiscal_year=fiscal_year,
            date__gte=start_date,
            date__lte=end_date,
            status='POSTED',
            entry_type='LOAN_REPAYMENT'
        )
        
        loan_repayments_total = Decimal('0.00')
        for entry in loan_repayment_entries:
            # Get the debit side (cash in)
            debits = entry.lines.filter(
                debit_amount__gt=0,
                account__code__startswith='10'  # Cash accounts
            ).aggregate(total=Sum('debit_amount'))
            amount = debits['total'] or Decimal('0.00')
            loan_repayments_total += amount
        
        if loan_repayments_total > 0:
            financing_activities['items'].append({
                'description': 'Loan repayments received',
                'amount': loan_repayments_total  # Positive = cash inflow
            })
            financing_activities['total'] += loan_repayments_total
        
        # Equity contributions (share capital)
        equity_accounts = Account.objects.filter(
            Q(code__startswith='30') | Q(name__icontains='share capital'),
            account_type__name='EQUITY',
            is_active=True
        )
        
        equity_contributions = Decimal('0.00')
        for account in equity_accounts:
            period_credits = JournalEntryLine.objects.filter(
                journal_entry__fiscal_year=fiscal_year,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date,
                journal_entry__status='POSTED',
                account=account,
                credit_amount__gt=0
            ).aggregate(total=Sum('credit_amount'))
            
            amount = period_credits['total'] or Decimal('0.00')
            equity_contributions += amount
        
        if equity_contributions > 0:
            financing_activities['items'].append({
                'description': 'Equity contributions',
                'amount': equity_contributions  # Positive = cash inflow
            })
            financing_activities['total'] += equity_contributions
        
        # =================================================================
        # SUMMARY
        # =================================================================
        
        net_cash_change = (
            operating_activities['net_cash_from_operations'] +
            investing_activities['total'] +
            financing_activities['total']
        )
        
        calculated_closing_balance = opening_balance + net_cash_change
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'fiscal_year': fiscal_year.name
            },
            'cash_balances': {
                'opening_balance': opening_balance,
                'closing_balance': closing_balance,
                'calculated_closing': calculated_closing_balance,
                'reconciliation_difference': closing_balance - calculated_closing_balance
            },
            'operating_activities': operating_activities,
            'investing_activities': investing_activities,
            'financing_activities': financing_activities,
            'summary': {
                'net_cash_from_operations': operating_activities['net_cash_from_operations'],
                'net_cash_from_investing': investing_activities['total'],
                'net_cash_from_financing': financing_activities['total'],
                'net_increase_in_cash': net_cash_change
            }
        }
    
    # =============================================================================
    # COST ACCOUNTING REPORTS
    # =============================================================================
    
    @staticmethod
    def get_cost_center_report(cost_center_code, fiscal_year, as_of_date=None):
        """
        Generate cost center performance report
        
        Args:
            cost_center_code: Cost center code
            fiscal_year: FiscalYear instance
            as_of_date: Optional date (defaults to today)
        
        Returns:
            dict with expenses by account
        """
        from django.db.models import Sum
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        # Get all journal lines for this cost center
        lines = JournalEntryLine.objects.filter(
            cost_center=cost_center_code,
            journal_entry__fiscal_year=fiscal_year,
            journal_entry__status='POSTED',
            journal_entry__date__lte=as_of_date
        )
        
        # Group by account
        expense_by_account = lines.values(
            'account__code',
            'account__name',
            'account__account_type__name'
        ).annotate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        ).order_by('account__code')
        
        total_expenses = Decimal('0.00')
        total_revenue = Decimal('0.00')
        
        expenses_list = []
        revenue_list = []
        
        for item in expense_by_account:
            net_amount = item['total_debit'] - item['total_credit']
            
            if item['account__account_type__name'] == 'EXPENSE':
                expenses_list.append({
                    'code': item['account__code'],
                    'name': item['account__name'],
                    'amount': net_amount
                })
                total_expenses += net_amount
            elif item['account__account_type__name'] == 'REVENUE':
                revenue_list.append({
                    'code': item['account__code'],
                    'name': item['account__name'],
                    'amount': item['total_credit'] - item['total_debit']
                })
                total_revenue += (item['total_credit'] - item['total_debit'])
        
        return {
            'cost_center': cost_center_code,
            'fiscal_year': fiscal_year.name,
            'as_of_date': as_of_date,
            'revenue': {
                'items': revenue_list,
                'total': total_revenue
            },
            'expenses': {
                'items': expenses_list,
                'total': total_expenses
            },
            'net_profit_loss': total_revenue - total_expenses
        }
    
    @staticmethod
    def get_project_cost_report(project_code, as_of_date=None):
        """
        Generate project cost report with budget variance
        
        Args:
            project_code: Project code
            as_of_date: Optional date (defaults to today)
        
        Returns:
            dict with costs, revenue, and variance
        """
        from django.db.models import Sum, Q
        from .models import Project
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        # Get project
        try:
            project = Project.objects.get(code=project_code)
        except Project.DoesNotExist:
            raise ValidationError(f'Project {project_code} not found')
        
        # Get actual costs
        cost_lines = JournalEntryLine.objects.filter(
            project_code=project_code,
            journal_entry__status='POSTED',
            journal_entry__date__lte=as_of_date,
            account__account_type__name='EXPENSE'
        )
        
        costs_by_account = cost_lines.values(
            'account__code',
            'account__name'
        ).annotate(
            amount=Sum('debit_amount')
        ).order_by('account__code')
        
        total_actual_cost = sum(item['amount'] for item in costs_by_account)
        
        # Get actual revenue
        revenue_lines = JournalEntryLine.objects.filter(
            project_code=project_code,
            journal_entry__status='POSTED',
            journal_entry__date__lte=as_of_date,
            account__account_type__name='REVENUE'
        )
        
        revenue_by_account = revenue_lines.values(
            'account__code',
            'account__name'
        ).annotate(
            amount=Sum('credit_amount')
        ).order_by('account__code')
        
        total_actual_revenue = sum(item['amount'] for item in revenue_by_account)
        
        return {
            'project': {
                'code': project.code,
                'name': project.name,
                'status': project.status,
                'manager': project.manager.get_full_name() if project.manager else None,
                'start_date': project.start_date,
                'end_date': project.end_date
            },
            'budget': {
                'cost': project.budgeted_cost,
                'revenue': project.budgeted_revenue,
                'profit': project.budgeted_revenue - project.budgeted_cost
            },
            'actual': {
                'cost': total_actual_cost,
                'cost_detail': list(costs_by_account),
                'revenue': total_actual_revenue,
                'revenue_detail': list(revenue_by_account),
                'profit': total_actual_revenue - total_actual_cost
            },
            'variance': {
                'cost': project.budgeted_cost - total_actual_cost,
                'cost_pct': ((project.budgeted_cost - total_actual_cost) / project.budgeted_cost * 100) 
                            if project.budgeted_cost > 0 else Decimal('0.00'),
                'revenue': total_actual_revenue - project.budgeted_revenue,
                'revenue_pct': ((total_actual_revenue - project.budgeted_revenue) / project.budgeted_revenue * 100)
                              if project.budgeted_revenue > 0 else Decimal('0.00'),
            },
            'as_of_date': as_of_date
        }

