# -*- coding: utf-8 -*-
{
    "name": "Alba Capital - Loan Management",
    "version": "19.0.1.0.0",
    "category": "Finance",
    "summary": "Core loan management: products, applications, disbursements, repayments, M-Pesa integration and accounting automation",
    "description": """
Alba Capital Loan Management
==============================
Manages the full loan lifecycle for Alba Capital:

* Configurable loan products (salary advance, business loan, asset financing)
* Customer KYC profiles linked to res.partner
* 9-stage application workflow with Kanban board
* Automated amortisation schedule generation (flat rate & reducing balance)
* Disbursement wizard with automatic journal entry posting
* Repayment posting with principal / interest / fees split
* PAR (Portfolio at Risk) and NPL tracking with automatic daily cron
* Overdue payment alerts (1, 3, 7, 14, 30 days)
* Maturity date reminders (weekly)
* Auto-close fully-repaid loans (daily cron)
* Portfolio stats push to Django portal (every 6 hours)

M-Pesa (Daraja API) Integration
---------------------------------
* Daraja OAuth2 token management with in-process caching
* STK Push (Lipa Na M-Pesa Online) — request payment directly from a loan form
* C2B Paybill / Till — receive inbound payments via Safaricom callbacks
* B2C payouts — investor interest disbursements via M-Pesa
* Full M-Pesa transaction audit log with reconciliation workflow
* Auto-reconciliation cron (hourly) — matches completed transactions to loans
* Pending STK query cron (every 30 min) — resolves stalled transactions

Accounting
-----------
* Loan statement PDF report (QWeb)
* Full audit trail via mail.thread chatter
    """,
    "author": "Alba Capital",
    "website": "https://www.albacapital.co.ke",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "mail",
        "contacts",
        "base_setup",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        # ── Security — always first ──────────────────────────────────────────
        "security/security.xml",
        "security/ir.model.access.csv",
        # ── Master data / sequences ──────────────────────────────────────────
        "data/sequence_data.xml",
        # ── Scheduled actions (crons) ────────────────────────────────────────
        "data/cron_data.xml",
        # ── Actions — must load before views that reference them ─────────────
        "views/actions.xml",
        # ── Loan management views (load basic views first) ───────────────────
        "views/customer_views.xml",
        "views/loan_product_views.xml",
        "views/loan_application_views.xml",
        "views/repayment_views.xml",
        # ── M-Pesa views ────────────────────────────────────────────────────
        "views/mpesa_config_views.xml",
        "views/mpesa_transaction_views.xml",
        # ── Loan views with computed fields (load last to ensure models ready) ─
        "views/loan_views.xml",
        # ── Menus (after all actions are defined) ────────────────────────────
        "views/menus.xml",
        # ── Wizards ──────────────────────────────────────────────────────────
        "wizard/loan_disburse_wizard_views.xml",
        "wizard/mpesa_stk_push_wizard_views.xml",
        # ── Reports ──────────────────────────────────────────────────────────
        "report/loan_statement_report.xml",
        "report/loan_statement_template.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 10,
}
