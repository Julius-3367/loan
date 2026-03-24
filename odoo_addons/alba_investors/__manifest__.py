# -*- coding: utf-8 -*-
{
    "name": "Alba Capital - Investor Management",
    "version": "19.0.1.0.0",
    "category": "Finance",
    "summary": "Investor profiles, investment accounts, compound interest accrual and monthly statement generation",
    "description": """
Alba Capital Investor Management
==================================
Manages the full investor lifecycle for Alba Capital:

* Investor profiles linked to Odoo contacts (res.partner)
* KYC management with verification workflow
* Investment accounts (fixed-term and open-ended)
* Monthly compound interest accrual via scheduled cron job
* Automated accounting journal entries for interest accrual
* Monthly investor statements auto-generated and emailed
* Portfolio value tracking per investor
* Integration with Alba Loans module for fund utilisation reporting
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
        "alba_loans",
    ],
    "data": [
        # Security — always first
        "security/security.xml",
        "security/ir.model.access.csv",
        # Master data / sequences / crons
        "data/sequence_data.xml",
        "data/cron_data.xml",
        # Views
        "views/investor_views.xml",
        "views/investment_views.xml",
        "views/investment_statement_views.xml",
        "views/menus.xml",
        # Wizards
        "wizard/generate_statement_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 20,
}
