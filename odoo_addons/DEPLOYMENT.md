# Alba Capital — Odoo Modules Deployment Guide

> Complete step-by-step guide for deploying `alba_loans`, `alba_investors`, and `alba_integration` on Odoo 19 Enterprise.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Pre-deployment Checklist](#2-pre-deployment-checklist)
3. [Deployment to Odoo.sh](#3-deployment-to-odoosd)
4. [Deployment to a Self-Hosted VPS](#4-deployment-to-a-self-hosted-vps)
5. [Post-install Configuration](#5-post-install-configuration)
6. [M-Pesa Daraja Setup](#6-m-pesa-daraja-setup)
7. [Django Portal Integration Setup](#7-django-portal-integration-setup)
8. [Smoke Tests](#8-smoke-tests)
9. [Production Hardening](#9-production-hardening)
10. [Backup & Recovery](#10-backup--recovery)
11. [Upgrade Procedure](#11-upgrade-procedure)
12. [Rollback Procedure](#12-rollback-procedure)
13. [Environment Variable Reference](#13-environment-variable-reference)

---

## 1. Prerequisites

### Odoo Side

| Requirement | Version / Notes |
|-------------|-----------------|
| Odoo Enterprise | **19.0** (Community is NOT supported — accounting features require Enterprise) |
| PostgreSQL | 14 or later |
| Python | 3.10 or later |
| Python package | `requests >= 2.28` — install on the Odoo server: `pip install requests` |
| Odoo modules (built-in) | `base`, `account`, `mail`, `contacts`, `base_setup` |

### Django Side

| Requirement | Version / Notes |
|-------------|-----------------|
| Python | 3.12 |
| Django | 5.0.2 |
| Python packages | `requests`, `django` (already in `requirements.txt`) |
| Network | Odoo must be able to POST to the Django webhook endpoint (HTTPS) |
| Network | Django must be able to GET/POST to the Odoo API endpoints (HTTPS) |

### General

- Both Odoo and Django must be served over **HTTPS** in production.
  - Safaricom's Daraja API requires HTTPS for all production callback URLs.
  - Odoo webhook signatures can be replayed over plain HTTP — always use TLS.
- Odoo must have a **public** HTTPS URL reachable from Safaricom's servers for
  M-Pesa callbacks.

---

## 2. Pre-deployment Checklist

Run these checks before touching the server:

```bash
# From the project root — validate all Python files
find odoo_addons -name "*.py" | xargs python3 -m py_compile && echo "All Python OK"

# Validate all XML files
find odoo_addons -name "*.xml" | while read f; do
  xmllint --noout "$f" && echo "OK $f" || echo "FAIL $f"
done
```

Expected output: every file reports `OK`.

Verify the module dependency order is correct:

```
alba_loans       → depends on: base, account, mail, contacts, base_setup
alba_investors   → depends on: base, account, mail, contacts, base_setup, alba_loans
alba_integration → depends on: base, mail, alba_loans, alba_investors
```

---

## 3. Deployment to Odoo.sh

Odoo.sh handles deployment via Git — just push to the linked branch.

### 3.1 Add modules to your repository

```bash
# In your Odoo.sh-linked Git repository
cp -r /path/to/ACCT.f/odoo_addons/alba_loans    ./addons/
cp -r /path/to/ACCT.f/odoo_addons/alba_investors ./addons/
cp -r /path/to/ACCT.f/odoo_addons/alba_integration ./addons/

git add addons/alba_loans addons/alba_investors addons/alba_integration
git commit -m "feat: add Alba Capital custom modules (alba_loans, alba_investors, alba_integration)"
git push origin <your-branch>
```

### 3.2 Add Python dependency

Create or update `requirements.txt` in the repository root:

```
requests>=2.28.0
```

Commit and push. Odoo.sh will automatically `pip install` this on the next build.

### 3.3 Install modules via Odoo UI

1. Open your Odoo.sh staging or production instance.
2. Enable developer mode: `Settings → Activate the developer mode`.
3. Go to `Apps → Update Apps List` — click **Update**.
4. Search **"Alba"** — install in this order:
   1. **Alba Capital - Loan Management** (`alba_loans`)
   2. **Alba Capital - Investor Management** (`alba_investors`)
   3. **Alba Capital - Django Integration Bridge** (`alba_integration`)

> **Important:** Install one at a time and wait for each to complete before
> installing the next.

---

## 4. Deployment to a Self-Hosted VPS

### 4.1 Copy modules to the Odoo addons path

```bash
# Typical addons path on a self-hosted instance
ADDONS_PATH=/opt/odoo/custom_addons

sudo cp -r /path/to/ACCT.f/odoo_addons/alba_loans     $ADDONS_PATH/
sudo cp -r /path/to/ACCT.f/odoo_addons/alba_investors  $ADDONS_PATH/
sudo cp -r /path/to/ACCT.f/odoo_addons/alba_integration $ADDONS_PATH/

sudo chown -R odoo:odoo $ADDONS_PATH/alba_loans
sudo chown -R odoo:odoo $ADDONS_PATH/alba_investors
sudo chown -R odoo:odoo $ADDONS_PATH/alba_integration
```

### 4.2 Install Python dependency

```bash
# Activate the Odoo virtual environment (adjust path as needed)
source /opt/odoo/venv/bin/activate
pip install "requests>=2.28.0"
deactivate
```

Or add to Odoo's `requirements.txt` and re-run `pip install -r requirements.txt`.

### 4.3 Update `odoo.conf` addons path

```ini
# /etc/odoo/odoo.conf
[options]
addons_path = /opt/odoo/addons,/opt/odoo/enterprise,/opt/odoo/custom_addons
```

### 4.4 Restart Odoo

```bash
sudo systemctl restart odoo
# Check for startup errors
sudo journalctl -u odoo -f --no-pager | head -50
```

### 4.5 Install modules

```bash
# Method A: via Odoo UI (recommended — see section 3.3)

# Method B: via command line
sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo-bin \
  --config /etc/odoo/odoo.conf \
  --database <your_db_name> \
  --install alba_loans \
  --stop-after-init

sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo-bin \
  --config /etc/odoo/odoo.conf \
  --database <your_db_name> \
  --install alba_investors \
  --stop-after-init

sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo-bin \
  --config /etc/odoo/odoo.conf \
  --database <your_db_name> \
  --install alba_integration \
  --stop-after-init

# Restart normally after all installs
sudo systemctl start odoo
```

---

## 5. Post-install Configuration

Perform these steps immediately after installing all three modules.

### 5.1 Configure the Chart of Accounts

Before creating any loan products, map these accounts in Odoo:

| Account | Type | Suggested Code |
|---------|------|---------------|
| Loans Receivable | Asset — Non-current | `1201` |
| Interest Income | Income | `4101` |
| Loan Fee Income | Income | `4102` |
| Penalty Income | Income | `4103` |
| Investment Liability | Liability | `2201` |
| Interest Expense | Expense | `5101` |
| Bank / Cash | Bank | (your bank account) |

### 5.2 Create Loan Products

1. Go to **Alba Loans → Configuration → Loan Products**.
2. Click **New** and fill in:
   - Product Name, Code, Category
   - Min/Max Amount and Tenure
   - Interest Rate and Method
   - Fee percentages
   - **Accounting accounts** (Loan Receivable, Interest Income, Fee Income)
3. Save and repeat for each product type.

### 5.3 Create an Integration API Key

1. Go to **Alba Integration → API Keys**.
2. Click **New**.
3. Fill in:
   - **Label:** `Django Portal – Production`
   - **Django Portal URL:** `https://portal.albacapital.co.ke`
   - **Webhook Path:** `/api/v1/webhooks/odoo/`
4. Click **Save** — the **API Key** and **Webhook Secret** are generated.
5. **Copy both values now** — the secret is only readable before the form is closed.
6. Add to your Django `.env`:
   ```env
   ODOO_API_KEY=<copied key>
   ODOO_WEBHOOK_SECRET=<copied secret>
   ODOO_URL=https://odoo.albacapital.co.ke
   ```

### 5.4 Configure Investor Interest Accounts

1. Go to **Alba Investors → Configuration** (if visible) or via Odoo's
   account settings.
2. Set:
   - **Interest Expense Account:** `5101 Interest Expense`
   - **Investment Liability Account:** `2201 Investment Liability`

### 5.5 Review System Parameters

Go to **Settings → Technical → System Parameters** and verify/update:

```
alba.integration.api_version                    = 1.0
alba.integration.webhook_timeout                = 30
alba.integration.max_retries                    = 5
alba.integration.sync_log_retention_days        = 90
alba.integration.webhook_log_retention_days     = 60
alba.loans.npl_threshold_days                   = 90
```

### 5.6 Activate Cron Jobs

1. Go to **Settings → Technical → Scheduled Actions**.
2. Search for **"Alba"**.
3. Verify that all cron jobs are **Active** and have sensible next-run times.

Expected cron jobs:

| Name | Schedule |
|------|----------|
| Alba Loans — Update PAR Buckets | Daily |
| Alba Loans — NPL Monitor | Daily |
| Alba Loans — Overdue Payment Alerts | Daily |
| Alba Loans — Maturity Date Reminders | Weekly |
| Alba Loans — Auto-close Fully-Repaid Loans | Daily |
| Alba Loans — Query Pending STK Transactions | Every 30 min |
| Alba Loans — Auto-reconcile M-Pesa Transactions | Hourly |
| Alba Loans — Sync Portfolio Stats to Django | Every 6 hours |
| Alba Investors — Monthly Interest Accrual | Monthly |
| Alba Investors — Monthly Statement Generation | Monthly |
| Alba Integration — Process Webhook Retry Queue | Every 15 min |
| Alba Integration — Purge Old Sync Logs | Weekly |
| Alba Integration — Health Check Webhook | Every 6 hours |
| Alba Integration — Purge Old Webhook Logs | Weekly |
| Alba Integration — Dead Retry Alert | Daily |

### 5.7 Assign User Groups

For each Odoo user, assign the appropriate group:

| Role | Group |
|------|-------|
| Credit officer | `Alba Loans / Loan Officer` |
| Finance manager | `Alba Loans / Loan Manager` |
| Investor manager | `Alba Investors / Investor Manager` |
| IT / integration admin | `Alba Integration / Integration Admin` |

---

## 6. M-Pesa Daraja Setup

### 6.1 Get Daraja Credentials

1. Register at [https://developer.safaricom.co.ke](https://developer.safaricom.co.ke).
2. Create a **Sandbox App** (for testing) and a **Production App** (for live).
3. Note:
   - **Consumer Key**
   - **Consumer Secret**
   - **Business Short Code** (your Paybill number)
   - **Passkey** (for Lipa Na M-Pesa / STK Push)

For **production**, you need:
- An active M-Pesa Paybill or Till number from Safaricom.
- Approved access to Lipa Na M-Pesa Online (STK Push).
- Approved access to C2B.
- (For investor payouts) Approved access to B2C + an Initiator username and Security Credential.

### 6.2 Configure in Odoo

1. Go to **Alba Loans → M-Pesa → M-Pesa Configuration**.
2. Click **New**.
3. Fill in all fields (see [M-Pesa section in alba_loans/README.md](alba_loans/README.md#m-pesa-integration)).
4. Click **Test Connection** — should show "Connection Successful".

### 6.3 Register C2B Callback URLs

1. Set **Callback Base URL** to your Odoo instance's public HTTPS URL, e.g.
   `https://odoo.albacapital.co.ke`.
2. Click **Register C2B URLs** — this POSTs the validation and confirmation
   URLs to Safaricom's API.
3. For STK Push and B2C, register the callback URLs manually in the
   [Daraja portal](https://developer.safaricom.co.ke):
   - STK Push Callback: `https://odoo.albacapital.co.ke/alba/mpesa/stk/callback`
   - B2C Result URL: `https://odoo.albacapital.co.ke/alba/mpesa/b2c/result`
   - B2C Queue Timeout URL: `https://odoo.albacapital.co.ke/alba/mpesa/b2c/timeout`

### 6.4 Test STK Push (Sandbox)

1. Create a test customer and loan in Odoo.
2. Open the loan form → click **Request M-Pesa Payment**.
3. Use the sandbox test number `254708374149`.
4. Click **Send STK Push**.
5. Check **Alba Loans → M-Pesa → Transactions** for the pending record.
6. The sandbox does not actually prompt a phone — use the Daraja portal's
   test STK callback to simulate a result.

### 6.5 Sandbox → Production Switch

1. In the M-Pesa Configuration record, change **Environment** from
   `Sandbox` to `Production`.
2. Update Consumer Key, Consumer Secret, Passkey, and Short Code to your
   **production** Daraja credentials.
3. Click **Test Connection** to verify.
4. Click **Register C2B URLs** again for the production environment.

---

## 7. Django Portal Integration Setup

### 7.1 Update `.env`

```env
# Odoo integration
ODOO_URL=https://odoo.albacapital.co.ke
ODOO_API_KEY=<from Odoo API key record>
ODOO_WEBHOOK_SECRET=<from Odoo API key record>
ODOO_TIMEOUT=30
ODOO_MAX_RETRIES=3
ODOO_RETRY_BACKOFF=2

# M-Pesa (proxy mode — recommended)
MPESA_STANDALONE=False
MPESA_STK_ENDPOINT=/alba/api/v1/mpesa/stk-push
MPESA_STK_QUERY_ENDPOINT=/alba/api/v1/mpesa/stk-status
```

### 7.2 Run Django migrations

The webhook receiver uses a `WebhookDelivery` model for idempotency.
If this model has a migration, run it:

```bash
cd loan_system
python manage.py migrate
```

### 7.3 Verify the webhook endpoint

```bash
# The endpoint must return 401 when called without a valid signature
curl -X POST https://portal.albacapital.co.ke/api/v1/webhooks/odoo/ \
  -H "Content-Type: application/json" \
  -d '{"event":"test","data":{}}' \
  -w "\nHTTP Status: %{http_code}\n"
# Expected: HTTP Status: 401
```

### 7.4 Run a full end-to-end smoke test

```bash
# From a Django shell
python manage.py shell
```

```python
from core.services.odoo_sync import OdooSyncService

service = OdooSyncService()

# 1. Health check
print(service.health_check())
# Expected: {'status': 'ok', 'service': 'alba-odoo', 'version': '1.0'}

# 2. List loan products
products = service.get_loan_products()
print(f"Found {len(products)} loan product(s)")

# 3. Connectivity check
print("Reachable:", service.is_reachable())
```

---

## 8. Smoke Tests

Run these after every deployment to verify the system is working correctly.

### 8.1 REST API Tests (curl)

```bash
ODOO_URL="https://odoo.albacapital.co.ke"
API_KEY="your-api-key-here"

# Health (no auth required)
curl -s "$ODOO_URL/alba/api/v1/health" | python3 -m json.tool

# Loan products
curl -s -H "X-Alba-API-Key: $API_KEY" \
  "$ODOO_URL/alba/api/v1/loan-products" | python3 -m json.tool

# Create customer
curl -s -X POST "$ODOO_URL/alba/api/v1/customers" \
  -H "X-Alba-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "django_customer_id": 9999,
    "email": "smoke.test@albacapital.co.ke",
    "first_name": "Smoke",
    "last_name": "Test",
    "phone": "0700000001"
  }' | python3 -m json.tool
```

### 8.2 M-Pesa Health Check

```bash
curl -s "$ODOO_URL/alba/mpesa/health" | python3 -m json.tool
# Expected: {"status": "ok", "service": "alba-mpesa-callbacks", "active_configs": 1}
```

### 8.3 Webhook Signature Verification (Python)

```python
import hashlib
import hmac
import json
import requests

ODOO_URL = "https://odoo.albacapital.co.ke"
WEBHOOK_SECRET = "your-webhook-secret"
DJANGO_WEBHOOK_URL = "https://portal.albacapital.co.ke/api/v1/webhooks/odoo/"

# Build a test payload
payload = {
    "event": "integration.health_check",
    "timestamp": "2024-06-15T10:00:00+00:00",
    "delivery_id": "test-delivery-001",
    "data": {"test": True}
}
body = json.dumps(payload).encode("utf-8")

# Sign it
signature = hmac.new(
    WEBHOOK_SECRET.encode("utf-8"),
    body,
    hashlib.sha256,
).hexdigest()

# POST to Django
resp = requests.post(
    DJANGO_WEBHOOK_URL,
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Alba-Signature": f"sha256={signature}",
        "X-Alba-Event": "integration.health_check",
        "X-Alba-Delivery": "test-delivery-001",
    },
    timeout=10,
)
print(f"Status: {resp.status_code}")
print(f"Body: {resp.json()}")
# Expected: Status: 200, Body: {'status': 'ok', 'event': 'integration.health_check'}
```

### 8.4 Cron Jobs Smoke Test

```bash
# In Odoo shell — manually trigger the health check cron
env['alba.sync.log'].get_sync_health_summary(hours=1)
# Should return a dict without error

env['alba.webhook.retry'].cron_process_retry_queue()
# Should run without error (0 records if queue is empty)
```

---

## 9. Production Hardening

### 9.1 HTTPS / TLS

- Odoo must be behind an HTTPS reverse proxy (nginx or Caddy).
- Django must be served over HTTPS.
- Set in Django `.env`:
  ```env
  SESSION_COOKIE_SECURE=True
  CSRF_COOKIE_SECURE=True
  ```

### 9.2 API Key IP Allowlisting

In the Odoo API key record, set **Allowed IP Addresses** to the specific
IP address(es) of your Django server:

```
185.1.2.3, 185.1.2.4
```

### 9.3 Firewall Rules

- Allow Safaricom IPs to reach Odoo's M-Pesa callback endpoints:
  - `196.201.214.200/24`
  - `196.201.214.206/24`
  - `196.201.213.114/24`
- Block direct access to Odoo `/alba/api/v1/*` from the internet — only
  allow from Django server IPs and your office/VPN.

### 9.4 Odoo Configuration

```ini
# /etc/odoo/odoo.conf
[options]
db_maxconn = 64
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 60
limit_time_real = 120
max_cron_threads = 2
workers = 4
proxy_mode = True
```

### 9.5 Log Rotation

```bash
# /etc/logrotate.d/odoo
/var/log/odoo/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    postrotate
        systemctl kill -s HUP odoo
    endscript
}
```

### 9.6 Database Connection Pooling

Use `pgbouncer` in front of PostgreSQL for connection pooling when running
multiple Odoo workers.

### 9.7 Monitoring

Monitor these metrics:

| Metric | Alert Threshold |
|--------|----------------|
| Webhook retry queue depth | > 10 pending records |
| Dead webhook count | > 0 |
| Sync failure rate (last hour) | > 5% of requests |
| Cron job last run (each) | > 2× scheduled interval |
| PAR 90+ days / total outstanding | > 10% |

---

## 10. Backup & Recovery

### 10.1 Database Backup

```bash
# Full PostgreSQL backup (run daily via cron)
pg_dump -U odoo -Fc <db_name> > /backups/odoo_$(date +%Y%m%d_%H%M%S).dump

# Restore
pg_restore -U odoo -d <db_name> /backups/odoo_<timestamp>.dump
```

### 10.2 Filestore Backup

```bash
# Backup Odoo filestore (attachments, etc.)
tar -czf /backups/filestore_$(date +%Y%m%d).tar.gz \
  /opt/odoo/.local/share/Odoo/filestore/<db_name>/
```

### 10.3 Module Backup

The module source code should be in version control (Git). Before any
upgrade:

```bash
git tag -a "pre-upgrade-$(date +%Y%m%d)" -m "Pre-upgrade snapshot"
git push origin --tags
```

---

## 11. Upgrade Procedure

When upgrading the custom modules (e.g. adding a new field or model):

### 11.1 Test on Staging First

1. Push changes to the staging branch / staging server.
2. Run the upgrade on staging:
   ```bash
   sudo -u odoo python /opt/odoo/odoo-bin \
     --config /etc/odoo/odoo.conf \
     --database <staging_db> \
     --update alba_loans,alba_investors,alba_integration \
     --stop-after-init
   ```
3. Verify all views load, crons are active, API endpoints respond.

### 11.2 Production Upgrade

1. Take a full database backup (see section 10.1).
2. Put Odoo into maintenance mode (optional — prevents new requests during upgrade).
3. Stop Odoo:
   ```bash
   sudo systemctl stop odoo
   ```
4. Copy updated module files:
   ```bash
   sudo cp -r /path/to/updated/alba_loans /opt/odoo/custom_addons/
   sudo cp -r /path/to/updated/alba_investors /opt/odoo/custom_addons/
   sudo cp -r /path/to/updated/alba_integration /opt/odoo/custom_addons/
   sudo chown -R odoo:odoo /opt/odoo/custom_addons/alba_*
   ```
5. Run the upgrade:
   ```bash
   sudo -u odoo python /opt/odoo/odoo-bin \
     --config /etc/odoo/odoo.conf \
     --database <production_db> \
     --update alba_loans,alba_investors,alba_integration \
     --stop-after-init 2>&1 | tee /tmp/upgrade_$(date +%Y%m%d).log
   ```
6. Check the log for errors.
7. Start Odoo:
   ```bash
   sudo systemctl start odoo
   ```
8. Run smoke tests (section 8).

---

## 12. Rollback Procedure

If an upgrade causes issues:

```bash
# 1. Stop Odoo
sudo systemctl stop odoo

# 2. Restore previous module files from Git
cd /opt/odoo/custom_addons
git checkout <previous-tag> -- alba_loans alba_investors alba_integration

# 3. Restore the database from backup
pg_restore -U odoo -d <db_name> --clean /backups/odoo_<pre-upgrade-timestamp>.dump

# 4. Start Odoo (no --update needed — database is back to pre-upgrade state)
sudo systemctl start odoo

# 5. Verify
curl -s https://odoo.albacapital.co.ke/alba/api/v1/health
```

---

## 13. Environment Variable Reference

### Django `.env` — Complete Reference

```env
# ── Django Core ────────────────────────────────────────────────────────────
SECRET_KEY=<50+ char random string>
DEBUG=False
ALLOWED_HOSTS=portal.albacapital.co.ke

# ── Database ────────────────────────────────────────────────────────────────
DB_NAME=alba_capital
DB_USER=postgres
DB_PASSWORD=<strong password>
DB_HOST=localhost
DB_PORT=5432

# ── Security ────────────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# ── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@albacapital.co.ke
EMAIL_HOST_PASSWORD=<app password>

# ── Odoo Integration ─────────────────────────────────────────────────────────
ODOO_URL=https://odoo.albacapital.co.ke
ODOO_API_KEY=<from Odoo API key record>
ODOO_WEBHOOK_SECRET=<from Odoo API key record>
ODOO_TIMEOUT=30
ODOO_MAX_RETRIES=3
ODOO_RETRY_BACKOFF=2

# ── M-Pesa (proxy mode — recommended) ────────────────────────────────────────
MPESA_STANDALONE=False
MPESA_STK_ENDPOINT=/alba/api/v1/mpesa/stk-push
MPESA_STK_QUERY_ENDPOINT=/alba/api/v1/mpesa/stk-status
MPESA_ALLOWED_IPS=196.201.214.200/24,196.201.214.206/24
```

### Odoo `odoo.conf` — Key Settings

```ini
[options]
addons_path = /opt/odoo/addons,/opt/odoo/enterprise,/opt/odoo/custom_addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = <strong password>
http_port = 8069
proxy_mode = True
workers = 4
max_cron_threads = 2
logfile = /var/log/odoo/odoo.log
log_level = warn
```

---

*Last updated: Alba Capital Engineering Team*
*Module version: 19.0.1.0.0*