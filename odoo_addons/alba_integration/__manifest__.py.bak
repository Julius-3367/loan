# -*- coding: utf-8 -*-
{
    "name": "Alba Capital - Django Integration Bridge",
    "version": "19.0.1.0.0",
    "category": "Technical",
    "summary": "REST API bridge, M-Pesa callbacks, webhook retry queue and sync audit log for the Django portal",
    "description": """
Alba Capital - Django Integration Bridge
=========================================

This module is the integration layer between the Alba Capital Django customer
portal and Odoo Enterprise.  It exposes REST API endpoints that the Django
portal calls to synchronise customers, loan applications, and payments, and
it sends HMAC-signed webhook POST requests back to Django whenever key status
changes occur inside Odoo.

Architecture
------------
Django → Odoo (inbound REST endpoints)
  GET   /alba/api/v1/health                          Liveness probe
  GET   /alba/api/v1/loan-products                   List active products
  POST  /alba/api/v1/customers                       Create / update customer
  POST  /alba/api/v1/customers/<id>/kyc              Update KYC status
  POST  /alba/api/v1/applications                    Submit loan application
  PATCH /alba/api/v1/applications/<id>/status        Change application state
  POST  /alba/api/v1/payments                        Record a repayment

Odoo → Django (outbound HMAC-signed webhooks)
  application.status_changed     Application moved to a new stage
  loan.disbursed                 Loan disbursed and active
  loan.npl_flagged               Loan flagged as Non-Performing
  loan.closed                    Loan fully repaid and closed
  loan.instalment_overdue        Instalment past due date
  loan.maturing_soon             Loan maturing within 30 days
  payment.matched                Repayment posted and allocated
  payment.mpesa_received         Inbound M-Pesa payment received
  customer.kyc_verified          KYC status updated to verified
  portfolio.stats_updated        Aggregate portfolio statistics
  integration.health_check       Periodic sync health summary
  integration.dead_webhooks_alert Dead retry records detected

Authentication
--------------
Inbound requests from Django must include an X-Alba-API-Key HTTP header
whose value matches an active alba.api.key record.

Outbound webhooks to Django are signed with HMAC-SHA256 and the signature
is sent in the X-Alba-Signature header as sha256=<hex_digest>.

Retry Queue
-----------
Failed webhook deliveries are automatically enqueued in alba.webhook.retry.
The system retries on an exponential back-off schedule (2 min → 5 min →
15 min → 1 hour → 4 hours).  After 5 attempts the record is marked 'dead'
and requires operator review.  A daily cron fires an alert webhook to Django
when dead records are present.

Sync Audit Log
--------------
Every inbound API call and outbound webhook delivery is recorded in
alba.sync.log for full auditability.  A weekly cron purges records older
than the configured retention period (default: 90 days).
    """,
    "author": "Alba Capital",
    "website": "https://albacapital.co.ke",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "alba_loans",
        "alba_investors",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        # ── Security — always first ──────────────────────────────────────────
        "security/security.xml",
        "security/ir.model.access.csv",
        # ── Seed / system parameters ─────────────────────────────────────────
        "data/integration_data.xml",
        # ── Scheduled actions (crons) ────────────────────────────────────────
        "data/cron_data.xml",
        # ── Views ────────────────────────────────────────────────────────────
        "views/api_key_views.xml",
        "views/webhook_log_views.xml",
        "views/webhook_retry_views.xml",
        "views/sync_log_views.xml",
        # ── Menus (after all actions are defined) ────────────────────────────
        "views/menus.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
    "auto_install": False,
    "sequence": 30,
}
