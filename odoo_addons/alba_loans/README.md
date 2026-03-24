# Alba Capital — Loan Management (`alba_loans`)

> Odoo 19 Enterprise module — core loan lifecycle management with M-Pesa Daraja integration.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Module Structure](#module-structure)
4. [Models](#models)
5. [M-Pesa Integration](#m-pesa-integration)
6. [Automation & Cron Jobs](#automation--cron-jobs)
7. [Security Groups](#security-groups)
8. [Installation](#installation)
9. [Configuration](#configuration)
10. [Accounting Setup](#accounting-setup)
11. [Usage Guide](#usage-guide)
12. [API / Webhook Events Fired](#api--webhook-events-fired)
13. [Changelog](#changelog)

---

## Overview

`alba_loans` is the core lending engine for Alba Capital's Odoo Enterprise instance.
It manages the full loan lifecycle — from customer KYC and 9-stage application
workflow through disbursement, repayment scheduling, accounting automation, and
portfolio risk monitoring.

It also provides **native M-Pesa Daraja API integration** (STK Push, C2B Paybill/Till,
B2C payouts) with a full transaction audit log and automated reconciliation.

---

## Features

### Loan Products
- Configurable products: Salary Advance, Business Loan, Asset Financing
- Per-product interest rates (flat rate and reducing balance)
- Origination fee, insurance fee, processing fee (as % of principal)
- Minimum/maximum amount and tenure constraints
- Per-product accounting account mapping (loan receivable, interest income, fee income)

### Customer Management
- KYC profiles linked to `res.partner`
- Identity verification workflow (pending → submitted → verified / rejected)
- Employment and income information
- Employer verification support

### 9-Stage Application Workflow
```
Draft → Submitted → Under Review → Credit Analysis → Pending Approval
→ Approved → Employer Verification → Guarantor Confirmation → Disbursed
```
With parallel exit paths to `Rejected` and `Cancelled`.

- Automated stage timestamps and responsible user capture
- Conditions of approval field
- Indicative totals (estimated interest, fees, total repayable) computed on the fly
- Kanban pipeline view

### Loan Disbursement
- Wizard-driven disbursement with accounting journal entry
  - DR Loan Receivable
  - CR Bank / Cash Account
- Automatic repayment schedule generation (flat rate or reducing balance)
- Support for weekly, fortnightly, and monthly repayment frequencies

### Repayment Management
- Payment allocation: principal → interest → fees → penalties
- Auto-allocation algorithm (uses overdue schedule entries, oldest first)
- Accounting journal entry on posting:
  - DR Bank / Cash
  - CR Loan Receivable (principal)
  - CR Interest Income
  - CR Fee Income / Penalty Income
- Reversal support with reason tracking
- M-Pesa transaction ID deduplication constraint

### Portfolio Risk (PAR)
- Daily PAR bucket computation: Current, 1–30, 31–60, 61–90, 91–180, >180 days
- Arrears amount and days-in-arrears fields
- Auto-NPL flagging when `days_in_arrears >= 90` (configurable threshold)
- Auto-close of fully repaid loans

### Reports
- QWeb loan statement PDF (printable per loan)

---

## Features — M-Pesa Integration

See the dedicated [M-Pesa section](#m-pesa-integration) below.

---

## Module Structure

```
alba_loans/
├── __init__.py
├── __manifest__.py
├── README.md
│
├── controllers/
│   ├── __init__.py
│   └── mpesa_callback.py       # Daraja callback HTTP endpoints
│
├── data/
│   ├── sequence_data.xml       # Sequences for loan/application numbers
│   └── cron_data.xml           # 8 scheduled automation jobs
│
├── models/
│   ├── __init__.py
│   ├── customer.py             # alba.customer — KYC customer profiles
│   ├── loan_product.py         # alba.loan.product — configurable products
│   ├── loan_application.py     # alba.loan.application — 9-stage workflow
│   ├── loan.py                 # alba.loan — active loan + cron methods
│   ├── loan_repayment.py       # alba.loan.repayment — payment posting
│   ├── repayment_schedule.py   # alba.repayment.schedule — amortisation
│   ├── mpesa_config.py         # alba.mpesa.config — Daraja credentials
│   └── mpesa_transaction.py    # alba.mpesa.transaction — audit log
│
├── report/
│   ├── loan_statement_report.xml
│   └── loan_statement_template.xml
│
├── security/
│   ├── security.xml            # Groups: loan_user, loan_officer, loan_manager
│   └── ir.model.access.csv
│
├── views/
│   ├── customer_views.xml
│   ├── loan_product_views.xml
│   ├── loan_application_views.xml
│   ├── loan_views.xml
│   ├── repayment_views.xml
│   ├── mpesa_config_views.xml
│   ├── mpesa_transaction_views.xml
│   └── menus.xml
│
└── wizard/
    ├── __init__.py
    ├── loan_disburse_wizard.py
    ├── loan_disburse_wizard_views.xml
    ├── mpesa_stk_push_wizard.py
    └── mpesa_stk_push_wizard_views.xml
```

---

## Models

### `alba.customer`
KYC customer profile linked to `res.partner`.

| Field | Type | Description |
|-------|------|-------------|
| `customer_number` | Char | Auto-generated sequence `ALB-CUST-XXXXX` |
| `partner_id` | Many2one | Linked Odoo contact |
| `id_number` | Char | National ID / Passport |
| `kyc_status` | Selection | pending → submitted → verified / rejected |
| `employer_name` | Char | Current employer |
| `monthly_income` | Monetary | Declared monthly income |
| `django_customer_id` | Integer | Sync key — Django portal User PK |

### `alba.loan.product`
Configurable loan product template.

| Field | Type | Description |
|-------|------|-------------|
| `code` | Char | Unique product code (e.g. `SAL-ADV-001`) |
| `category` | Selection | salary_advance / business_loan / asset_financing |
| `interest_rate` | Float | Monthly interest rate (%) |
| `interest_method` | Selection | flat_rate / reducing_balance |
| `account_loan_receivable_id` | Many2one | Accounting: loan receivable account |
| `account_interest_income_id` | Many2one | Accounting: interest income account |
| `account_fees_income_id` | Many2one | Accounting: fee income account |

### `alba.loan.application`
9-stage loan application workflow.

| Field | Type | Description |
|-------|------|-------------|
| `application_number` | Char | Auto-generated `APP-XXXXXX` |
| `state` | Selection | 9 stages + rejected/cancelled |
| `requested_amount` | Monetary | Customer-requested amount |
| `approved_amount` | Monetary | Officer-approved amount |
| `django_application_id` | Integer | Django portal sync key |

### `alba.loan`
Active loan record created on disbursement.

| Field | Type | Description |
|-------|------|-------------|
| `loan_number` | Char | Auto-generated `LN-XXXXXX` |
| `outstanding_balance` | Monetary | Computed: total_repayable − total_paid |
| `days_in_arrears` | Integer | Days since oldest overdue instalment |
| `par_bucket` | Selection | Current / 1-30 / 31-60 / 61-90 / 91-180 / >180 |
| `state` | Selection | active / closed / npl / written_off |
| `django_loan_id` | Integer | Django portal sync key |

### `alba.repayment.schedule`
Individual instalment row generated by the disbursement wizard.

### `alba.loan.repayment`
Payment record against an active loan.

| Field | Type | Description |
|-------|------|-------------|
| `payment_method` | Selection | mpesa / bank_transfer / cash / cheque / rtgs |
| `mpesa_transaction_id` | Char | M-Pesa receipt code (unique constraint) |
| `state` | Selection | draft → posted → reversed |

### `alba.mpesa.config`
Daraja API configuration. See [M-Pesa Integration](#m-pesa-integration).

### `alba.mpesa.transaction`
M-Pesa transaction audit log. See [M-Pesa Integration](#m-pesa-integration).

---

## M-Pesa Integration

### Overview

The M-Pesa integration uses the [Safaricom Daraja API v1](https://developer.safaricom.co.ke/Documentation).
It supports three transaction flows:

| Flow | Direction | Purpose |
|------|-----------|---------|
| **STK Push** (Lipa Na M-Pesa Online) | Outbound → Customer | Request payment from customer's handset |
| **C2B** (Customer to Business) | Inbound ← Safaricom | Receive Paybill / Till payments automatically |
| **B2C** (Business to Customer) | Outbound → Customer | Investor payouts / refunds |

### Configuration

1. In Odoo, go to **Alba Loans → M-Pesa → M-Pesa Configuration**.
2. Create a new configuration record:

| Field | Value |
|-------|-------|
| **Environment** | `Sandbox` for testing, `Production` for live |
| **Consumer Key** | From [Daraja portal](https://developer.safaricom.co.ke) |
| **Consumer Secret** | From Daraja portal |
| **Business Short Code** | Your Paybill number (e.g. `174379` for sandbox) |
| **Till Number** | Optional — only for Buy Goods transactions |
| **Passkey** | Lipa Na M-Pesa passkey (required for STK Push) |
| **Callback Base URL** | Public HTTPS URL of this Odoo instance |

3. Click **Test Connection** to verify your credentials.
4. Click **Register C2B URLs** to push the validation and confirmation callback
   URLs to Safaricom.

### Callback Endpoints

These are automatically computed from **Callback Base URL**:

| Endpoint | Purpose |
|----------|---------|
| `POST /alba/mpesa/stk/callback` | STK Push result |
| `POST /alba/mpesa/c2b/validation` | C2B payment validation |
| `POST /alba/mpesa/c2b/confirmation` | C2B payment confirmation |
| `POST /alba/mpesa/b2c/result` | B2C payout result |
| `POST /alba/mpesa/b2c/timeout` | B2C queue timeout |
| `GET  /alba/mpesa/health` | Liveness probe |

Register `/alba/mpesa/stk/callback`, `/alba/mpesa/b2c/result`, and
`/alba/mpesa/b2c/timeout` manually in the [Daraja portal](https://developer.safaricom.co.ke).

### STK Push Flow

1. Open a loan in **Alba Loans → Loans → Active Loans**.
2. Click **Request M-Pesa Payment** (visible on the loan form header).
3. The wizard pre-fills the customer's phone, the next instalment amount,
   and the loan number as account reference.
4. Click **Send STK Push**.
5. The customer receives a payment prompt on their phone.
6. Safaricom fires a callback to `/alba/mpesa/stk/callback`.
7. The `alba.mpesa.transaction` record is updated automatically.
8. A pending **Retry cron** (every 30 min) re-queries any transactions
   that have not received a callback.

### C2B Payment Flow

When a customer pays to the Paybill / Till directly:

1. Safaricom calls `/alba/mpesa/c2b/validation` — the handler checks that
   the `BillRefNumber` (loan number) exists and is an active loan.
2. Safaricom calls `/alba/mpesa/c2b/confirmation` — an `alba.mpesa.transaction`
   record is created and auto-matched to the loan.
3. The **hourly auto-reconcile cron** creates a draft `alba.loan.repayment`
   for every completed, unreconciled transaction with a matched loan.
4. An officer opens the draft repayment, reviews the allocation, and clicks **Post**.

### Transaction Reconciliation

Go to **Alba Loans → M-Pesa → Needs Attention** to see all completed transactions
that have not been reconciled to a repayment.

- **Auto-Match Loan** — match by account reference (loan number).
- **Reconcile to Loan** — create a draft repayment.
- **Query Status** — re-query Safaricom for pending STK transactions.

### Sandbox Testing

Use the [Daraja sandbox](https://developer.safaricom.co.ke/test_credentials):

| Setting | Sandbox Value |
|---------|--------------|
| Short Code | `174379` |
| Passkey | `bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919` |
| Test MSISDN | `254708374149` |
| Consumer Key | From your sandbox app on the Daraja portal |

---

## Automation & Cron Jobs

Eight scheduled actions are installed with the module:

| Job | Schedule | Description |
|-----|----------|-------------|
| **Update PAR Buckets** | Daily | Recompute days_in_arrears / par_bucket for all active loans |
| **NPL Monitor** | Daily | Flag loans with ≥ 90 days arrears as Non-Performing |
| **Overdue Payment Alerts** | Daily | Post chatter alerts at 1, 3, 7, 14, 30 days overdue |
| **Maturity Date Reminders** | Weekly | Alert officers for loans maturing within 30 days |
| **Auto-close Repaid Loans** | Daily | Close loans with outstanding_balance ≤ 0 |
| **Query Pending STK** | Every 30 min | Re-query Safaricom for unresolved STK transactions |
| **Auto-reconcile M-Pesa** | Hourly | Match completed transactions to loans and create draft repayments |
| **Push Portfolio Stats** | Every 6 hours | Send aggregate PAR / NPL metrics to Django via webhook |

All crons are installed with `noupdate="1"` so they can be adjusted per
deployment without being overwritten on module upgrade.

Configure the NPL threshold (default 90 days):

```
Settings → Technical → System Parameters → alba.loans.npl_threshold_days
```

---

## Security Groups

| Group | Technical ID | Permissions |
|-------|-------------|-------------|
| **Loan User** | `alba_loans.group_loan_user` | Read-only on customers, applications, loans, repayments |
| **Loan Officer** | `alba_loans.group_loan_officer` | Full create/edit; can post repayments; access M-Pesa transactions |
| **Loan Manager** | `alba_loans.group_loan_manager` | All of the above + delete + product/M-Pesa config management + reversal |

---

## Installation

### Prerequisites

- Odoo 19 Enterprise
- Python package: `requests` (`pip install requests`)
- Modules: `base`, `account`, `mail`, `contacts`, `base_setup`

### Steps

1. Copy the `alba_loans` directory to your Odoo addons path.
2. Restart the Odoo server.
3. Enable developer mode: `Settings → Activate Developer Mode`.
4. Go to `Apps → Update Apps List`.
5. Search for **Alba Capital - Loan Management** and click **Install**.

### Install Order

Install modules in this order to satisfy dependencies:

```
1. alba_loans
2. alba_investors   (depends on alba_loans)
3. alba_integration (depends on alba_loans + alba_investors)
```

---

## Configuration

### After Installation Checklist

- [ ] Create at least one **Loan Product** (`Alba Loans → Configuration → Loan Products`)
      and set the accounting accounts on it.
- [ ] Create a **M-Pesa Configuration** record and click **Test Connection**.
- [ ] Click **Register C2B URLs** on the M-Pesa config.
- [ ] Register the STK callback URL in the [Daraja portal](https://developer.safaricom.co.ke).
- [ ] Review and activate cron jobs (`Settings → Technical → Scheduled Actions`,
      filter by "Alba").
- [ ] Assign users to the appropriate security groups.

---

## Accounting Setup

Map the following accounts on each **Loan Product**:

| Field | Account Type | Example |
|-------|-------------|---------|
| Loan Receivable Account | Asset — Receivable / Current | `1201 Loans Receivable` |
| Interest Income Account | Income | `4101 Interest Income` |
| Fee Income Account | Income | `4102 Loan Fee Income` |

On each **Loan** record, set:
- **Disbursement Journal** — the Bank or Cash journal to credit on disbursement.

On each **Repayment** record, set:
- **Payment Journal** — the Bank or Cash journal to debit on repayment posting.

---

## Usage Guide

### Creating a Loan Application

1. **Alba Loans → Customers** — create the customer KYC profile.
2. **Alba Loans → Loan Applications → Pipeline** — click **New**.
3. Fill in Customer, Loan Product, Requested Amount, Tenure, Purpose.
4. Click **Submit** to move from Draft → Submitted.
5. Progress through the 9 stages using the header buttons.
6. At **Approved** stage, set the **Approved Amount** and any conditions.
7. Click **Disburse Loan** to open the disbursement wizard.

### Disbursing a Loan

1. From an approved application, click **Disburse Loan**.
2. In the wizard, confirm:
   - Disbursement date
   - Disbursement journal (bank/cash account)
   - Actual disbursement amount
3. Click **Disburse** — this:
   - Creates an `alba.loan` record.
   - Posts the disbursement accounting journal entry.
   - Generates the full repayment schedule.
   - Fires a `loan.disbursed` webhook to the Django portal.

### Recording a Repayment

**Manual entry:**
1. Open the loan → click **Add Repayment** (or go to **Repayments → New**).
2. Fill in Payment Date, Amount, Payment Method, M-Pesa Transaction ID.
3. Click **Auto-Allocate** to distribute across principal / interest / fees.
4. Click **Post** to post the accounting entry.

**Via M-Pesa STK Push:**
1. Open the loan → click **Request M-Pesa Payment**.
2. Fill in the wizard and click **Send STK Push**.
3. Wait for the customer to confirm on their phone.
4. The cron will auto-reconcile the completed transaction to a draft repayment.
5. Open the draft repayment, review allocation, click **Post**.

---

## API / Webhook Events Fired

This module fires the following webhook events to the Django portal
(via `alba_integration`):

| Event | Trigger |
|-------|---------|
| `loan.disbursed` | Loan disbursement wizard completed |
| `loan.npl_flagged` | Daily NPL monitor cron flags loans ≥ 90 days arrears |
| `loan.closed` | Auto-close cron closes fully-repaid loans |
| `loan.instalment_overdue` | Daily overdue alert cron (at 1/3/7/14/30 days) |
| `loan.maturing_soon` | Weekly maturity reminder cron |
| `payment.matched` | Repayment posted and accounting entry created |
| `payment.mpesa_received` | C2B confirmation or STK callback received |
| `portfolio.stats_updated` | Every-6-hours portfolio stats cron |

All events are signed with HMAC-SHA256 and include a `delivery_id` UUID for
idempotency on the Django side.

---

## Changelog

### 19.0.1.0.0 (initial release)
- Core loan lifecycle: products, applications (9 stages), disbursement, repayment
- M-Pesa Daraja API: STK Push, C2B Paybill/Till, B2C payouts
- Full M-Pesa transaction audit log with auto-reconciliation
- 8 scheduled automation cron jobs
- PAR tracking, NPL auto-flagging, auto-close
- Webhook events for all key state transitions
- QWeb loan statement PDF report
- Security groups: Loan User, Loan Officer, Loan Manager