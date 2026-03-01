"""
Accounting Service - Business logic for accounting operations

Provides high-level functions for:
- Creating journal entries
- Generating financial reports
- Account balance calculations
- Bank reconciliation
"""

from django.db import transaction
from django.db.models import Sum, Q, F
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from .models import (
    Account, JournalEntry, JournalLine, FiscalPeriod,
    AccountType, BankStatement, BankTransaction
)


class AccountingService:
    """Service class for accounting operations"""
    
    # Standard account codes - to be configured during setup
    ACCOUNTS = {
        'LOANS_RECEIVABLE': '1200',
        'CASH_BANK': '1010',
        'INTEREST_RECEIVABLE': '1210',
        'FEES_RECEIVABLE': '1220',
        'INTEREST_INCOME': '4010',
        'FEE_INCOME': '4020',
        'PENALTY_INCOME': '4030',
        'BAD_DEBT_EXPENSE': '5010',
        'PROCESSING_FEE_INCOME': '4025',
    }
    
    @classmethod
    def get_account(cls, code):
        """Get account by code"""
        try:
            return Account.objects.get(code=code)
        except Account.DoesNotExist:
            raise ValueError(f"Account {code} not found in Chart of Accounts")
    
    @classmethod
    @transaction.atomic
    def create_loan_disbursement_entry(cls, loan):
        """
        Create journal entry for loan disbursement
        
        DR: Loans Receivable
        CR: Cash/Bank
        
        Also recognize processing fees if applicable
        """
        # Get accounts
        loans_receivable = cls.get_account(cls.ACCOUNTS['LOANS_RECEIVABLE'])
        cash_bank = cls.get_account(cls.ACCOUNTS['CASH_BANK'])
        
        # Get user (use system user if loan.disbursed_by not available)
        from core.models import User
        user = getattr(loan, 'disbursed_by', None) or User.objects.filter(is_superuser=True).first()
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            entry_type=JournalEntry.EntryType.LOAN_DISBURSEMENT,
            date=loan.disbursement_date or timezone.now().date(),
            reference=f"LOAN-{loan.id}",
            description=f"Loan disbursement to {loan.customer.get_full_name()} - {loan.loan_product.name}",
            loan=loan,
            created_by=user,
            status=JournalEntry.Status.DRAFT
        )
        
        # DR: Loans Receivable (Principal + Interest + Fees)
        total_receivable = loan.principal_amount + loan.interest_amount + loan.processing_fee
        
        JournalLine.objects.create(
            journal_entry=entry,
            account=loans_receivable,
            debit=total_receivable,
            credit=Decimal('0.00'),
            description=f"Loan disbursement - Principal: {loan.principal_amount}, Interest: {loan.interest_amount}, Fee: {loan.processing_fee}"
        )
        
        # CR: Cash/Bank (Only principal disbursed)
        JournalLine.objects.create(
            journal_entry=entry,
            account=cash_bank,
            debit=Decimal('0.00'),
            credit=loan.principal_amount,
            description=f"Cash disbursed to customer"
        )
        
        # CR: Fee Income (Processing fee recognized upfront)
        if loan.processing_fee > 0:
            fee_income = cls.get_account(cls.ACCOUNTS['PROCESSING_FEE_INCOME'])
            JournalLine.objects.create(
                journal_entry=entry,
                account=fee_income,
                debit=Decimal('0.00'),
                credit=loan.processing_fee,
                description=f"Processing fee income"
            )
        
        # CR: Interest Income (Unearned interest - to be recognized over time)
        # For simplicity, we're recognizing it upfront. In accrual accounting,
        # this would go to "Unearned Interest" liability account first
        if loan.interest_amount > 0:
            interest_income = cls.get_account(cls.ACCOUNTS['INTEREST_INCOME'])
            JournalLine.objects.create(
                journal_entry=entry,
                account=interest_income,
                debit=Decimal('0.00'),
                credit=loan.interest_amount,
                description=f"Interest income on loan"
            )
        
        # Post the entry
        entry.post(user)
        
        return entry
    
    @classmethod
    @transaction.atomic
    def create_loan_repayment_entry(cls, repayment):
        """
        Create journal entry for loan repayment
        
        DR: Cash/Bank
        CR: Loans Receivable (principal portion)
        CR: Interest Income (interest portion)
        CR: Fee Income (fee portion)
        CR: Penalty Income (penalty portion)
        """
        # Get accounts
        cash_bank = cls.get_account(cls.ACCOUNTS['CASH_BANK'])
        loans_receivable = cls.get_account(cls.ACCOUNTS['LOANS_RECEIVABLE'])
        interest_income = cls.get_account(cls.ACCOUNTS['INTEREST_INCOME'])
        fee_income = cls.get_account(cls.ACCOUNTS['FEE_INCOME'])
        penalty_income = cls.get_account(cls.ACCOUNTS['PENALTY_INCOME'])
        
        # Get user
        from core.models import User
        user = getattr(repayment, 'recorded_by', None) or User.objects.filter(is_superuser=True).first()
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            entry_type=JournalEntry.EntryType.LOAN_REPAYMENT,
            date=repayment.payment_date,
            reference=f"REPAY-{repayment.id}",
            description=f"Loan repayment from {repayment.loan.customer.get_full_name()} - Receipt: {repayment.receipt_number}",
            loan=repayment.loan,
            loan_repayment=repayment,
            created_by=user,
            status=JournalEntry.Status.DRAFT
        )
        
        # DR: Cash/Bank (Total amount received)
        JournalLine.objects.create(
            journal_entry=entry,
            account=cash_bank,
            debit=repayment.amount,
            credit=Decimal('0.00'),
            description=f"Cash received via {repayment.payment_method}"
        )
        
        # CR: Loans Receivable (Principal portion)
        if repayment.principal_paid > 0:
            JournalLine.objects.create(
                journal_entry=entry,
                account=loans_receivable,
                debit=Decimal('0.00'),
                credit=repayment.principal_paid,
                description=f"Principal repayment"
            )
        
        # CR: Interest Income (Interest portion)
        if repayment.interest_paid > 0:
            JournalLine.objects.create(
                journal_entry=entry,
                account=interest_income,
                debit=Decimal('0.00'),
                credit=repayment.interest_paid,
                description=f"Interest payment"
            )
        
        # CR: Fee Income (Fee portion)
        if repayment.fee_paid > 0:
            JournalLine.objects.create(
                journal_entry=entry,
                account=fee_income,
                debit=Decimal('0.00'),
                credit=repayment.fee_paid,
                description=f"Fee payment"
            )
        
        # CR: Penalty Income (Penalty portion)
        if repayment.penalty_paid > 0:
            JournalLine.objects.create(
                journal_entry=entry,
                account=penalty_income,
                debit=Decimal('0.00'),
                credit=repayment.penalty_paid,
                description=f"Penalty payment"
            )
        
        # Post the entry
        entry.post(user)
        
        return entry
    
    @classmethod
    @transaction.atomic
    def create_loan_writeoff_entry(cls, loan, user, reason=''):
        """
        Create journal entry for loan write-off
        
        DR: Bad Debt Expense
        CR: Loans Receivable
        """
        loans_receivable = cls.get_account(cls.ACCOUNTS['LOANS_RECEIVABLE'])
        bad_debt_expense = cls.get_account(cls.ACCOUNTS['BAD_DEBT_EXPENSE'])
        
        # Calculate outstanding balance
        outstanding = loan.principal_amount - loan.principal_paid
        
        if outstanding <= 0:
            raise ValueError("No outstanding balance to write off")
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            entry_type=JournalEntry.EntryType.WRITE_OFF,
            date=timezone.now().date(),
            reference=f"WO-{loan.id}",
            description=f"Write-off of loan {loan.id} - {loan.customer.get_full_name()}. Reason: {reason}",
            loan=loan,
            created_by=user,
            status=JournalEntry.Status.DRAFT
        )
        
        # DR: Bad Debt Expense
        JournalLine.objects.create(
            journal_entry=entry,
            account=bad_debt_expense,
            debit=outstanding,
            credit=Decimal('0.00'),
            description=f"Bad debt expense recognition"
        )
        
        # CR: Loans Receivable
        JournalLine.objects.create(
            journal_entry=entry,
            account=loans_receivable,
            debit=Decimal('0.00'),
            credit=outstanding,
            description=f"Write-off of uncollectible loan"
        )
        
        # Post the entry
        entry.post(user)
        
        return entry
    
    @classmethod
    def get_trial_balance(cls, as_of_date=None):
        """
        Generate Trial Balance report
        
        Returns list of accounts with their debit/credit balances
        """
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        accounts = Account.objects.filter(is_active=True).order_by('code')
        
        trial_balance = []
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for account in accounts:
            balance = account.get_balance(as_of_date)
            
            # Determine debit or credit column based on account type and balance
            if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                debit = balance if balance >= 0 else Decimal('0.00')
                credit = abs(balance) if balance < 0 else Decimal('0.00')
            else:
                credit = balance if balance >= 0 else Decimal('0.00')
                debit = abs(balance) if balance < 0 else Decimal('0.00')
            
            if debit != 0 or credit != 0:  # Only include accounts with balance
                trial_balance.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'debit': debit,
                    'credit': credit,
                })
                total_debits += debit
                total_credits += credit
        
        return {
            'as_of_date': as_of_date,
            'accounts': trial_balance,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'is_balanced': total_debits == total_credits,
        }
    
    @classmethod
    def get_balance_sheet(cls, as_of_date=None):
        """
        Generate Balance Sheet report
        
        Assets = Liabilities + Equity
        """
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        # Get accounts by type
        assets = Account.objects.filter(
            account_type=AccountType.ASSET,
            is_active=True
        ).order_by('code')
        
        liabilities = Account.objects.filter(
            account_type=AccountType.LIABILITY,
            is_active=True
        ).order_by('code')
        
        equity = Account.objects.filter(
            account_type=AccountType.EQUITY,
            is_active=True
        ).order_by('code')
        
        # Calculate balances
        asset_list = []
        total_assets = Decimal('0.00')
        for account in assets:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                asset_list.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'balance': balance,
                })
                total_assets += balance
        
        liability_list = []
        total_liabilities = Decimal('0.00')
        for account in liabilities:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                liability_list.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'balance': balance,
                })
                total_liabilities += balance
        
        equity_list = []
        total_equity = Decimal('0.00')
        for account in equity:
            balance = account.get_balance(as_of_date)
            if balance != 0:
                equity_list.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'balance': balance,
                })
                total_equity += balance
        
        # Calculate net income for the period (Revenue - Expenses)
        # This is needed because revenue/expense accounts haven't been closed yet
        revenue_accounts = Account.objects.filter(
            account_type=AccountType.REVENUE,
            is_active=True
        )
        expense_accounts = Account.objects.filter(
            account_type=AccountType.EXPENSE,
            is_active=True
        )
        
        total_revenue = Decimal('0.00')
        for account in revenue_accounts:
            balance = account.get_balance(as_of_date)
            total_revenue += balance
        
        total_expenses = Decimal('0.00')
        for account in expense_accounts:
            balance = account.get_balance(as_of_date)
            total_expenses += balance
        
        net_income = total_revenue - total_expenses
        
        # Add net income to equity (this would normally go to Retained Earnings at period end)
        if net_income != 0:
            equity_list.append({
                'account': None,
                'code': 'NET-INCOME',
                'name': 'Net Income (Current Period)',
                'balance': net_income,
            })
            total_equity += net_income
        
        return {
            'as_of_date': as_of_date,
            'assets': asset_list,
            'total_assets': total_assets,
            'liabilities': liability_list,
            'total_liabilities': total_liabilities,
            'equity': equity_list,
            'total_equity': total_equity,
            'net_income': net_income,
            'total_liabilities_equity': total_liabilities + total_equity,
            'is_balanced': total_assets == (total_liabilities + total_equity),
        }
    
    @classmethod
    def get_income_statement(cls, start_date, end_date):
        """
        Generate Income Statement (Profit & Loss)
        
        Revenue - Expenses = Net Income
        """
        # Get revenue accounts
        revenue_accounts = Account.objects.filter(
            account_type=AccountType.REVENUE,
            is_active=True
        ).order_by('code')
        
        # Get expense accounts
        expense_accounts = Account.objects.filter(
            account_type=AccountType.EXPENSE,
            is_active=True
        ).order_by('code')
        
        # Calculate revenue
        revenue_list = []
        total_revenue = Decimal('0.00')
        
        for account in revenue_accounts:
            # Get transactions in period
            lines = account.journal_lines.filter(
                journal_entry__status=JournalEntry.Status.POSTED,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
            )
            
            credits = lines.aggregate(total=Sum('credit'))['total'] or Decimal('0.00')
            debits = lines.aggregate(total=Sum('debit'))['total'] or Decimal('0.00')
            balance = credits - debits  # Revenue is credit balance
            
            if balance != 0:
                revenue_list.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'amount': balance,
                })
                total_revenue += balance
        
        # Calculate expenses
        expense_list = []
        total_expenses = Decimal('0.00')
        
        for account in expense_accounts:
            lines = account.journal_lines.filter(
                journal_entry__status=JournalEntry.Status.POSTED,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
            )
            
            debits = lines.aggregate(total=Sum('debit'))['total'] or Decimal('0.00')
            credits = lines.aggregate(total=Sum('credit'))['total'] or Decimal('0.00')
            balance = debits - credits  # Expense is debit balance
            
            if balance != 0:
                expense_list.append({
                    'account': account,
                    'code': account.code,
                    'name': account.name,
                    'amount': balance,
                })
                total_expenses += balance
        
        net_income = total_revenue - total_expenses
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'revenue': revenue_list,
            'total_revenue': total_revenue,
            'expenses': expense_list,
            'total_expenses': total_expenses,
            'net_income': net_income,
        }
    
    @classmethod
    def get_aged_receivables(cls, as_of_date=None):
        """
        Generate Aged Receivables Report
        
        Shows loan receivables grouped by overdue buckets
        """
        from loans.models import Loan
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        active_loans = Loan.objects.filter(
            status__in=[Loan.LoanStatus.ACTIVE, Loan.LoanStatus.OVERDUE]
        )
        
        aged_receivables = {
            'current': [],
            '1_30_days': [],
            '31_60_days': [],
            '61_90_days': [],
            'over_90_days': [],
        }
        
        totals = {
            'current': Decimal('0.00'),
            '1_30_days': Decimal('0.00'),
            '31_60_days': Decimal('0.00'),
            '61_90_days': Decimal('0.00'),
            'over_90_days': Decimal('0.00'),
        }
        
        for loan in active_loans:
            outstanding = loan.outstanding_balance
            days_overdue = loan.days_overdue
            
            loan_data = {
                'loan': loan,
                'customer': loan.customer.get_full_name(),
                'outstanding': outstanding,
                'days_overdue': days_overdue,
            }
            
            if days_overdue <= 0:
                aged_receivables['current'].append(loan_data)
                totals['current'] += outstanding
            elif days_overdue <= 30:
                aged_receivables['1_30_days'].append(loan_data)
                totals['1_30_days'] += outstanding
            elif days_overdue <= 60:
                aged_receivables['31_60_days'].append(loan_data)
                totals['31_60_days'] += outstanding
            elif days_overdue <= 90:
                aged_receivables['61_90_days'].append(loan_data)
                totals['61_90_days'] += outstanding
            else:
                aged_receivables['over_90_days'].append(loan_data)
                totals['over_90_days'] += outstanding
        
        total_receivables = sum(totals.values())
        
        return {
            'as_of_date': as_of_date,
            'aged_receivables': aged_receivables,
            'totals': totals,
            'total_receivables': total_receivables,
        }
    
    @classmethod
    def get_par_report(cls, as_of_date=None):
        """
        Generate Portfolio at Risk (PAR) Report
        
        PAR = Outstanding balance of loans overdue X days / Total outstanding portfolio
        
        Returns PAR for 1, 7, 30, and 90 days
        """
        from loans.models import Loan
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        active_loans = Loan.objects.filter(
            status__in=[Loan.LoanStatus.ACTIVE, Loan.LoanStatus.OVERDUE]
        )
        
        total_portfolio = sum(loan.outstanding_balance for loan in active_loans)
        
        # Calculate PAR for different buckets
        par_buckets = {
            'PAR_1': Decimal('0.00'),
            'PAR_7': Decimal('0.00'),
            'PAR_30': Decimal('0.00'),
            'PAR_90': Decimal('0.00'),
        }
        
        for loan in active_loans:
            days_overdue = loan.days_overdue
            outstanding = loan.outstanding_balance
            
            if days_overdue >= 1:
                par_buckets['PAR_1'] += outstanding
            if days_overdue >= 7:
                par_buckets['PAR_7'] += outstanding
            if days_overdue >= 30:
                par_buckets['PAR_30'] += outstanding
            if days_overdue >= 90:
                par_buckets['PAR_90'] += outstanding
        
        # Calculate percentages
        par_percentages = {}
        for key, value in par_buckets.items():
            if total_portfolio > 0:
                par_percentages[key] = (value / total_portfolio) * 100
            else:
                par_percentages[key] = Decimal('0.00')
        
        return {
            'as_of_date': as_of_date,
            'total_portfolio': total_portfolio,
            'par_amounts': par_buckets,
            'par_percentages': par_percentages,
        }
    
    # =================================================================================
    # ADVANCED REPORTING: CASH FLOW STATEMENT, COST CENTER, PROJECT COSTING
    # =================================================================================
    
    @classmethod
    def get_cash_flow_statement(cls, fiscal_period, start_date=None, end_date=None):
        """
        Generate Statement of Cash Flows (Indirect Method)
        
        Classifies cash flow into: Operating, Investing, Financing activities
        """
        if start_date is None:
            start_date = fiscal_period.start_date
        if end_date is None:
            end_date = min(fiscal_period.end_date, timezone.now().date())
        
        # Get cash accounts (typically 1010)
        cash_accounts = Account.objects.filter(
            Q(code__startswith='1010') | Q(account_type=AccountType.ASSET, name__icontains='cash'),
            is_active=True
        )
        
        # Calculate opening and closing cash balances
        opening_balance = sum(account.get_balance(start_date) for account in cash_accounts)
        closing_balance = sum(account.get_balance(end_date) for account in cash_accounts)
        
        # Operating Activities: Calculate net income
        revenue_accounts = Account.objects.filter(account_type=AccountType.REVENUE, is_active=True)
        expense_accounts = Account.objects.filter(account_type=AccountType.EXPENSE, is_active=True)
        
        total_revenue = sum(account.get_balance(end_date) for account in revenue_accounts)
        total_expenses = sum(account.get_balance(end_date) for account in expense_accounts)
        net_income = total_revenue - total_expenses
        
        # Add back non-cash expenses (depreciation, bad debt)
        depreciation = sum(
            account.get_balance(end_date) 
            for account in expense_accounts.filter(Q(name__icontains='depreciation'))
        )
        bad_debt = sum(
            account.get_balance(end_date)
            for account in expense_accounts.filter(Q(name__icontains='bad debt'))
        )
        
        net_cash_from_operations = net_income + depreciation + bad_debt
        
        # Investing Activities: Loan disbursements (cash outflow)
        loan_disbursement_entries = JournalEntry.objects.filter(
            entry_type=JournalEntry.EntryType.LOAN_DISBURSEMENT,
            status=JournalEntry.Status.POSTED,
            entry_date__gte=start_date,
            entry_date__lte=end_date
        )
        
        loan_disbursements = sum(
            entry.lines.filter(credit__gt=0, account__code__startswith='10').aggregate(
                total=Sum('credit')
            )['total'] or Decimal('0.00')
            for entry in loan_disbursement_entries
        )
        
        # Financing Activities: Loan repayments received (cash inflow)
        loan_repayment_entries = JournalEntry.objects.filter(
            entry_type=JournalEntry.EntryType.LOAN_REPAYMENT,
            status=JournalEntry.Status.POSTED,
            entry_date__gte=start_date,
            entry_date__lte=end_date
        )
        
        loan_repayments = sum(
            entry.lines.filter(debit__gt=0, account__code__startswith='10').aggregate(
                total=Sum('debit')
            )['total'] or Decimal('0.00')
            for entry in loan_repayment_entries
        )
        
        # Calculate net cash change
        net_cash_change = net_cash_from_operations - loan_disbursements + loan_repayments
        
        return {
            'period': f"{start_date} to {end_date}",
            'opening_cash_balance': opening_balance,
            'operating_activities': {
                'net_income': net_income,
                'add_depreciation': depreciation,
                'add_bad_debt': bad_debt,
                'net_cash_from_operations': net_cash_from_operations
            },
            'investing_activities': {
                'loan_disbursements': -loan_disbursements,
                'net_cash_from_investing': -loan_disbursements
            },
            'financing_activities': {
                'loan_repayments_received': loan_repayments,
                'net_cash_from_financing': loan_repayments
            },
            'net_cash_change': net_cash_change,
            'closing_cash_balance': closing_balance,
            'calculated_closing': opening_balance + net_cash_change,
            'variance': closing_balance - (opening_balance + net_cash_change)
        }
    
    @classmethod
    def get_cost_center_report(cls, cost_center_code, as_of_date=None):
        """
        Generate cost center performance report
        Shows all expenses and revenues by cost center
        """
        from .models import CostCenter
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        try:
            cost_center = CostCenter.objects.get(code=cost_center_code)
        except CostCenter.DoesNotExist:
            raise ValueError(f"Cost center {cost_center_code} not found")
        
        # Get all journal lines for this cost center
        lines = JournalLine.objects.filter(
            cost_center_code=cost_center_code,
            journal_entry__status=JournalEntry.Status.POSTED,
            journal_entry__entry_date__lte=as_of_date
        )
        
        # Group by account
        expense_by_account = lines.filter(
            account__account_type=AccountType.EXPENSE
        ).values(
            'account__code',
            'account__name'
        ).annotate(
            total=Sum(F('debit') - F('credit'))
        ).order_by('account__code')
        
        revenue_by_account = lines.filter(
            account__account_type=AccountType.REVENUE
        ).values(
            'account__code',
            'account__name'
        ).annotate(
            total=Sum(F('credit') - F('debit'))
        ).order_by('account__code')
        
        total_expenses = sum(item['total'] for item in expense_by_account)
        total_revenue = sum(item['total'] for item in revenue_by_account)
        
        return {
            'cost_center': {
                'code': cost_center.code,
                'name': cost_center.name,
                'manager': cost_center.manager.get_full_name() if cost_center.manager else None
            },
            'as_of_date': as_of_date,
            'revenue': {
                'items': list(revenue_by_account),
                'total': total_revenue
            },
            'expenses': {
                'items': list(expense_by_account),
                'total': total_expenses
            },
            'net_profit_loss': total_revenue - total_expenses
        }
    
    @classmethod
    def get_project_cost_report(cls, project_code, as_of_date=None):
        """
        Generate project cost report with budget variance
        """
        from .models import Project
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        try:
            project = Project.objects.get(code=project_code)
        except Project.DoesNotExist:
            raise ValueError(f"Project {project_code} not found")
        
        # Get actual costs
        cost_lines = JournalLine.objects.filter(
            project_code=project_code,
            journal_entry__status=JournalEntry.Status.POSTED,
            journal_entry__entry_date__lte=as_of_date,
            account__account_type=AccountType.EXPENSE
        )
        
        costs_by_account = cost_lines.values(
            'account__code',
            'account__name'
        ).annotate(
            amount=Sum('debit')
        ).order_by('account__code')
        
        total_actual_cost = sum(item['amount'] for item in costs_by_account)
        
        return {
            'project': {
                'code': project.code,
                'name': project.name,
                'status': project.status,
                'manager': project.manager.get_full_name() if project.manager else None
            },
            'budget': {
                'cost': project.budgeted_cost,
                'revenue': project.budgeted_revenue
            },
            'actual': {
                'cost': total_actual_cost,
                'cost_detail': list(costs_by_account)
            },
            'variance': {
                'cost': project.budgeted_cost - total_actual_cost,
                'cost_pct': ((project.budgeted_cost - total_actual_cost) /project.budgeted_cost * 100) 
                           if project.budgeted_cost > 0 else Decimal('0.00')
            },
            'as_of_date': as_of_date
        }
