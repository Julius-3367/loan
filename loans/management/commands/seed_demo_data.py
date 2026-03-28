"""
seed_demo_data.py
=================
Populates the database with realistic Alba Capital demo data drawn directly
from the client questionnaire (v1.0, 18 March 2026).

Idempotent – safe to run multiple times; existing records are skipped or
updated (never duplicated).

Usage:
    python manage.py seed_demo_data            # full seed
    python manage.py seed_demo_data --flush    # wipe demo data first, then re-seed
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _d(val) -> Decimal:
    return Decimal(str(val))


def _days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


def _months_from(d: date, n: int) -> date:
    import calendar
    month = d.month + n
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(d.day, max_day))


# ─────────────────────────────────────────────────────────────────────────────
# Loan products — exact terms per questionnaire Section C
# ─────────────────────────────────────────────────────────────────────────────

PRODUCT_SPECS = [
    {
        "code": "SAL001",
        "name": "Salary Advance",
        "category": "salary_advance",
        "description": (
            "Short-term salary advance for employed individuals. "
            "Flat interest 10%/month; 3.5% processing fee; 1.5% insurance fee; "
            "1-month grace period. Requires employer verification."
        ),
        "min_amount": _d(5_000),
        "max_amount": _d(100_000),
        "min_tenure_months": 1,
        "max_tenure_months": 1,
        "interest_rate": _d("10.00"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("5.00"),   # 3.5% processing + 1.5% insurance
        "processing_fee": _d(0),
        "penalty_rate": _d("15.00"),
        "grace_period_days": 30,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": True,
        "is_fee_based": False,
        "is_active": True,
    },
    {
        "code": "BIZ001",
        "name": "Business Loan",
        "category": "business_loan",
        "description": (
            "Working capital & growth loans for individuals and SMEs. "
            "Flat rate 10%/month; 10% origination fee; 15% penalty; 1-month grace."
        ),
        "min_amount": _d(100_000),
        "max_amount": _d(500_000),
        "min_tenure_months": 1,
        "max_tenure_months": 12,
        "interest_rate": _d("10.00"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("10.00"),
        "processing_fee": _d(0),
        "penalty_rate": _d("15.00"),
        "grace_period_days": 30,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": True,
        "requires_employer_verification": False,
        "is_fee_based": False,
        "is_active": True,
    },
    {
        "code": "PERS001",
        "name": "Personal Loan",
        "category": "personal_loan",
        "description": (
            "Consumer loans for school fees, medical bills, etc. "
            "Flat rate 10%/month; 3.5% processing + 1.5% insurance; 15% penalty; "
            "1-month grace."
        ),
        "min_amount": _d(10_000),
        "max_amount": _d(100_000),
        "min_tenure_months": 1,
        "max_tenure_months": 12,
        "interest_rate": _d("10.00"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("5.00"),   # 3.5 + 1.5
        "processing_fee": _d(0),
        "penalty_rate": _d("15.00"),
        "grace_period_days": 30,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": False,
        "is_fee_based": False,
        "is_active": True,
    },
    {
        "code": "IPF001",
        "name": "IPF Loan",
        "category": "personal_loan",
        "description": (
            "Invoice Purchase Finance / LPO financing. "
            "10% per annum on reducing balance; repayable on completion."
        ),
        "min_amount": _d(50_000),
        "max_amount": _d(2_000_000),
        "min_tenure_months": 1,
        "max_tenure_months": 12,
        "interest_rate": _d("10.00"),
        "interest_method": "REDUCING_BALANCE",
        "origination_fee_percentage": _d("0"),
        "processing_fee": _d(0),
        "penalty_rate": _d("5.00"),
        "grace_period_days": 0,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": False,
        "is_fee_based": False,
        "is_active": True,
    },
    {
        "code": "BID001",
        "name": "Bid Bond",
        "category": "bid_bond",
        "description": (
            "Fee-based product for contractors requiring tender/bid bonds. "
            "1.5% flat fee on bond value; no interest; repayable on completion."
        ),
        "min_amount": _d(100_000),
        "max_amount": _d(10_000_000),
        "min_tenure_months": 1,
        "max_tenure_months": 12,
        "interest_rate": _d("0"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("1.50"),
        "processing_fee": _d(0),
        "penalty_rate": _d("0"),
        "grace_period_days": 0,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": False,
        "is_fee_based": True,
        "is_active": True,
    },
    {
        "code": "PERF001",
        "name": "Performance Bond",
        "category": "performance_bond",
        "description": (
            "Fee-based product for contractors requiring performance guarantees. "
            "1% flat fee on bond value."
        ),
        "min_amount": _d(100_000),
        "max_amount": _d(10_000_000),
        "min_tenure_months": 1,
        "max_tenure_months": 12,
        "interest_rate": _d("0"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("1.00"),
        "processing_fee": _d(0),
        "penalty_rate": _d("0"),
        "grace_period_days": 0,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": False,
        "is_fee_based": True,
        "is_active": True,
    },
    {
        "code": "STAFF001",
        "name": "Staff Loan",
        "category": "staff_loan",
        "description": (
            "Internal staff loans: Personal, Emergency, Asset, Education. "
            "5% reducing balance; deducted monthly from payroll; max 50% of gross salary."
        ),
        "min_amount": _d(5_000),
        "max_amount": _d(500_000),
        "min_tenure_months": 1,
        "max_tenure_months": 24,
        "interest_rate": _d("5.00"),
        "interest_method": "REDUCING_BALANCE",
        "origination_fee_percentage": _d("0"),
        "processing_fee": _d(0),
        "penalty_rate": _d("2.00"),
        "grace_period_days": 0,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": False,
        "requires_employer_verification": False,
        "is_fee_based": False,
        "is_active": True,
    },
    {
        "code": "ASSET001",
        "name": "Asset Finance",
        "category": "asset_financing",
        "description": (
            "Asset and equipment financing. Staff: 5% reducing balance. "
            "Clients: 10% flat rate. Repayable monthly."
        ),
        "min_amount": _d(100_000),
        "max_amount": _d(5_000_000),
        "min_tenure_months": 6,
        "max_tenure_months": 48,
        "interest_rate": _d("10.00"),
        "interest_method": "FLAT_RATE",
        "origination_fee_percentage": _d("2.00"),
        "processing_fee": _d(0),
        "penalty_rate": _d("5.00"),
        "grace_period_days": 0,
        "default_repayment_frequency": "MONTHLY",
        "requires_guarantor": True,
        "requires_employer_verification": False,
        "is_fee_based": False,
        "is_active": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Staff — real names from questionnaire Section B
# ─────────────────────────────────────────────────────────────────────────────

STAFF_USERS = [
    {
        "email": "martin.gichovi@albacapital.co.ke",
        "first_name": "Martin",
        "last_name": "Gichovi",
        "role": "ADMIN",
        "is_staff": True,
        "is_superuser": True,
        "phone": "+254700000001",
        "is_approved": True,
    },
    {
        "email": "faith.nduta@albacapital.co.ke",
        "first_name": "Faith",
        "last_name": "Nduta",
        "role": "ADMIN",
        "is_staff": True,
        "is_superuser": True,
        "phone": "+254700000002",
        "is_approved": True,
    },
    {
        "email": "edwin.kipkoech@albacapital.co.ke",
        "first_name": "Edwin",
        "last_name": "Kipkoech",
        "role": "MANAGEMENT",
        "is_staff": True,
        "is_superuser": False,
        "phone": "+254700000003",
        "is_approved": True,
    },
    {
        "email": "benson.chiro@albacapital.co.ke",
        "first_name": "Benson",
        "last_name": "Chiro",
        "role": "FINANCE_OFFICER",
        "is_staff": True,
        "is_superuser": False,
        "phone": "+254700000004",
        "is_approved": True,
    },
    {
        "email": "gaudancia@albacapital.co.ke",
        "first_name": "Gaudancia",
        "last_name": "Wanjiku",
        "role": "CREDIT_OFFICER",
        "is_staff": True,
        "is_superuser": False,
        "phone": "+254700000005",
        "is_approved": True,
    },
    {
        "email": "phemmy@albacapital.co.ke",
        "first_name": "Phemmy",
        "last_name": "Achieng",
        "role": "FINANCE_OFFICER",
        "is_staff": True,
        "is_superuser": False,
        "phone": "+254700000006",
        "is_approved": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Demo customers — 25 Kenyan names across employer & sector segments
# ─────────────────────────────────────────────────────────────────────────────

CUSTOMERS = [
    # Salaried – Government
    {"first": "James",   "last": "Kamau",    "email": "james.kamau@demo.ac.ke",    "id": "12345678",  "dob": date(1985, 3, 12), "employer": "Kenya Revenue Authority",       "income": 85_000,  "bank": "KCB Bank",     "account": "1183721001", "status": "EMPLOYED",      "sector": "government",   "city": "Nairobi"},
    {"first": "Mary",    "last": "Njeri",    "email": "mary.njeri@demo.ac.ke",     "id": "23456789",  "dob": date(1990, 7, 22), "employer": "Nairobi County Government",    "income": 62_000,  "bank": "Equity Bank",  "account": "0192837465", "status": "EMPLOYED",      "sector": "government",   "city": "Nairobi"},
    {"first": "Peter",   "last": "Ochieng",  "email": "peter.ochieng@demo.ac.ke",  "id": "34567890",  "dob": date(1982, 11, 5), "employer": "Kenya Power",                  "income": 95_000,  "bank": "Stanbic Bank", "account": "9182736455", "status": "EMPLOYED",      "sector": "government",   "city": "Nairobi"},
    # Salaried – Private
    {"first": "Grace",   "last": "Wangari",  "email": "grace.wangari@demo.ac.ke",  "id": "45678901",  "dob": date(1993, 2, 14), "employer": "Safaricom PLC",                "income": 120_000, "bank": "ABSA Bank",    "account": "4029384756", "status": "EMPLOYED",      "sector": "services",     "city": "Nairobi"},
    {"first": "Samuel",  "last": "Mutua",    "email": "samuel.mutua@demo.ac.ke",   "id": "56789012",  "dob": date(1988, 8, 30), "employer": "Equity Bank Kenya",            "income": 140_000, "bank": "Equity Bank",  "account": "5019283746", "status": "EMPLOYED",      "sector": "services",     "city": "Nairobi"},
    {"first": "Elizabeth","last":"Otieno",   "email": "elizabeth.otieno@demo.ac.ke","id": "67890123", "dob": date(1987, 5, 18), "employer": "Nation Media Group",            "income": 75_000,  "bank": "Co-op Bank",   "account": "6108374651", "status": "EMPLOYED",      "sector": "services",     "city": "Nairobi"},
    {"first": "Daniel",  "last": "Kimani",   "email": "daniel.kimani@demo.ac.ke",  "id": "78901234",  "dob": date(1991, 9, 7),  "employer": "Bidco Africa",                 "income": 68_000,  "bank": "KCB Bank",     "account": "7201938465", "status": "EMPLOYED",      "sector": "manufacturing","city": "Thika"},
    {"first": "Agnes",   "last": "Mwangi",   "email": "agnes.mwangi@demo.ac.ke",   "id": "89012345",  "dob": date(1983, 12, 25),"employer": "Nairobi Hospital",             "income": 110_000, "bank": "ABSA Bank",    "account": "8291837462", "status": "EMPLOYED",      "sector": "health",       "city": "Nairobi"},
    {"first": "John",    "last": "Kariuki",  "email": "john.kariuki@demo.ac.ke",   "id": "90123456",  "dob": date(1986, 4, 3),  "employer": "Uchumi Supermarkets",          "income": 52_000,  "bank": "Stanbic Bank", "account": "9103827461", "status": "EMPLOYED",      "sector": "trade",        "city": "Nairobi"},
    # Self-employed / Business owners
    {"first": "Rose",    "last": "Adhiambo", "email": "rose.adhiambo@demo.ac.ke",  "id": "01234567",  "dob": date(1980, 6, 17), "employer": "Adhiambo Enterprises",        "income": 180_000, "bank": "Equity Bank",  "account": "0293847162", "status": "SELF_EMPLOYED", "sector": "trade",        "city": "Kisumu"},
    {"first": "Michael", "last": "Njoroge",  "email": "michael.njoroge@demo.ac.ke","id": "11234567",  "dob": date(1978, 10, 9), "employer": "Njoroge Hardware Ltd",         "income": 250_000, "bank": "KCB Bank",     "account": "1102938475", "status": "SELF_EMPLOYED", "sector": "construction", "city": "Nakuru"},
    {"first": "Alice",   "last": "Auma",     "email": "alice.auma@demo.ac.ke",     "id": "21234567",  "dob": date(1989, 1, 28), "employer": "Auma Fashion House",           "income": 95_000,  "bank": "Co-op Bank",   "account": "2201938471", "status": "SELF_EMPLOYED", "sector": "trade",        "city": "Kisumu"},
    {"first": "Robert",  "last": "Waweru",   "email": "robert.waweru@demo.ac.ke",  "id": "31234567",  "dob": date(1975, 3, 31), "employer": "Waweru Transport Ltd",         "income": 320_000, "bank": "ABSA Bank",    "account": "3302019384", "status": "SELF_EMPLOYED", "sector": "transport",    "city": "Nairobi"},
    {"first": "Esther",  "last": "Oduya",    "email": "esther.oduya@demo.ac.ke",   "id": "41234567",  "dob": date(1992, 8, 12), "employer": "Oduya Agribusiness",           "income": 145_000, "bank": "KCB Bank",     "account": "4401938472", "status": "SELF_EMPLOYED", "sector": "agriculture",  "city": "Eldoret"},
    # Teachers / Education
    {"first": "Patrick", "last": "Njuguna",  "email": "patrick.njuguna@demo.ac.ke","id": "51234567",  "dob": date(1984, 5, 20), "employer": "TSC Kenya",                    "income": 72_000,  "bank": "Equity Bank",  "account": "5501938473", "status": "EMPLOYED",      "sector": "education",    "city": "Nyeri"},
    {"first": "Lucy",    "last": "Chebet",   "email": "lucy.chebet@demo.ac.ke",    "id": "61234567",  "dob": date(1994, 11, 3), "employer": "Alliance High School",         "income": 58_000,  "bank": "Co-op Bank",   "account": "6601938474", "status": "EMPLOYED",      "sector": "education",    "city": "Kikuyu"},
    # Contractors (for bid bonds)
    {"first": "Hassan",  "last": "Omar",     "email": "hassan.omar@demo.ac.ke",    "id": "71234567",  "dob": date(1979, 7, 15), "employer": "Omar Construction Co.",        "income": 450_000, "bank": "Stanbic Bank", "account": "7701938475", "status": "SELF_EMPLOYED", "sector": "construction", "city": "Mombasa"},
    {"first": "Faith",   "last": "Makena",   "email": "faith.makena@demo.ac.ke",   "id": "81234567",  "dob": date(1987, 2, 9),  "employer": "Makena Supplies Ltd",          "income": 210_000, "bank": "KCB Bank",     "account": "8801938476", "status": "SELF_EMPLOYED", "sector": "construction", "city": "Meru"},
    # NGO workers
    {"first": "Brian",   "last": "Omondi",   "email": "brian.omondi@demo.ac.ke",   "id": "91234567",  "dob": date(1991, 4, 25), "employer": "Kenya Red Cross",              "income": 88_000,  "bank": "Equity Bank",  "account": "9901938477", "status": "EMPLOYED",      "sector": "health",       "city": "Nairobi"},
    # Overdue / NPL scenario
    {"first": "Joseph",  "last": "Gitau",    "email": "joseph.gitau@demo.ac.ke",   "id": "02345678",  "dob": date(1983, 9, 6),  "employer": "Self Employed",                "income": 65_000,  "bank": "Co-op Bank",   "account": "0091938478", "status": "SELF_EMPLOYED", "sector": "trade",        "city": "Nairobi"},
    # Fully paid scenario
    {"first": "Caroline","last": "Wairimu",  "email": "caroline.wairimu@demo.ac.ke","id": "12340001", "dob": date(1990, 6, 14), "employer": "Kengen",                       "income": 130_000, "bank": "ABSA Bank",    "account": "1200938401", "status": "EMPLOYED",      "sector": "government",   "city": "Nairobi"},
    # Extra diversity
    {"first": "Victor",  "last": "Korir",    "email": "victor.korir@demo.ac.ke",   "id": "22340001",  "dob": date(1988, 12, 1), "employer": "Finserve Africa",              "income": 165_000, "bank": "KCB Bank",     "account": "2200938402", "status": "EMPLOYED",      "sector": "services",     "city": "Nairobi"},
    {"first": "Mercy",   "last": "Akinyi",   "email": "mercy.akinyi@demo.ac.ke",   "id": "32340001",  "dob": date(1995, 3, 8),  "employer": "Twiga Foods",                  "income": 55_000,  "bank": "Equity Bank",  "account": "3300938403", "status": "EMPLOYED",      "sector": "agriculture",  "city": "Nairobi"},
    {"first": "Isaac",   "last": "Rotich",   "email": "isaac.rotich@demo.ac.ke",   "id": "42340001",  "dob": date(1981, 8, 22), "employer": "Rotich Logistics",             "income": 290_000, "bank": "Stanbic Bank", "account": "4400938404", "status": "SELF_EMPLOYED", "sector": "transport",    "city": "Eldoret"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Investors — 10 accounts across individual + corporate
# ─────────────────────────────────────────────────────────────────────────────

INVESTORS = [
    {"first": "David",    "last": "Njogu",     "email": "david.njogu@investor.ac.ke",     "id": "INV12345", "phone": "+254711100001", "bank": "KCB Bank",     "account": "5500000001", "amount": 500_000,  "rate": "12.00", "months": 12},
    {"first": "Priscilla","last": "Wanjiku",   "email": "priscilla.wanjiku@investor.ac.ke","id": "INV23456","phone": "+254711100002", "bank": "Equity Bank",  "account": "5500000002", "amount": 1_000_000,"rate": "13.00", "months": 24},
    {"first": "Kenneth",  "last": "Owino",     "email": "kenneth.owino@investor.ac.ke",   "id": "INV34567", "phone": "+254711100003", "bank": "ABSA Bank",    "account": "5500000003", "amount": 250_000,  "rate": "11.50", "months": 6},
    {"first": "Teresa",   "last": "Muthoni",   "email": "teresa.muthoni@investor.ac.ke",  "id": "INV45678", "phone": "+254711100004", "bank": "Stanbic Bank", "account": "5500000004", "amount": 750_000,  "rate": "12.50", "months": 12},
    {"first": "Collins",  "last": "Otiende",   "email": "collins.otiende@investor.ac.ke", "id": "INV56789", "phone": "+254711100005", "bank": "Co-op Bank",   "account": "5500000005", "amount": 2_000_000,"rate": "14.00", "months": 36},
    {"first": "Angela",   "last": "Wambua",    "email": "angela.wambua@investor.ac.ke",   "id": "INV67890", "phone": "+254711100006", "bank": "KCB Bank",     "account": "5500000006", "amount": 300_000,  "rate": "12.00", "months": 12},
    {"first": "Bernard",  "last": "Ogola",     "email": "bernard.ogola@investor.ac.ke",   "id": "INV78901", "phone": "+254711100007", "bank": "Equity Bank",  "account": "5500000007", "amount": 1_500_000,"rate": "13.50", "months": 24},
    {"first": "Hilda",    "last": "Mwende",    "email": "hilda.mwende@investor.ac.ke",    "id": "INV89012", "phone": "+254711100008", "bank": "ABSA Bank",    "account": "5500000008", "amount": 400_000,  "rate": "12.00", "months": 12},
    {"first": "Silas",    "last": "Kipchoge",  "email": "silas.kipchoge@investor.ac.ke",  "id": "INV90123", "phone": "+254711100009", "bank": "Stanbic Bank", "account": "5500000009", "amount": 5_000_000,"rate": "14.50", "months": 36},
    {"first": "Naomi",    "last": "Aloo",      "email": "naomi.aloo@investor.ac.ke",      "id": "INV01234", "phone": "+254711100010", "bank": "KCB Bank",     "account": "5500000010", "amount": 600_000,  "rate": "12.50", "months": 18},
]


class Command(BaseCommand):
    help = "Seed realistic Alba Capital demo data from client questionnaire."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all demo data before re-seeding (keeps superuser admin@alba.local).",
        )

    # ─────────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        from core.models import User
        from loans.models import (
            Customer,
            Investment,
            InvestmentTransaction,
            InvestorProfile,
            Loan,
            LoanApplication,
            LoanProduct,
            LoanRepayment,
            Notification,
            RepaymentSchedule,
        )

        if options["flush"]:
            self._flush(User)

        with transaction.atomic():
            admin_user = self._get_admin(User)
            products = self._seed_products(LoanProduct, admin_user)
            staff_map = self._seed_staff(User)
            customers = self._seed_customers(User, Customer, staff_map, products)
            self._seed_loans(
                customers, products, staff_map,
                LoanApplication, Loan, LoanRepayment, RepaymentSchedule, Notification,
                User
            )
            self._seed_investors(User, InvestorProfile, Investment, InvestmentTransaction)

        self.stdout.write(self.style.SUCCESS("\n✓ Demo data seed complete.\n"))

    # ─────────────────────────────────────────────────────────────────────
    def _flush(self, User):
        self.stdout.write("  Flushing demo data…")
        from loans.models import (
            Investment, InvestmentTransaction, InvestorProfile,
            Loan, LoanApplication, LoanRepayment, RepaymentSchedule,
            Customer, Notification,
        )
        LoanRepayment.objects.all().delete()
        RepaymentSchedule.objects.all().delete()
        Loan.objects.all().delete()
        LoanApplication.objects.all().delete()
        Notification.objects.all().delete()
        InvestmentTransaction.objects.all().delete()
        Investment.objects.all().delete()
        InvestorProfile.objects.all().delete()
        Customer.objects.all().delete()
        User.objects.filter(email__endswith="@demo.ac.ke").delete()
        User.objects.filter(email__endswith="@investor.ac.ke").delete()
        User.objects.filter(email__endswith="@albacapital.co.ke").delete()
        self.stdout.write("  Done flushing.\n")

    # ─────────────────────────────────────────────────────────────────────
    def _get_admin(self, User):
        admin = User.objects.filter(is_superuser=True).order_by("id").first()
        if not admin:
            admin = User.objects.create_superuser(
                email="admin@alba.local",
                password="Admin@1234",
                first_name="System",
                last_name="Admin",
            )
        return admin

    # ─────────────────────────────────────────────────────────────────────
    def _seed_products(self, LoanProduct, admin_user):
        self.stdout.write("  Seeding loan products…")
        products = {}
        for spec in PRODUCT_SPECS:
            obj, created = LoanProduct.objects.update_or_create(
                code=spec["code"],
                defaults={**spec, "created_by": admin_user},
            )
            products[spec["code"]] = obj
            verb = "Created" if created else "Updated"
            self.stdout.write(f"    {verb}: {obj.name}")
        return products

    # ─────────────────────────────────────────────────────────────────────
    def _seed_staff(self, User):
        self.stdout.write("  Seeding staff users…")
        staff_map = {}
        pw = make_password("Staff@1234")
        for s in STAFF_USERS:
            obj, created = User.objects.update_or_create(
                email=s["email"],
                defaults={
                    "first_name": s["first_name"],
                    "last_name": s["last_name"],
                    "role": s["role"],
                    "is_staff": s["is_staff"],
                    "is_superuser": s["is_superuser"],
                    "phone": s.get("phone", ""),
                    "is_approved": True,
                    "password": pw,
                },
            )
            staff_map[s["role"]] = obj          # last one of each role wins
            staff_map[s["email"]] = obj          # also by email
            self.stdout.write(f"    {'Created' if created else 'Exists'}: {obj.get_full_name()} ({obj.role})")
        return staff_map

    # ─────────────────────────────────────────────────────────────────────
    def _seed_customers(self, User, Customer, staff_map, products):
        self.stdout.write("  Seeding customers…")
        pw = make_password("Customer@1234")
        kyc_verifier = staff_map.get("CREDIT_OFFICER") or staff_map.get("MANAGEMENT")
        customers = []

        for i, c in enumerate(CUSTOMERS):
            user, _ = User.objects.update_or_create(
                email=c["email"],
                defaults={
                    "first_name": c["first"],
                    "last_name": c["last"],
                    "role": "CUSTOMER",
                    "is_approved": True,
                    "phone": f"+2547{str(20000001 + i)[1:]}",
                    "password": pw,
                },
            )
            # Decide KYC status based on index
            kyc_ok = i < len(CUSTOMERS) - 4  # last 4 pending
            profile, _ = Customer.objects.update_or_create(
                user=user,
                defaults={
                    "date_of_birth": c["dob"],
                    "id_number": c["id"],
                    "address": f"P.O Box {1000 + i}, {c['city']}",
                    "county": _city_to_county(c["city"]),
                    "city": c["city"],
                    "employment_status": c["status"],
                    "employer_name": c["employer"],
                    "monthly_income": _d(c["income"]),
                    "bank_name": c["bank"],
                    "bank_account": c["account"],
                    "kyc_verified": kyc_ok,
                    "kyc_verified_by": kyc_verifier if kyc_ok else None,
                    "kyc_verified_at": timezone.now() - timedelta(days=random.randint(10, 120)) if kyc_ok else None,
                    "national_id_verified": kyc_ok,
                    "bank_statement_verified": kyc_ok,
                },
            )
            customers.append(profile)
            self.stdout.write(f"    Customer: {user.get_full_name()} ({'KYC OK' if kyc_ok else 'KYC pending'})")

        return customers

    # ─────────────────────────────────────────────────────────────────────
    def _seed_loans(
        self, customers, products, staff_map,
        LoanApplication, Loan, LoanRepayment, RepaymentSchedule, Notification,
        User,
    ):
        self.stdout.write("  Seeding loan applications and loans…")
        officer = staff_map.get("CREDIT_OFFICER")
        manager = staff_map.get("MANAGEMENT")

        scenarios = [
            # (customer_idx, product_code, amount, months, status, days_disbursed_ago, payments_made)
            # Active loans with repayments
            (0,  "SAL001",  50_000,   1,  "DISBURSED",  35,  1),
            (1,  "PERS001", 80_000,   6,  "DISBURSED",  95,  3),
            (2,  "BIZ001",  300_000,  12, "DISBURSED",  180, 6),
            (3,  "SAL001",  75_000,   1,  "DISBURSED",  25,  1),
            (4,  "PERS001", 60_000,   3,  "DISBURSED",  70,  2),
            (5,  "BIZ001",  200_000,  6,  "DISBURSED",  130, 4),
            (6,  "SAL001",  40_000,   1,  "DISBURSED",  15,  0),
            (7,  "PERS001", 100_000,  12, "DISBURSED",  200, 6),
            (8,  "IPF001",  150_000,  6,  "DISBURSED",  90,  3),
            (9,  "BIZ001",  400_000,  12, "DISBURSED",  65,  2),
            # Bid bonds / performance bonds
            (16, "BID001",  500_000,  6,  "DISBURSED",  40,  0),
            (17, "PERF001", 750_000,  6,  "DISBURSED",  20,  0),
            # Pending / in-pipeline applications
            (10, "BIZ001",  250_000,  6,  "UNDER_REVIEW",    0,  0),
            (11, "BIZ001",  350_000,  12, "CREDIT_ANALYSIS", 0,  0),
            (12, "PERS001", 45_000,   3,  "SUBMITTED",       0,  0),
            (13, "IPF001",  800_000,  12, "PENDING_APPROVAL",0,  0),
            (14, "SAL001",  30_000,   1,  "SUBMITTED",       0,  0),
            (15, "PERS001", 70_000,   6,  "DRAFT",           0,  0),
            # Overdue / stressed scenario
            (19, "BIZ001",  180_000,  6,  "DISBURSED",  130, 1),   # Joseph – 1 payment then stopped
            # Fully paid
            (20, "SAL001",  60_000,   1,  "DISBURSED",  65,  1),   # Caroline – fully paid
            # Extra active
            (21, "PERS001", 90_000,   6,  "DISBURSED",  50,  1),
            (22, "SAL001",  35_000,   1,  "DISBURSED",  30,  1),
            (23, "ASSET001",500_000,  24, "DISBURSED",  120, 4),
        ]

        for idx, (cust_i, prod_code, amount, months, target_status, days_ago_dis, payments) in enumerate(scenarios):
            if cust_i >= len(customers):
                continue
            customer = customers[cust_i]
            product = products.get(prod_code)
            if not product:
                continue

            app_num = f"LA-DEMO-{idx + 1:04d}"
            if LoanApplication.objects.filter(application_number=app_num).exists():
                self.stdout.write(f"    Skip (exists): {app_num}")
                continue

            dis_date = _days_ago(days_ago_dis) if target_status == "DISBURSED" else None

            # === Create Application ===
            app = LoanApplication(
                application_number=app_num,
                customer=customer,
                loan_product=product,
                requested_amount=_d(amount),
                approved_amount=_d(amount) if target_status == "DISBURSED" else None,
                tenure_months=months,
                repayment_frequency=product.default_repayment_frequency,
                purpose=_loan_purpose(prod_code),
                reviewed_by=officer,
                approved_by=manager if target_status in ("DISBURSED", "APPROVED", "PENDING_APPROVAL") else None,
                reviewed_at=timezone.now() - timedelta(days=days_ago_dis + 5) if target_status == "DISBURSED" else None,
                approved_at=timezone.now() - timedelta(days=days_ago_dis + 2) if target_status == "DISBURSED" else None,
                submitted_at=timezone.now() - timedelta(days=days_ago_dis + 7) if days_ago_dis else timezone.now() - timedelta(days=random.randint(1, 5)),
                disbursed_at=timezone.make_aware(timezone.datetime.combine(dis_date, timezone.datetime.min.time())) if dis_date else None,
                internal_notes=f"Demo application – {product.name}",
            )
            # Force status
            app.status = "DISBURSED" if target_status == "DISBURSED" else target_status
            app.save()

            if target_status != "DISBURSED":
                self.stdout.write(f"    Application {app_num}: {customer.user.get_full_name()} → {target_status}")
                # In-portal notification for submitted apps
                if target_status in ("SUBMITTED", "UNDER_REVIEW", "CREDIT_ANALYSIS", "PENDING_APPROVAL"):
                    Notification.objects.get_or_create(
                        user=customer.user,
                        notification_type="APPLICATION_SUBMITTED",
                        loan_application=app,
                        defaults={
                            "title": "Application Received",
                            "message": f"Your application {app_num} is {app.get_status_display()}.",
                            "priority": "MEDIUM",
                        },
                    )
                continue

            # === Calculate loan financials ===
            principal = _d(amount)
            rate = product.interest_rate / _d(100)
            if product.interest_method == "FLAT_RATE":
                total_interest = principal * rate * _d(months)
            else:
                total_interest = principal * rate * _d(months) * _d("0.5")

            total_fees = (principal * product.origination_fee_percentage / _d(100)) + product.processing_fee
            total_payable = principal + total_interest + total_fees
            instalment = (total_payable / _d(months)).quantize(_d("0.01"))

            first_pay = _months_from(dis_date, 1)
            maturity = _months_from(dis_date, months)

            # === Create Loan ===
            loan = Loan.objects.create(
                application=app,
                customer=customer,
                loan_product=product,
                principal_amount=principal,
                interest_amount=total_interest,
                fees=total_fees,
                total_amount=total_payable,
                outstanding_balance=total_payable,
                installment_amount=instalment,
                repayment_frequency=product.default_repayment_frequency,
                tenure_months=months,
                disbursement_date=dis_date,
                first_payment_date=first_pay,
                maturity_date=maturity,
                next_payment_date=_months_from(dis_date, payments + 1),
                disbursed_by=manager,
                disbursement_method="Bank Transfer",
                disbursement_reference=f"REF-DEMO-{idx + 1:04d}",
                status="ACTIVE",
            )

            # === Generate Repayment Schedule ===
            for i in range(1, months + 1):
                due = _months_from(dis_date, i)
                RepaymentSchedule.objects.get_or_create(
                    loan=loan,
                    installment_number=i,
                    defaults={
                        "due_date": due,
                        "principal_due": (principal / _d(months)).quantize(_d("0.01")),
                        "interest_due": (total_interest / _d(months)).quantize(_d("0.01")),
                        "fees_due": (total_fees / _d(months)).quantize(_d("0.01")),
                        "total_due": instalment,
                        "is_paid": i <= payments,
                        "paid_date": (timezone.now() - timedelta(days=(months - i) * 30 + 5)).date() if i <= payments else None,
                    },
                )

            # === Record Repayments ===
            running_balance = total_payable
            for i in range(1, payments + 1):
                pay_date = _months_from(dis_date, i)
                method = random.choice(["M_PESA", "BANK_TRANSFER", "BANK_TRANSFER"])
                ref = f"MPE{random.randint(1000000, 9999999)}" if method == "M_PESA" else f"EFT{random.randint(10000000, 99999999)}"
                paid_principal = (principal / _d(months)).quantize(_d("0.01"))
                paid_interest = (total_interest / _d(months)).quantize(_d("0.01"))
                paid_fees = (total_fees / _d(months)).quantize(_d("0.01"))
                paid_amount = paid_principal + paid_interest + paid_fees
                running_balance -= paid_amount

                rcpt = f"RCP-DEMO-{idx + 1:04d}-{i:02d}"
                LoanRepayment.objects.get_or_create(
                    receipt_number=rcpt,
                    defaults={
                        "loan": loan,
                        "payment_date": pay_date,
                        "amount": paid_amount,
                        "payment_type": "REGULAR_PAYMENT",
                        "payment_method": method,
                        "reference_number": ref,
                        "principal_paid": paid_principal,
                        "interest_paid": paid_interest,
                        "penalty_paid": _d(0),
                        "processed_by": manager,
                        "notes": f"Demo payment #{i}",
                    },
                )

            # Update loan outstanding balance
            fully_paid = payments == months
            loan.outstanding_balance = max(_d(0), running_balance.quantize(_d("0.01")))
            loan.last_payment_date = _months_from(dis_date, payments) if payments > 0 else None
            # Overdue scenario for cust idx 19 (Joseph Gitau)
            if cust_i == 19:
                loan.status = "OVERDUE"
                loan.days_overdue = max(0, (date.today() - _months_from(dis_date, 2)).days)
            elif fully_paid:
                loan.status = "PAID"
                loan.outstanding_balance = _d(0)
            loan.save(update_fields=["outstanding_balance", "last_payment_date", "status", "days_overdue"])

            # Disbursement notification
            Notification.objects.get_or_create(
                user=customer.user,
                notification_type="LOAN_DISBURSED",
                loan=loan,
                defaults={
                    "title": "Loan Disbursed",
                    "message": f"Loan {loan.loan_number} of KES {principal:,} has been disbursed to your account.",
                    "priority": "HIGH",
                },
            )

            self.stdout.write(
                f"    Loan {loan.loan_number}: {customer.user.get_full_name()} | "
                f"KES {principal:,} | {payments}/{months} payments | {loan.status}"
            )

    # ─────────────────────────────────────────────────────────────────────
    def _seed_investors(self, User, InvestorProfile, Investment, InvestmentTransaction):
        self.stdout.write("  Seeding investor accounts…")
        pw = make_password("Investor@1234")

        for idx, inv in enumerate(INVESTORS):
            user, created = User.objects.update_or_create(
                email=inv["email"],
                defaults={
                    "first_name": inv["first"],
                    "last_name": inv["last"],
                    "role": "INVESTOR",
                    "is_approved": True,
                    "phone": inv["phone"],
                    "password": pw,
                },
            )

            profile, _ = InvestorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "id_number": inv["id"],
                    "physical_address": f"P.O Box {2000 + idx}, Nairobi",
                    "bank_name": inv["bank"],
                    "bank_account_number": inv["account"],
                    "kyc_status": "verified",
                },
            )

            # Create one active investment
            start_date = _days_ago(random.randint(30, 365))
            maturity_date = _months_from(start_date, inv["months"])
            principal = _d(inv["amount"])
            rate = _d(inv["rate"]) / _d(100) / _d(12)
            months_elapsed = min(inv["months"], max(1, (date.today() - start_date).days // 30))
            monthly_interest = (principal * rate).quantize(_d("0.01"))
            accrued = (monthly_interest * _d(months_elapsed)).quantize(_d("0.01"))
            current_balance = principal + accrued

            investment, inv_created = Investment.objects.get_or_create(
                investor=profile,
                defaults={
                    "investment_type": "fixed_term",
                    "principal_amount": principal,
                    "interest_rate": _d(inv["rate"]),
                    "compounding_frequency": "monthly",
                    "start_date": start_date,
                    "maturity_date": maturity_date,
                    "current_balance": current_balance,
                    "total_interest_earned": accrued,
                    "state": "active" if date.today() < maturity_date else "matured",
                },
            )

            if inv_created:
                # Initial deposit transaction
                InvestmentTransaction.objects.create(
                    investment=investment,
                    transaction_type="deposit",
                    amount=principal,
                    description="Initial investment deposit",
                    balance_after=principal,
                    transaction_date=start_date,
                    status="completed",
                )
                # Monthly interest credits
                for m in range(1, months_elapsed + 1):
                    InterestDate = _months_from(start_date, m)
                    InvestmentTransaction.objects.create(
                        investment=investment,
                        transaction_type="interest_credit",
                        amount=monthly_interest,
                        description=f"Monthly interest – {InterestDate.strftime('%b %Y')}",
                        balance_after=(principal + monthly_interest * _d(m)).quantize(_d("0.01")),
                        transaction_date=InterestDate,
                        status="completed",
                    )

            self.stdout.write(
                f"    Investor: {user.get_full_name()} | "
                f"KES {inv['amount']:,} @ {inv['rate']}% | {inv['months']} months | "
                f"{'Created' if inv_created else 'Exists'}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _city_to_county(city: str) -> str:
    mapping = {
        "Nairobi": "Nairobi",
        "Kisumu": "Kisumu",
        "Nakuru": "Nakuru",
        "Mombasa": "Mombasa",
        "Eldoret": "Uasin Gishu",
        "Nyeri": "Nyeri",
        "Kikuyu": "Kiambu",
        "Meru": "Meru",
        "Thika": "Kiambu",
    }
    return mapping.get(city, "Nairobi")


def _loan_purpose(code: str) -> str:
    purposes = {
        "SAL001":  "Salary advance to cover household expenses pending next paycheck.",
        "BIZ001":  "Working capital to purchase stock and expand business operations.",
        "PERS001": "School fees payment for children's secondary education.",
        "IPF001":  "Invoice purchase finance against confirmed LPO from county government.",
        "BID001":  "Bid bond for road construction tender in Kiambu County.",
        "PERF001": "Performance bond to secure contract completion guarantee.",
        "STAFF001":"Staff personal loan for household appliances.",
        "ASSET001":"Asset finance for commercial vehicle (1-tonne pickup).",
    }
    return purposes.get(code, "General financing needs.")
