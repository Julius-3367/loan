from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from loans.models import LoanProduct


class Command(BaseCommand):
    help = 'Create sample loan products for the loan system'

    def handle(self, *args, **options):
        """Create sample loan products"""
        
        loan_products_data = [
            {
                'code': 'QSAL001',
                'name': 'Quick Salary Advance',
                'category': 'SALARY_ADVANCE',
                'description': 'Fast salary advance for employed individuals with immediate disbursement',
                'min_amount': Decimal('10000'),
                'max_amount': Decimal('50000'),
                'interest_rate': 15.0,
                'interest_method': 'REDUCING_BALANCE',
                'min_tenure_months': 1,
                'max_tenure_months': 6,
                'origination_fee_percentage': 5.0,
                'processing_fee': Decimal('500'),
                'is_active': True,
            },
            {
                'code': 'BIZ001',
                'name': 'Business Expansion Loan',
                'category': 'BUSINESS_LOAN',
                'description': 'Flexible financing for business growth and working capital needs',
                'min_amount': Decimal('50000'),
                'max_amount': Decimal('500000'),
                'interest_rate': 18.0,
                'interest_method': 'REDUCING_BALANCE',
                'min_tenure_months': 6,
                'max_tenure_months': 36,
                'origination_fee_percentage': 3.0,
                'processing_fee': Decimal('1500'),
                'is_active': True,
            },
            {
                'code': 'ASSET001',
                'name': 'Asset Finance - Vehicle',
                'category': 'ASSET_FINANCING',
                'description': 'Financing for new and used vehicle purchases with competitive rates',
                'min_amount': Decimal('100000'),
                'max_amount': Decimal('1000000'),
                'interest_rate': 12.0,
                'interest_method': 'REDUCING_BALANCE',
                'min_tenure_months': 12,
                'max_tenure_months': 48,
                'origination_fee_percentage': 2.0,
                'processing_fee': Decimal('2000'),
                'is_active': True,
            },
            {
                'code': 'PER001',
                'name': 'Emergency Personal Loan',
                'category': 'SALARY_ADVANCE',
                'description': 'Quick personal loan for emergency expenses and personal needs',
                'min_amount': Decimal('20000'),
                'max_amount': Decimal('200000'),
                'interest_rate': 20.0,
                'interest_method': 'FLAT_RATE',
                'min_tenure_months': 3,
                'max_tenure_months': 24,
                'origination_fee_percentage': 4.0,
                'processing_fee': Decimal('1000'),
                'is_active': True,
            },
            {
                'code': 'EDU001',
                'name': 'Education Finance',
                'category': 'BUSINESS_LOAN',
                'description': 'Affordable financing for education expenses and professional development',
                'min_amount': Decimal('30000'),
                'max_amount': Decimal('300000'),
                'interest_rate': 14.0,
                'interest_method': 'REDUCING_BALANCE',
                'min_tenure_months': 6,
                'max_tenure_months': 48,
                'origination_fee_percentage': 2.5,
                'processing_fee': Decimal('750'),
                'is_active': True,
            },
        ]

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for product_data in loan_products_data:
                product, created = LoanProduct.objects.update_or_create(
                    name=product_data['name'],
                    defaults=product_data
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Created loan product: {product.name}')
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'Updated loan product: {product.name}')
                    )

        total_products = LoanProduct.objects.filter(is_active=True).count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nLoan products setup complete!\n'
                f'Created: {created_count} new products\n'
                f'Updated: {updated_count} existing products\n'
                f'Total active products: {total_products}'
            )
        )
