#!/usr/bin/env python3
"""
End-to-End Loan Workflow Test
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Simulates a customer applying for a loan from the Django portal
and walking through all 9 approval stages in Odoo.

Stages: draft → submitted → under_review → credit_analysis
        → pending_approval → approved → employer_verification
        → guarantor_confirmation → disbursed
"""

import json
import sys
import xmlrpc.client
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
ODOO_URL     = "http://localhost:8069"
ODOO_DB      = "alba_odoo"
ODOO_USER    = "admin"
ODOO_PASS    = "admin"

API_BASE     = "http://localhost:8000"   # Django side (simulated via REST)
ODOO_API     = "http://localhost:8069"
API_KEY      = "a63928f1-eeca-48b6-8a94-a471ff54ae8e"
API_HEADERS  = {"X-Alba-API-Key": API_KEY, "Content-Type": "application/json"}

import urllib.request
import urllib.error

def rest(method, path, body=None):
    """Thin HTTP client for the Odoo REST endpoints."""
    url = f"{ODOO_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=API_HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def ok(label, code, body):
    success = code in (200, 201)
    mark = "✓" if success else "✗"
    print(f"  {mark} [{code}] {label}")
    if not success:
        print(f"       Error: {body.get('error', body)}")
        sys.exit(1)
    return body

def section(title):
    print(f"\n{'━'*60}")
    print(f"  {title}")
    print(f"{'━'*60}")

# ── XML-RPC connection ────────────────────────────────────────────────────────
def odoo_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        print("✗ Odoo XML-RPC authentication failed")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models

def odoo_call(models, uid, model, method, args=None, kwargs=None):
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        model, method,
        args or [],
        kwargs or {}
    )

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN TEST
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═"*60)
print("  ALBA CAPITAL — END-TO-END LOAN WORKFLOW TEST")
print("  Currency: KES (Kenyan Shilling)")
print("═"*60)

uid, models = odoo_connect()
print(f"\n  Odoo XML-RPC connected (uid={uid})")

# ── Step 0: Health check ──────────────────────────────────────────────────────
section("STEP 0: Health Check")
code, body = rest("GET", "/alba/api/v1/health")
ok("Health endpoint", code, body)
print(f"       Service: {body.get('service')} | Version: {body.get('api_version')}")

# ── Step 1: List loan products ────────────────────────────────────────────────
section("STEP 1: Loan Products (KES)")
code, body = rest("GET", "/alba/api/v1/loan-products")
ok("List loan products", code, body)
products = body.get("products") or body.get("loan_products") or []
print(f"       {len(products)} products available:")
for p in products[:4]:
    print(f"         • {p['code']:12s}  {p['name']:30s}  KSh {p.get('min_amount',0):,.0f}–{p.get('max_amount',0):,.0f}")
# Pick a product that supports at least 6 months tenure (skip SAL-ADV which is 1-month max)
test_product = next(
    (p for p in products if (p.get('max_tenure') or 0) >= 6 and p.get('min_amount', 0) <= 100000),
    next((p for p in products if (p.get('max_tenure') or 0) >= 6), products[0])
)
test_tenure = min(6, test_product.get('max_tenure') or 6)
test_amount = max(test_product.get('min_amount', 50000), 50000)
print(f"\n       Selected product: {test_product['name']} ({test_product['code']})")
print(f"       Tenure: {test_tenure} months | Amount: KSh {test_amount:,.0f}")

# ── Step 2: Create test customer ──────────────────────────────────────────────
section("STEP 2: Register Customer (Django → Odoo)")
import random, string
suffix = ''.join(random.choices(string.digits, k=4))
django_customer_id = int(suffix) + 90000   # must be integer (alba.customer field type)
django_app_id = int(suffix) + 91000  # must be integer (fields.Integer on alba.loan.application)

customer_payload = {
    "django_customer_id": django_customer_id,
    "first_name": "Grace",
    "last_name": "Wanjiku",
    "email": f"grace.wanjiku.{suffix}@test.co.ke",
    "phone": "+254712345678",
    "id_number": f"KE{suffix}001",
    "employment_type": "employed",
    "employer_name": "Safaricom PLC",
    "monthly_income": 85000,
    "kra_pin": f"A{suffix}Z",
}
code, body = rest("POST", "/alba/api/v1/customers", customer_payload)
ok("Create customer via REST", code, body)
odoo_customer_id = body.get("odoo_customer_id") or body.get("customer", {}).get("id")
print(f"       Odoo Customer ID: {odoo_customer_id}")
print(f"       Django ID: {django_customer_id}")

# ── Step 3: Submit loan application (DRAFT) ───────────────────────────────────
section("STEP 3: Submit Loan Application (draft)")
app_payload = {
    "django_application_id": django_app_id,
    "django_customer_id": django_customer_id,
    "loan_product_code": test_product['code'],
    "requested_amount": test_amount,
    "tenure_months": test_tenure,
    "purpose": "School fees payment for dependants",
}
code, body = rest("POST", "/alba/api/v1/applications", app_payload)
ok("Create application (draft)", code, body)
odoo_app_id = body.get("odoo_application_id") or body.get("application", {}).get("id")
app_number = body.get("application_number", "")
print(f"       Odoo Application ID: {odoo_app_id}")
print(f"       Application Number: {app_number}")
print(f"       State: draft")

