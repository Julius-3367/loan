"""
Management command to setup initial Chart of Accounts

Creates a comprehensive Chart of Accounts for a microfinance/lending institution
following standard accounting principles.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models import Account, AccountType
from core.models import User


class Command(BaseCommand):
    help = 'Setup initial Chart of Accounts for Alba Capital'
    
    def handle(self, *args, **options):
        """Create comprehensive Chart of Accounts"""
        
        self.stdout.write(self.style.WARNING('Setting up Chart of Accounts...'))
        
        # Get or create system user
        admin_user = User.objects.filter(is_superuser=True).first()
        
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found. Please create a superuser first.'))
            return
        
        with transaction.atomic():
            accounts = [
                # ============================================
                # ASSETS (1000-1999)
                # ============================================
                
                # Current Assets (1000-1099)
                {
                    'code': '1000',
                    'name': 'Current Assets',
                    'account_type': AccountType.ASSET,
                    'is_control': True,
                    'description': 'Assets expected to be converted to cash within one year'
                },
                {
                    'code': '1010',
                    'name': 'Cash and Bank',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1000',
                    'description': 'Cash on hand and bank balances'
                },
                {
                    'code': '1015',
                    'name': 'Petty Cash',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1000',
                    'description': 'Small cash fund for minor expenses'
                },
                {
                    'code': '1020',
                    'name': 'Mobile Money - M-PESA',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1000',
                    'description': 'M-PESA business account balance'
                },
                
                # Loans Receivable (1200-1299)
                {
                    'code': '1200',
                    'name': 'Loans Receivable',
                    'account_type': AccountType.ASSET,
                    'description': 'Outstanding principal balance on loans disbursed'
                },
                {
                    'code': '1210',
                    'name': 'Interest Receivable',
                    'account_type': AccountType.ASSET,
                    'description': 'Accrued interest not yet collected'
                },
                {
                    'code': '1220',
                    'name': 'Fees Receivable',
                    'account_type': AccountType.ASSET,
                    'description': 'Accrued fees not yet collected'
                },
                {
                    'code': '1230',
                    'name': 'Penalties Receivable',
                    'account_type': AccountType.ASSET,
                    'description': 'Accrued penalties on overdue loans'
                },
                {
                    'code': '1290',
                    'name': 'Allowance for Bad Debts',
                    'account_type': AccountType.ASSET,
                    'description': 'Provision for uncollectible loans (contra-asset)'
                },
                
                # Fixed Assets (1500-1599)
                {
                    'code': '1500',
                    'name': 'Fixed Assets',
                    'account_type': AccountType.ASSET,
                    'is_control': True,
                    'description': 'Long-term tangible assets'
                },
                {
                    'code': '1510',
                    'name': 'Office Equipment',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1500',
                    'description': 'Computers, furniture, and office equipment'
                },
                {
                    'code': '1515',
                    'name': 'Accumulated Depreciation - Office Equipment',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1500',
                    'description': 'Accumulated depreciation on office equipment (contra-asset)'
                },
                {
                    'code': '1520',
                    'name': 'Motor Vehicles',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1500',
                    'description': 'Company vehicles'
                },
                {
                    'code': '1525',
                    'name': 'Accumulated Depreciation - Motor Vehicles',
                    'account_type': AccountType.ASSET,
                    'parent_code': '1500',
                    'description': 'Accumulated depreciation on vehicles (contra-asset)'
                },
                
                # ============================================
                # LIABILITIES (2000-2999)
                # ============================================
                
                # Current Liabilities (2000-2099)
                {
                    'code': '2000',
                    'name': 'Current Liabilities',
                    'account_type': AccountType.LIABILITY,
                    'is_control': True,
                    'description': 'Obligations due within one year'
                },
                {
                    'code': '2010',
                    'name': 'Accounts Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2000',
                    'description': 'Amounts owed to suppliers'
                },
                {
                    'code': '2020',
                    'name': 'Accrued Expenses',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2000',
                    'description': 'Expenses incurred but not yet paid'
                },
                {
                    'code': '2030',
                    'name': 'PAYE Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2000',
                    'description': 'Employee income tax withheld'
                },
                {
                    'code': '2040',
                    'name': 'NHIF Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2000',
                    'description': 'National Hospital Insurance Fund contributions'
                },
                {
                    'code': '2050',
                    'name': 'NSSF Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2000',
                    'description': 'National Social Security Fund contributions'
                },
                
                # Long-term Liabilities (2100-2199)
                {
                    'code': '2100',
                    'name': 'Long-term Liabilities',
                    'account_type': AccountType.LIABILITY,
                    'is_control': True,
                    'description': 'Obligations due after one year'
                },
                {
                    'code': '2110',
                    'name': 'Bank Loans Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2100',
                    'description': 'Long-term loans from banks'
                },
                {
                    'code': '2120',
                    'name': 'Investor Funds Payable',
                    'account_type': AccountType.LIABILITY,
                    'parent_code': '2100',
                    'description': 'Capital provided by investors'
                },
                
                # ============================================
                # EQUITY (3000-3999)
                # ============================================
                {
                    'code': '3000',
                    'name': 'Equity',
                    'account_type': AccountType.EQUITY,
                    'is_control': True,
                    'description': 'Owner\'s equity in the business'
                },
                {
                    'code': '3010',
                    'name': 'Share Capital',
                    'account_type': AccountType.EQUITY,
                    'parent_code': '3000',
                    'description': 'Capital invested by shareholders'
                },
                {
                    'code': '3020',
                    'name': 'Retained Earnings',
                    'account_type': AccountType.EQUITY,
                    'parent_code': '3000',
                    'description': 'Accumulated profits retained in the business'
                },
                {
                    'code': '3030',
                    'name': 'Current Year Earnings',
                    'account_type': AccountType.EQUITY,
                    'parent_code': '3000',
                    'description': 'Net income for the current fiscal year'
                },
                
                # ============================================
                # REVENUE (4000-4999)
                # ============================================
                {
                    'code': '4000',
                    'name': 'Revenue',
                    'account_type': AccountType.REVENUE,
                    'is_control': True,
                    'description': 'Income from business operations'
                },
                {
                    'code': '4010',
                    'name': 'Interest Income - Loans',
                    'account_type': AccountType.REVENUE,
                    'parent_code': '4000',
                    'description': 'Interest earned on loan products'
                },
                {
                    'code': '4020',
                    'name': 'Fee Income - Loan Fees',
                    'account_type': AccountType.REVENUE,
                    'parent_code': '4000',
                    'description': 'Fees charged on loans (application, processing, etc.)'
                },
                {
                    'code': '4025',
                    'name': 'Processing Fee Income',
                    'account_type': AccountType.REVENUE,
                    'parent_code': '4000',
                    'description': 'Processing fees on loan applications'
                },
                {
                    'code': '4030',
                    'name': 'Penalty Income',
                    'account_type': AccountType.REVENUE,
                    'parent_code': '4000',
                    'description': 'Late payment penalties'
                },
                {
                    'code': '4040',
                    'name': 'Other Income',
                    'account_type': AccountType.REVENUE,
                    'parent_code': '4000',
                    'description': 'Miscellaneous income'
                },
                
                # ============================================
                # EXPENSES (5000-5999)
                # ============================================
                {
                    'code': '5000',
                    'name': 'Operating Expenses',
                    'account_type': AccountType.EXPENSE,
                    'is_control': True,
                    'description': 'Expenses incurred in running the business'
                },
                {
                    'code': '5010',
                    'name': 'Bad Debt Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Loans written off as uncollectible'
                },
                {
                    'code': '5020',
                    'name': 'Salaries and Wages',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Employee compensation'
                },
                {
                    'code': '5030',
                    'name': 'Rent Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Office rent payments'
                },
                {
                    'code': '5040',
                    'name': 'Utilities Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Electricity, water, internet, phone'
                },
                {
                    'code': '5050',
                    'name': 'Office Supplies',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Stationery and office consumables'
                },
                {
                    'code': '5060',
                    'name': 'Marketing and Advertising',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Marketing campaigns and promotional materials'
                },
                {
                    'code': '5070',
                    'name': 'Professional Fees',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Legal, accounting, consulting fees'
                },
                {
                    'code': '5080',
                    'name': 'Depreciation Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Depreciation of fixed assets'
                },
                {
                    'code': '5090',
                    'name': 'Bank Charges',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Transaction fees and bank service charges'
                },
                {
                    'code': '5100',
                    'name': 'Interest Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Interest paid on borrowings and investor funds'
                },
                {
                    'code': '5110',
                    'name': 'Insurance Expense',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Business insurance premiums'
                },
                {
                    'code': '5120',
                    'name': 'Travel and Transport',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Travel costs for business purposes'
                },
                {
                    'code': '5130',
                    'name': 'Training and Development',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Employee training and professional development'
                },
                {
                    'code': '5999',
                    'name': 'Miscellaneous Expenses',
                    'account_type': AccountType.EXPENSE,
                    'parent_code': '5000',
                    'description': 'Other operating expenses'
                },
            ]
            
            # Track parent accounts to link children
            created_accounts = {}
            
            # Create accounts
            for account_data in accounts:
                parent_code = account_data.pop('parent_code', None)
                parent = created_accounts.get(parent_code) if parent_code else None
                
                # Check if account already exists
                existing = Account.objects.filter(code=account_data['code']).first()
                
                if existing:
                    self.stdout.write(
                        self.style.WARNING(f'  Account {account_data["code"]} - {account_data["name"]} already exists')
                    )
                    created_accounts[account_data['code']] = existing
                else:
                    account = Account.objects.create(
                        parent=parent,
                        created_by=admin_user,
                        **account_data
                    )
                    created_accounts[account_data['code']] = account
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Created: {account.code} - {account.name}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Chart of Accounts setup complete! Created {len(created_accounts)} accounts.')
            )
            
            # Display account summary
            self.stdout.write('\n' + '='*60)
            self.stdout.write(self.style.WARNING('CHART OF ACCOUNTS SUMMARY'))
            self.stdout.write('='*60)
            
            for account_type in AccountType:
                count = Account.objects.filter(account_type=account_type).count()
                self.stdout.write(f'  {account_type.label}: {count} accounts')
            
            self.stdout.write('='*60 + '\n')
