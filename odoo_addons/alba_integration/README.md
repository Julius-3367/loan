# Alba Capital — Django Integration Bridge (`alba_integration`)

> Odoo 19 Enterprise module — REST API bridge, HMAC-signed webhooks,
> retry queue, and sync audit log connecting the Django portal to Odoo.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Structure](#module-structure)
4. [REST API Endpoints](#rest-api-endpoints)
5. [Outbound Webhooks](#outbound-webhooks)
6. [Webhook Retry Queue](#webhook-retry-queue)
7. [Sync Audit Log](#sync-audit-log)
8. [API Key Management](#api-key-management)
9. [Security Groups](#security-groups)
10. [Installation](#installation)
11. [Configuration](#configuration)
12. [Django Portal Setup](#django-portal-setup)
13. [Operations Guide](#operations-guide)
14. [Event Catalogue](#event-catalogue)
15. [Troubleshooting](#troubleshooting)
16. [Changelog](#changelog)

---

## Overview

`alba_integration` is the integration layer between the **Alba Capital Django
customer portal** and **Odoo Enterprise**. It exposes a set of authenticated
REST endpoints that the portal calls to synchronise data, and it fires
HMAC-SHA256-signed webhook POST requests back to Django whenever key events
occur inside Odoo.

### What this module does

- **Inbound (Django → Odoo):** Exposes REST endpoints under `/alba/api/v1/`
  for the portal to create customers, submit loan applications, update KYC
  status, record payments, and query loan products.
- **Outbound (Odoo → Django):** Fires signed webhook events whenever
  application status changes, loans are disbursed, payments are matched,
  M-Pesa payments arrive, customers are KYC-verified, and more.
- **Retry Queue:** Automatically retries failed webhook deliveries on an
  exponential back-off schedule with operator visibility.
- **Sync Audit Log:** Records every inbound and outbound sync operation for
  full auditability and troubleshooting.
- **Health Monitoring:** Periodic health-check webhooks and dead-webhook alerts
  keep the operations team informed of integration status.

---

## Architecture

```
┌─────────────────────────────────┐        ┌─────────────────────────────────┐
│       Django Portal             │        │        Odoo Enterprise          │
│                                 │        │                                 │
│  OdooSyncService ──────────────►│  HTTP  │  AlbaApiController              │
│  (core/services/odoo_sync.py)   │───────►│  /alba/api/v1/*                 │
│                                 │        │                                 │
│  WebhookReceiver ◄──────────────│  HTTP  │  alba.api.key.send_webhook()    │
│  /api/v1/webhooks/odoo/         │◄───────│  (HMAC-SHA256 signed)           │
│                                 │        │                                 │
│  MpesaService ─────────────────►│  HTTP  │  /alba/api/v1/mpesa/stk-push    │
│  (core/services/mpesa.py)       │───────►│  (proxied to Daraja)            │
└─────────────────────────────────┘        └─────────────────────────────────┘
                                                          │
                                                          ▼
                                           ┌─────────────────────────────────┐
                                           │   Safaricom Daraja API          │
                                           │   (M-Pesa STK / C2B / B2C)     │
                                           └─────────────────────────────────┘
```

### Authentication

| Direction | Mechanism |
|-----------|-----------|
| Django → Odoo | `X-Alba-API-Key` header matching an active `alba.api.key` record |
| Odoo → Django | `X-Alba-Signature: sha256=<hmac_hex>` computed over raw body |

### Webhook Envelope

Every outbound webhook from Odoo uses this JSON envelope:

```json
{
  "event": "application.status_changed",
  "timestamp": "2024-06-15T10:30:00+00:00",
  "delivery_id": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "odoo_application_id": 42,
    "django_application_id": 17,
    "new_status": "approved"
  }
}
```

---

## Module Structure

```
alba_integration/
├── __init__.py
├── __manifest__.py
├── README.md
│
├── controllers/
│   ├── __init__.py
│   └── api_controller.py       # REST endpoints: /alba/api/v1/*
│
├── data/
│   ├── integration_data.xml    # Seeded system parameters
│   └── cron_data.xml           # 5 scheduled automation jobs
│
├── models/
│   ├── __init__.py
│   ├── api_key.py              # alba.api.key — key + secret management
│   ├── webhook_log.py          # alba.webhook.log — delivery history
│   ├── webhook_retry.py        # alba.webhook.retry — retry queue
│   └── sync_log.py             # alba.sync.log — operation audit log
│
├── security/
│   ├── security.xml            # Groups: integration_user, integration_admin
│   └── ir.model.access.csv
│
└── views/
    ├── api_key_views.xml
    ├── webhook_log_views.xml
    ├── webhook_retry_views.xml
    ├── sync_log_views.xml
    └── menus.xml
```

---

## REST API Endpoints

All endpoints are under the prefix `/alba/api/v1/`.

Every request (except `/health`) must include:

```
X-Alba-API-Key: <your-api-key>
Content-Type: application/json
```

### `GET /alba/api/v1/health`

Liveness probe — no authentication required.

**Response 200:**
```json
{
  "status": "ok",
  "service": "alba-odoo",
  "version": "1.0"
}
```

---

### `GET /alba/api/v1/loan-products`

Returns all active loan products configured in Odoo.

**Response 200:**
```json
{
  "products": [
    {
      "id": 1,
      "name": "Salary Advance",
      "code": "SAL-ADV-001",
      "category": "salary_advance",
      "min_amount": 5000.0,
      "max_amount": 100000.0,
      "min_tenure_months": 1,
      "max_tenure_months": 12,
      "interest_rate": 5.0,
      "interest_method": "reducing_balance",
      "repayment_frequency": "monthly",
      "origination_fee_percentage": 2.0
    }
  ]
}
```

---

### `POST /alba/api/v1/customers`

Create or update a customer in Odoo from a Django User record.

**Request body:**
```json
{
  "django_customer_id": 42,
  "email": "john.doe@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "0712345678",
  "id_number": "12345678",
  "id_type": "national_id",
  "date_of_birth": "1990-01-15",
  "nationality": "Kenyan",
  "employer_name": "Acme Corp",
  "monthly_income": 80000.0,
  "kyc_status": "pending"
}
```

**Response 201 (created) / 200 (updated):**
```json
{
  "odoo_customer_id": 15,
  "customer_number": "ALB-CUST-00015",
  "status": "created"
}
```

---

### `POST /alba/api/v1/customers/<odoo_customer_id>/kyc`

Update the KYC status of an existing Odoo customer.

**Request body:**
```json
{
  "kyc_status": "verified",
  "notes": "Documents verified on 2024-06-15",
  "document_type": "national_id",
  "document_number": "12345678"
}
```

Valid `kyc_status` values: `pending`, `submitted`, `verified`, `rejected`.

**Response 200:**
```json
{
  "odoo_customer_id": 15,
  "kyc_status": "verified",
  "status": "updated"
}
```

---

### `POST /alba/api/v1/applications`

Submit a new loan application from the portal.

**Request body:**
```json
{
  "django_application_id": 101,
  "odoo_customer_id": 15,
  "odoo_loan_product_id": 1,
  "requested_amount": 50000.0,
  "tenure_months": 6,
  "repayment_frequency": "monthly",
  "purpose": "Business working capital"
}
```

**Response 201:**
```json
{
  "odoo_application_id": 88,
  "application_number": "APP-000088",
  "status": "created"
}
```

---

### `PATCH /alba/api/v1/applications/<odoo_application_id>/status`

Transition a loan application to a new stage.

**Request body:**
```json
{
  "status": "approved",
  "approved_amount": 45000.0,
  "conditions_of_approval": "Must provide P60 for last 3 months."
}
```

Valid `status` values:
`submitted`, `under_review`, `credit_analysis`, `pending_approval`,
`approved`, `employer_verification`, `guarantor_confirmation`,
`disbursed`, `rejected`, `cancelled`.

For `rejected`, include `"rejection_reason": "..."`.
For `cancelled`, include `"cancellation_reason": "..."`.

**Response 200:**
```json
{
  "odoo_application_id": 88,
  "application_number": "APP-000088",
  "new_status": "approved",
  "status": "updated"
}
```

---

### `POST /alba/api/v1/payments`

Record a repayment against a loan.

**Request body:**
```json
{
  "odoo_loan_id": 22,
  "amount": 9500.0,
  "payment_date": "2024-06-15",
  "payment_method": "mpesa",
  "mpesa_transaction_id": "QGH7YXXXXX",
  "payment_reference": "QGH7YXXXXX",
  "django_payment_id": 55,
  "notes": "Customer paid via M-Pesa Paybill"
}
```

Valid `payment_method` values: `mpesa`, `bank_transfer`, `cash`, `cheque`, `rtgs`.

**Response 201:**
```json
{
  "odoo_repayment_id": 304,
  "status": "posted",
  "principal_applied": 8200.0,
  "interest_applied": 1300.0
}
```

---

### `POST /alba/api/v1/mpesa/stk-push`

Proxy an STK Push request to the Daraja API via Odoo.

**Request body:**
```json
{
  "phone_number": "254712345678",
  "amount": 9500,
  "account_reference": "LN-000022",
  "transaction_desc": "Loan Repayment",
  "odoo_loan_id": 22
}
```

**Response 200:**
```json
{
  "checkout_request_id": "ws_CO_15062024103045123456",
  "merchant_request_id": "12345-67890-1",
  "response_code": "0",
  "customer_message": "Success. Request accepted for processing",
  "odoo_transaction_id": 12
}
```

---

### `POST /alba/api/v1/mpesa/stk-status`

Query the status of a pending STK Push transaction.

**Request body:**
```json
{
  "checkout_request_id": "ws_CO_15062024103045123456"
}
```

**Response 200:**
```json
{
  "checkout_request_id": "ws_CO_15062024103045123456",
  "result_code": "0",
  "result_desc": "The service request is processed successfully.",
  "status": "completed",
  "mpesa_code": "QGH7YXXXXX",
  "amount": 9500.0
}
```

---

### Error Responses

All endpoints return errors in this format:

```json
{
  "error": "Human-readable error message.",
  "code": "optional_error_code"
}
```

| HTTP Status | Meaning |
|-------------|---------|
| `400` | Validation error — missing fields or invalid values |
| `403` | Missing or invalid `X-Alba-API-Key` header |
| `404` | Referenced Odoo record not found |
| `409` | Duplicate record (e.g. M-Pesa transaction ID already exists) |
| `500` | Unexpected server error — check Odoo server logs |

---

## Outbound Webhooks

Odoo fires a signed POST request to the Django portal's webhook endpoint
whenever a key event occurs.

### Signature Verification (Django side)

```python
import hashlib
import hmac

def verify_webhook(raw_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256="):]
    computed = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected)
```

### Request Headers

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json; charset=utf-8` |
| `X-Alba-Signature` | `sha256=<hmac_sha256_hex>` |
| `X-Alba-Event` | Event type string |
| `X-Alba-Delivery` | UUID for idempotency |
| `User-Agent` | `AlbaOdooIntegration/1.0` |

### Expected Response

The Django portal must return HTTP `2xx` within 30 seconds. Any other status
triggers an automatic retry via the retry queue.

---

## Webhook Retry Queue

When a webhook delivery fails (network error, non-2xx, timeout), the system
automatically creates an `alba.webhook.retry` record and retries on an
exponential back-off schedule.

### Back-off Schedule

| Attempt | Delay |
|---------|-------|
| 1st retry | 2 minutes |
| 2nd retry | 5 minutes |
| 3rd retry | 15 minutes |
| 4th retry | 60 minutes |
| 5th retry | 4 hours |
| After 5 retries | Status → **Dead** |

### Managing the Queue

Go to **Alba Integration → Retry Queue** to see all pending retries.

- **Retry Now** — attempt immediate re-delivery (available on any non-delivered record).
- **Mark Dead** — permanently abandon retries for this record.
- **Re-queue** — reset a dead record back to pending for another retry cycle.
- **Alba Integration → Dead Webhooks** — filtered view of all dead records.

### Cron: Process Retry Queue

Runs **every 15 minutes**. Processes up to 50 records per run (ordered by
`next_retry_at` ascending). A daily **Dead Retry Alert** cron fires a
`integration.dead_webhooks_alert` webhook to Django when dead records are present.

---

## Sync Audit Log

Every inbound API call and outbound webhook delivery is recorded as an
`alba.sync.log` record.

### Fields

| Field | Description |
|-------|-------------|
| `direction` | `inbound` (Django → Odoo) or `outbound` (Odoo → Django) |
| `operation` | `create`, `update`, `status_change`, `delete`, `full_sync`, `health_check` |
| `status` | `success`, `partial`, `failure`, `skipped`, `pending` |
| `odoo_model` | Technical Odoo model name (e.g. `alba.loan.application`) |
| `odoo_record_id` | Odoo database ID |
| `django_record_id` | Django primary key |
| `event_type` | Webhook event type (outbound only) |
| `http_status_code` | HTTP response code |
| `duration_ms` | Processing time in milliseconds |
| `request_data` | JSON snapshot of the inbound request body |
| `response_data` | JSON snapshot of the response |
| `remote_ip` | Client IP of inbound requests |

### Accessing Logs

- **All events:** Alba Integration → Sync Logs → All Sync Events
- **Failures only:** Alba Integration → Sync Logs → Failures

### Retention

A weekly cron purges records older than the configured retention period.
Configure via:

```
Settings → Technical → System Parameters → alba.integration.sync_log_retention_days
```

Default: **90 days**.

---

## API Key Management

Go to **Alba Integration → API Keys** to manage integration keys.

### Creating an API Key

1. Click **New**.
2. Fill in:
   - **Label** — e.g. `Django Portal – Production`
   - **Django Portal URL** — e.g. `https://portal.albacapital.co.ke`
   - **Webhook Path** — defaults to `/api/v1/webhooks/odoo/`
   - **Allowed IP Addresses** — optional; comma-separated IP whitelist
3. Click **Save** — the **API Key** and **Webhook Secret** are generated automatically.
4. Copy the key and secret to your Django `.env` file:
   ```
   ODOO_API_KEY=<key>
   ODOO_WEBHOOK_SECRET=<webhook_secret>
   ```

### Rotating Credentials

- **Regenerate API Key** — invalidates the current key immediately. Update Django before clicking.
- **Rotate Webhook Secret** — invalidates the current secret. Update Django before clicking.

### IP Allowlisting

Enter a comma-separated list of IP addresses in **Allowed IP Addresses** to restrict
which clients can use the key. Leave blank to accept from any IP.

---

## Security Groups

| Group | Technical ID | Permissions |
|-------|-------------|-------------|
| **Integration User** | `group_integration_user` | Read webhook logs, sync logs, retry queue |
| **Integration Admin** | `group_integration_admin` | Full: manage API keys, retry queue, view/delete all logs. Implies Integration User. |

---

## Installation

### Prerequisites

- Odoo 19 Enterprise
- Python package: `requests`
- Modules: `base`, `mail`, `alba_loans`, `alba_investors`

### Steps

1. Copy `alba_integration` to your Odoo addons path.
2. Restart the Odoo server.
3. Enable developer mode.
4. Apps → Update Apps List.
5. Install **Alba Capital - Django Integration Bridge**.

### Install Order

```
1. alba_loans       ← must be installed first
2. alba_investors   ← must be installed second
3. alba_integration ← install last
```

---

## Configuration

### System Parameters

The following `ir.config_parameter` values are seeded on install and can be
customised under **Settings → Technical → System Parameters**:

| Parameter Key | Default | Description |
|---------------|---------|-------------|
| `alba.integration.api_version` | `1.0` | API version returned by /health |
| `alba.integration.webhook_timeout` | `30` | Outbound webhook HTTP timeout (seconds) |
| `alba.integration.max_retries` | `5` | Max retry attempts per webhook |
| `alba.integration.sync_log_retention_days` | `90` | Days to retain sync log records |
| `alba.integration.webhook_log_retention_days` | `60` | Days to retain webhook log records |
| `alba.loans.npl_threshold_days` | `90` | Days in arrears before loan is flagged NPL |

---

## Django Portal Setup

### 1. Install the service layer

The Django portal service layer is at:

```
loan_system/core/services/
├── __init__.py
├── odoo_sync.py     ← OdooSyncService (REST client)
├── mpesa.py         ← MpesaService (STK Push proxy)
└── webhooks.py      ← Webhook receiver view + HMAC verification
```

### 2. Add to `INSTALLED_APPS` and configure `.env`

```env
ODOO_URL=https://odoo.albacapital.co.ke
ODOO_API_KEY=<copy from Odoo API key record>
ODOO_WEBHOOK_SECRET=<copy from Odoo API key record>
ODOO_TIMEOUT=30
```

### 3. Wire the webhook URL

`config/urls.py` already includes:

```python
path("api/v1/webhooks/odoo/", odoo_webhook_receiver, name="odoo_webhook_receiver"),
```

Ensure the Odoo API key record's **Webhook Path** is set to `/api/v1/webhooks/odoo/`.

### 4. Verify end-to-end

```bash
# Test Odoo connectivity from Django
python manage.py shell -c "
from core.services.odoo_sync import OdooSyncService
s = OdooSyncService()
print(s.health_check())
print('Reachable:', s.is_reachable())
"
```

### 5. Test webhook signature

```bash
# From Odoo shell — fire a test webhook
api_key = env['alba.api.key'].search([('is_active','=',True)], limit=1)
api_key.send_webhook('integration.health_check', {'test': True})
```

Check the Django server logs for the received event.

---

## Operations Guide

### Daily Checks

| Check | Location |
|-------|----------|
| Any dead webhooks? | Alba Integration → Dead Webhooks |
| Sync failures in last 24h? | Alba Integration → Sync Logs → Failures |
| Pending retries overdue? | Alba Integration → Retry Queue (filter: Due Now) |
| M-Pesa transactions needing attention? | Alba Loans → M-Pesa → Needs Attention |

### Webhook Delivery Failure Runbook

1. Go to **Alba Integration → Retry Queue** and find the failing record.
2. Check **Last Error** and **Last HTTP Status**.
3. Common causes:
   - `status=0` — Django portal unreachable (check HTTPS / firewall).
   - `status=401` — Odoo webhook secret doesn't match Django `ODOO_WEBHOOK_SECRET`.
   - `status=500` — Django handler raised an exception (check Django logs).
4. Fix the root cause.
5. Click **Retry Now** on the dead record.
6. Alternatively, click **Re-queue** to restart the back-off cycle.

### Rotating API Credentials

1. **In Odoo:** Go to Alba Integration → API Keys → select the key.
2. Click **Regenerate API Key** (or **Rotate Webhook Secret**).
3. Copy the new value immediately (it is not shown again for the secret).
4. **In Django:** Update `.env`:
   ```env
   ODOO_API_KEY=<new_key>
   ODOO_WEBHOOK_SECRET=<new_secret>
   ```
5. Restart the Django server (or reload gunicorn workers).
6. Verify with a health check call.

### Purging Logs Manually

```python
# In Odoo shell — purge sync logs older than 30 days
from datetime import timedelta
cutoff = fields.Datetime.now() - timedelta(days=30)
env['alba.sync.log'].sudo().search([('create_date', '<', cutoff)]).unlink()
```

---

## Event Catalogue

Complete list of webhook events fired by the Alba Capital Odoo modules:

### `alba_loans` events

| Event | Trigger | Key Payload Fields |
|-------|---------|-------------------|
| `loan.disbursed` | Disbursement wizard | `odoo_loan_id`, `loan_number`, `django_application_id`, `disbursed_amount` |
| `loan.npl_flagged` | Daily NPL cron | `odoo_loan_id`, `loan_number`, `days_in_arrears` |
| `loan.closed` | Auto-close cron | `odoo_loan_id`, `loan_number`, `state` |
| `loan.instalment_overdue` | Daily overdue cron | `odoo_loan_id`, `days_overdue`, `balance_due`, `due_date` |
| `loan.maturing_soon` | Weekly maturity cron | `odoo_loan_id`, `maturity_date`, `outstanding_balance` |
| `payment.matched` | Repayment posted | `odoo_repayment_id`, `django_payment_id`, `principal_applied`, `interest_applied` |
| `payment.mpesa_received` | C2B / STK callback | `mpesa_code`, `amount`, `phone_number`, `loan_number` |
| `portfolio.stats_updated` | Every 6h portfolio cron | `total_active_loans`, `total_disbursed`, `npl_count`, `par_30_balance`, `par_90_balance` |

### `alba_integration` events

| Event | Trigger | Key Payload Fields |
|-------|---------|-------------------|
| `application.status_changed` | Application stage change | `odoo_application_id`, `django_application_id`, `new_status` |
| `customer.kyc_verified` | KYC status update | `odoo_customer_id`, `django_customer_id`, `kyc_status` |
| `integration.health_check` | Every 6h health cron | `window_hours`, `inbound`, `outbound`, `total` |
| `integration.dead_webhooks_alert` | Daily dead-retry cron | `dead_count`, `action_required` |

---

## Troubleshooting

### "Invalid or inactive API key" (HTTP 403)

- Check that `ODOO_API_KEY` in Django `.env` matches the **Key** field on the
  Odoo API key record exactly (no trailing whitespace).
- Verify the key record is **Active** (`is_active = True`).
- If IP allowlisting is enabled, check that the Django server's egress IP
  is in the **Allowed IP Addresses** list.

### Webhooks not arriving in Django

1. Check **Alba Integration → Webhook Logs** — is the delivery being attempted?
2. If logs show HTTP 0 or a connection error, the Django URL is unreachable
   from Odoo. Verify the **Django Portal URL** on the API key record and that
   the URL is publicly accessible from the Odoo server.
3. If logs show HTTP 401 from Django, the `ODOO_WEBHOOK_SECRET` in Django
   `.env` does not match the **Webhook Secret** on the Odoo API key record.
4. Check **Alba Integration → Retry Queue** — are retries being attempted?

### Duplicate customer / application in Odoo

The `django_customer_id` and `django_application_id` fields have unique
constraints. If a duplicate is attempted, Odoo returns HTTP 409.

On the Django side, always persist `odoo_customer_id` / `odoo_application_id`
after a successful create call so subsequent calls update rather than create.

### Cron jobs not running

Go to **Settings → Technical → Scheduled Actions** and search "Alba" to verify
that all crons are **Active** and have a sensible **Next Execution Date**.

If a cron has `numbercall = 0` it has been exhausted — set `numbercall = -1`
to make it run indefinitely.

---

## Changelog

### 19.0.1.0.0 (initial release)

- REST API endpoints: health, loan-products, customers, KYC, applications,
  application-status, payments, mpesa/stk-push, mpesa/stk-status
- Outbound HMAC-SHA256-signed webhooks with retry queue
- `alba.webhook.retry` model — exponential back-off retry with Odoo UI
- `alba.sync.log` model — full inbound/outbound sync audit log with retention cron
- 5 scheduled cron jobs: retry queue processor, log purge, health check,
  webhook log purge, dead retry alert
- API key management: auto-generated key + secret, regeneration, rotation,
  IP allowlisting, last-used tracking
- Security groups: Integration User, Integration Admin
- Updated menus: Retry Queue, Dead Webhooks, Sync Logs, Sync Failures