# ── Step 4–11: Walk through all stages via PATCH ──────────────────────────────
stages = [
    ("submitted",               "Customer confirms and submits from portal"),
    ("under_review",            "Loan officer picks up for review"),
    ("credit_analysis",         "Credit team analyses risk & score"),
    ("pending_approval",        "Forwarded to management for final sign-off"),
    ("approved",                "Management approves — KSh 50,000"),
    ("employer_verification",   "Employer letter & payslip verified"),
    ("guarantor_confirmation",  "Guarantor signs off"),
]

prev_state = "draft"
for new_state, description in stages:
    section(f"STAGE: {prev_state.upper()} → {new_state.upper()}")
    print(f"       Action: {description}")
    code, body = rest(
        "PATCH",
        f"/alba/api/v1/applications/{odoo_app_id}/status",
        {"new_status": new_state, "notes": description},
    )
    ok(f"Transition to {new_state}", code, body)
    print(f"       previous_state: {body.get('previous_state')}")
    print(f"       new_state:      {body.get('new_state')}")
    print(f"       application_number: {body.get('application_number')}")
    prev_state = new_state

# ── Step 12: Disburse via PATCH (API falls back to write when no action_disburse) ─
section("STAGE: GUARANTOR_CONFIRMATION → DISBURSED")
code, body = rest("PATCH", f"/alba/api/v1/applications/{odoo_app_id}/status", {
    "new_status": "disbursed",
    "notes": "E2E test disbursement",
    "approved_amount": test_amount,
    "disbursement_date": str(date.today()),
})
ok("Transition to disbursed", code, body)
print(f"       previous_state: {body.get('previous_state')}")
print(f"       new_state:      {body.get('new_state')}")

# ── Step 13: Verify final state ───────────────────────────────────────────────
section("VERIFICATION: Final Application & Loan State")

app_rec = odoo_call(
    models, uid, "alba.loan.application",
    "read",
    [[odoo_app_id]],
    {"fields": ["state", "application_number", "requested_amount", "approved_amount",
                "currency_id", "loan_product_id", "customer_id", "django_application_id",
                "submitted_date", "approved_date"]}
)
if app_rec:
    a = app_rec[0]
    print(f"\n  Application:")
    print(f"    Number:           {a.get('application_number')}")
    print(f"    State:            {a.get('state')}")
    print(f"    Requested Amount: {a.get('currency_id', ['','KSh'])[1]} {a.get('requested_amount'):,.2f}")
    print(f"    Approved Amount:  {a.get('currency_id', ['','KSh'])[1]} {a.get('approved_amount') or 'N/A'}")
    print(f"    Product:          {a.get('loan_product_id', ['', 'N/A'])[1]}")
    print(f"    Customer:         {a.get('customer_id', ['', 'N/A'])[1]}")
    print(f"    Currency:         {a.get('currency_id', ['', 'N/A'])[1]}")
    print(f"    Django App ID:    {a.get('django_application_id')}")

# Check if a loan record was created
loans = odoo_call(
    models, uid, "alba.loan",
    "search_read",
    [[["application_id", "=", odoo_app_id]]],
    {"fields": ["id", "loan_number", "state", "principal_amount",
                "outstanding_balance", "currency_id", "disbursement_date"]}
)
if loans:
    l = loans[0]
    print(f"\n  Loan Record Created:")
    print(f"    Loan Number:      {l.get('loan_number')}")
    print(f"    State:            {l.get('state')}")
    print(f"    Principal:        KSh {l.get('principal_amount'):,.2f}")
    print(f"    Balance:          KSh {l.get('outstanding_balance'):,.2f}")
    print(f"    Currency:         {l.get('currency_id', ['','N/A'])[1]}")
    print(f"    Disbursed on:     {l.get('disbursement_date')}")

    # Check repayment schedule
    schedules = odoo_call(
        models, uid, "alba.repayment.schedule",
        "search_read",
        [[["loan_id", "=", l["id"]]]],
        {"fields": ["installment_number", "due_date", "installment_amount",
                    "principal_amount", "interest_amount", "status"],
         "order": "installment_number asc"}
    )
    if schedules:
        print(f"\n  Repayment Schedule ({len(schedules)} instalments):")
        print(f"    {'#':>3}  {'Due Date':12}  {'Instalment':>14}  {'Principal':>12}  {'Interest':>10}  {'Status'}")
        print(f"    {'─'*3}  {'─'*12}  {'─'*14}  {'─'*12}  {'─'*10}  {'─'*10}")
        for s in schedules:
            print(
                f"    {s['installment_number']:>3}  {str(s['due_date']):12}  "
                f"KSh {s['installment_amount']:>10,.2f}  "
                f"KSh {s['principal_amount']:>8,.2f}  "
                f"KSh {s['interest_amount']:>6,.2f}  "
                f"{s['status']}"
            )
else:
    # Not necessarily an error — loan may be linked differently
    # Check by application number
    if app_rec and app_rec[0].get("state") == "disbursed":
        print(f"\n  ✓ Application state is 'disbursed' (loan may be linked via application)")
    else:
        print(f"\n  ⚠  No loan record found linked to application {odoo_app_id}")

print("\n" + "═"*60)
print("  END-TO-END TEST COMPLETE")
print("═"*60 + "\n")
