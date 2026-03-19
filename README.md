# Alba Capital — Loan Customer Portal

**Django 5.0.2 · Python 3.12 · PostgreSQL · Odoo 19 Enterprise**

---

## 📋 Overview

Alba Capital is a financial services platform split across two systems:

| Layer | Technology | Responsibility |
|---|---|---|
| **Customer Portal** | Django 5.0.2 (this repo) | Public-facing loan application UI |
| **ERP Backend** | Odoo 19 Enterprise | Staff workflows, accounting, HR, payroll, CRM |
| **Database** | PostgreSQL | Shared persistent store |

Customers register, complete their KYC profile, apply for loans, upload documents, add guarantors, and track their active loans — all through this Django portal. Everything that happens after a customer submits an application (credit review, approval, disbursement, repayment tracking, accounting entries) is handled entirely inside Odoo.

---

## 🏗️ Architecture

```
┌─────────────────────────────────┐        ┌──────────────────────────────────┐
│      Django Customer Portal     │        │       Odoo 19 Enterprise          │
│                                 │        │                                  │
│  - Landing page                 │        │  - Loan processing & approval    │
│  - Customer registration        │◄──────►│  - Credit scoring & KYC review   │
│  - KYC profile & documents      │  REST  │  - Loan disbursement             │
│  - Loan application form        │  API   │  - Repayment & collections       │
│  - Application status tracking  │        │  - Accounting & GL               │
│  - Active loan dashboard        │        │  - HR & payroll                  │
│                                 │        │  - Investor reporting            │
└────────────┬────────────────────┘        └──────────────┬───────────────────┘
             │                                             │
             └──────────────┬──────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │   PostgreSQL   │
                    └────────────────┘
```

---

## 🗂️ Project Structure

```
loan_system/
├── config/                  # Django project settings & URLs
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                    # Auth, RBAC, dashboards, audit log
│   ├── models.py            # User (email-based), AuditLog
│   ├── views.py             # Login, register, dashboards, user approval
│   ├── forms.py             # LoginForm, UserRegistrationForm
│   └── urls.py
├── loans/                   # Customer loan portal
│   ├── models.py            # LoanProduct, Customer, LoanApplication, Loan …
│   ├── views.py             # Customer-facing views only
│   ├── forms.py             # CustomerProfileForm, LoanApplicationForm …
│   └── urls.py
├── templates/
│   ├── base.html
│   ├── landing.html
│   ├── core/                # login, register, dashboards, user_approval
│   └── loans/
│       └── customer/        # dashboard, apply, profile, my_applications …
├── static/
├── manage.py
└── requirements.txt
```

---

## ⚙️ Tech Stack

| Component | Version |
|---|---|
| Python | 3.12 |
| Django | 5.0.2 |
| PostgreSQL driver | psycopg2-binary 2.9.9 |
| Django REST Framework | 3.14.0 |
| Gunicorn | 21.2.0 |
| WhiteNoise | 6.6.0 |
| python-decouple | 3.8 |

---

## 🚀 Quick Start

### 1. Clone & create the virtual environment

```bash
git clone <repo-url>
cd loan_system

python3.12 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in every value — especially `DB_NAME`, `DB_PASSWORD`, and `SECRET_KEY`:

```ini
SECRET_KEY=change-this-to-a-long-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=your_chosen_db_name
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432
```

### 4. Create the PostgreSQL database

```bash
psql -U postgres -c "CREATE DATABASE your_chosen_db_name;"
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. Start the development server

```bash
python manage.py runserver
```

Visit **http://127.0.0.1:8000**

---

## 👤 User Roles

| Role | Access |
|---|---|
| `CUSTOMER` | Customer portal — apply for loans, track applications & repayments |
| `ADMIN` | Django admin panel — manage users, approve registrations |
| `CREDIT_OFFICER` | Odoo — process and approve loan applications |
| `FINANCE_OFFICER` | Odoo — accounting, disbursement |
| `HR_OFFICER` | Odoo — HR & payroll |
| `MANAGEMENT` | Odoo — reporting & analytics |
| `INVESTOR` | Odoo — investor portal |

New customer registrations require admin approval before the account becomes active.

---

## 🔐 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key |
| `DEBUG` | ✅ | `True` for dev, `False` for production |
| `ALLOWED_HOSTS` | ✅ | Comma-separated list of allowed hosts |
| `DB_NAME` | ✅ | PostgreSQL database name |
| `DB_USER` | ✅ | PostgreSQL user (default: `postgres`) |
| `DB_PASSWORD` | ✅ | PostgreSQL password |
| `DB_HOST` | ✅ | Database host (default: `localhost`) |
| `DB_PORT` | ✅ | Database port (default: `5432`) |
| `SESSION_COOKIE_SECURE` | | Set `True` in production |
| `CSRF_COOKIE_SECURE` | | Set `True` in production |
| `EMAIL_BACKEND` | | Console backend by default |

---

## 🌐 URL Map

| URL | View | Description |
|---|---|---|
| `/` | `landing_page` | Public landing page |
| `/login/` | `LoginView` | Customer / admin login |
| `/register/` | `RegisterView` | New customer registration |
| `/logout/` | `logout_view` | Logout |
| `/dashboard/` | `DashboardView` | Role-based redirect |
| `/customer/dashboard/` | `CustomerDashboardView` | Customer overview |
| `/admin-panel/` | `AdminDashboardView` | Admin overview |
| `/users/approval/` | `user_approval_list` | Pending account approvals |
| `/loans/` | `customer_loan_dashboard` | Loan dashboard |
| `/loans/profile/` | `customer_profile` | KYC profile |
| `/loans/apply/` | `apply_for_loan` | New loan application |
| `/loans/applications/` | `my_applications` | Application history |
| `/loans/application/<id>/` | `application_detail` | Application detail |
| `/loans/my-loans/` | `my_loans` | Active loans |
| `/loans/loan/<id>/` | `loan_detail` | Loan detail & repayments |
| `/loans/api/calculate-loan/` | `calculate_loan` | AJAX loan calculator |

---

## 🔒 Security

- Email-based authentication (no usernames)
- Role-Based Access Control (RBAC) on every view
- Customer accounts require admin approval before first login
- Immutable audit log on all actions (user, timestamp, IP, user agent)
- CSRF protection enabled
- Session expiry after 1 hour of inactivity
- `SECRET_KEY`, `DB_PASSWORD` have no fallback defaults — startup fails fast if missing

### Production checklist

```
[ ] Set DEBUG=False
[ ] Set a strong SECRET_KEY
[ ] Set SESSION_COOKIE_SECURE=True
[ ] Set CSRF_COOKIE_SECURE=True
[ ] Configure ALLOWED_HOSTS to your domain
[ ] Run behind Nginx + Gunicorn
[ ] Run python manage.py collectstatic
```

---

## 🗄️ Database

PostgreSQL is the only supported database. SQLite is not used.

```bash
# Create database
psql -U postgres -c "CREATE DATABASE your_db_name;"

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

---

## 🚢 Production

```bash
# Collect static files
python manage.py collectstatic --no-input

# Start with Gunicorn
gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120
```

---

## 🔗 Odoo Integration

Staff-side processing (credit review, KYC verification, loan approval, disbursement, accounting, HR, payroll) is handled in **Odoo 19 Enterprise**. Integration between this portal and Odoo will be done via REST API. Configuration for the Odoo connection will be added to `.env` once the Odoo instance is set up.

---

## 📞 Support

**Alba Capital** — internal system.  
For issues contact the system administrator.