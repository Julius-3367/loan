# Alba Capital — Odoo Custom Add-ons

This directory contains the three custom Odoo 16/17 Enterprise modules that power
Alba Capital's back-office lending, investor management, and portal integration.

```
ACCT.f/
├── loan_system/          ← Django customer-facing portal (existing)
└── odoo_addons/          ← This directory — Odoo custom modules
    ├── alba_loans/       ← Core loan management
    ├── alba_investors/   ← Investor & fund management
    └── alba_integration/ ← Django ↔ Odoo API bridge
```

---

## Modules

### 1. `alba_loans` — Core Loan Management
| Feature | Detail |
|---|---|
| Loan Products | Configurable salary advance / business loan / asset financing products |
| Customer Profiles | KYC-linked customer records, credit scores, employment data |
| Application Workflow | 9-stage pipeline: Draft → Submitted → Under Review → Credit Analysis → Pending Approval → Approved → Employer Verification → Guarantor Confirmation → Disbursed (+ Rejected / Cancelled terminals) |
| Active Loans | Principal, balance, PAR bucket, days-in-arrears tracking |
| Repayment Schedules | Auto-generated amortisation schedules (flat rate & reducing balance) |
| Accounting Automation | Journal entries posted automatically on disbursement and repayment |
| Reports | Loan statement PDF, PAR / NPL report |

### 2. `alba_investors` — Investor & Fund Management
| Feature | Detail |
|---|---|
| Investor Profiles | KYC, bank/M-Pesa payout details |
| Investments | Fixed-term and open-ended investment accounts |
| Compound Interest | Monthly cron accrues compound interest on each active investment |
| Statements | Monthly statements auto-generated and emailed on the 2nd of each month |
| Accounting | Journal entries for interest accrual (DR Interest Expense / CR Interest Payable) |

### 3. `alba_integration` — Django Portal & Payment API Bridge
| Feature | Detail |
|---|---|
| Inbound REST API | Endpoints under `/alba/api/v1/` — customers, applications, payments, KYC |
| Outbound Webhooks | HMAC-SHA256 signed POST to Django on status changes, disbursements, payments |
| API Key Management | Per-key tokens, IP allowlists, rotation actions |
| Webhook Logs | Full inbound/outbound log with response codes and duration |

---

## Integration Flow

```
Django Portal                           Odoo Enterprise
─────────────────────────────────────────────────────────
Customer registers      ──POST /customers──►  Create res.partner + alba.customer
Customer applies        ──POST /applications─►  Create alba.loan.application (DRAFT)
Customer submits form   ──PATCH /applications/<id>/status─► Transition to SUBMITTED
                                                ↓
                        Officer reviews in Odoo Kanban board
                                                ↓
                        Status change          ──webhook application.status_changed──►  Django updates portal
                                                ↓
                        Loan disbursed         ──webhook loan.disbursed──►  Django marks loan active
                                                ↓
Customer makes payment  ──POST /payments──►  Create + post alba.loan.repayment
                        ◄──webhook payment.matched──  Django shows receipt
```

---

## Deployment

### Odoo.sh
1. Add this `odoo_addons/` folder as the custom addons path in your Odoo.sh project.
2. Push to the linked GitHub repository; Odoo.sh will auto-install.

### Private VPS / Cloud
1. Copy the three module folders into your Odoo server's `addons/` directory.
2. Restart Odoo: `sudo systemctl restart odoo`
3. Activate developer mode in Odoo → Apps → Update App List.
4. Install in order: `alba_loans` → `alba_investors` → `alba_integration`.

### Configuration after install
1. **Odoo side:** Go to *Alba Integration → API Keys* and create a new key for the Django portal.
   Copy the generated **Key** and **Webhook Secret**.
2. **Django side:** Paste values into `.env`:
   ```
   ODOO_API_KEY=<key>
   ODOO_WEBHOOK_SECRET=<secret>
   ODOO_URL=https://your-odoo-instance.com
   ```
3. Map account codes: *Alba Loans → Configuration → Loan Products* — set the
   accounting accounts on each product (Loan Receivable, Interest Income, Fees Income).

---

## Development

```bash
# Lint Python files
python -m py_compile alba_loans/models/*.py
python -m py_compile alba_investors/models/*.py
python -m py_compile alba_integration/models/*.py
python -m py_compile alba_integration/controllers/*.py

# Validate XML files
xmllint --noout alba_loans/views/*.xml
xmllint --noout alba_investors/views/*.xml
xmllint --noout alba_integration/views/*.xml
```

---

## Dependencies

| Module | Odoo Dependencies |
|---|---|
| `alba_loans` | `base`, `account`, `mail`, `contacts` |
| `alba_investors` | `base`, `account`, `mail`, `contacts`, `alba_loans` |
| `alba_integration` | `base`, `mail`, `alba_loans`, `alba_investors` |

---

*Alba Capital ERP — Confidential*