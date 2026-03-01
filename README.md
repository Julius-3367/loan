# Alba Capital ERP System

**Professional Enterprise Resource Planning System Built with Django**

---

## 📋 Project Overview

Alba Capital ERP is a comprehensive enterprise resource planning system designed for Alba Capital, a financial services company. The system is built using modern technologies following MVP (Minimum Viable Product) methodology to ensure quality and iterative development.

### Tech Stack

- **Backend**: Django 5.0.2 (Python 3.12)
- **Database**: PostgreSQL / SQLite (configurable)
- **Frontend**: Django Templates + Tailwind CSS 3.x
- **API**: Django REST Framework 3.14
- **Authentication**: Custom email-based authentication with RBAC

---

## ✅ MVP 1: Authentication & Role-Based Access Control (COMPLETE)

### Features Implemented

#### 1. Custom User Model with RBAC ✓
- Email-based authentication (no username required)
- 7 distinct user roles as per SRS requirements:
  - **ADMIN** - System Administrator (full access)
  - **CREDIT_OFFICER** - Loan processing and approval
  - **FINANCE_OFFICER** - Accounting and financial management
  - **HR_OFFICER** - Human resource and payroll
  - **MANAGEMENT** - Executive dashboards and analytics
  - **INVESTOR** - Portfolio viewing (read-only)
  - **CUSTOMER** - Loan applications and self-service

#### 2. Granular Permission System ✓
- Model-level permission checking via `User.has_permission(module, permission_type)`
- Supports permissions: `view`, `create`, `edit`, `delete`, `approve`
- Module-based access control for:
  - Loans, Accounting, HR, Payroll
  - CRM, Customers, Investors
  - Reports, Analytics, Dashboards

#### 3. Authentication System ✓
- Professional login page with Tailwind styling
- Customer registration page with admin approval requirement
- Remember me functionality
- Session management
- Secure password hashing
- **Registration Approval Workflow** - new customers require admin approval

#### 4. Separate Dashboards ✓
- **Staff Dashboard** (`/dashboard/`)
  - System statistics (users, staff, customers)
  - Recent activity feed
  - Quick action links
  - Only accessible to staff roles

- **Customer Portal** (`/customer/dashboard/`)
  - Customer-specific statistics
  - Loan application status (ready for MVP2)
  - Getting started guide
  - Only accessible to customers

#### 5. Audit Logging System ✓
- Immutable audit trail (SRS Section 4.1 requirement)
- Tracks all user actions: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, APPROVE, REJECT
- Stores IP address, user agent, timestamp
- Full Django admin integration

#### 6. Professional UI/UX ✓
- Alba Capital branding colors (Navy #22354e, Orange #ff805d)
- Responsive Tailwind CSS design
- Toast notifications for user feedback
- Mobile-friendly interface
- Clean, modern aesthetic

### Test Results

```
MVP1 TEST SUMMARY
================================================================================
✓ User Model with RBAC
✓ 7 User Roles Configured
✓ Permission Matrix Working
✓ Email-based Authentication
✓ Login/Logout Functionality
✓ Staff Dashboard Access
✓ Customer Portal Access
✓ Role-based Redirects
✓ Audit Logging System
✓ Django Admin Integration

RESULT: 10/10 tests passed (100%)
```

### Database Statistics
- Users: 3 (1 Admin, 1 Credit Officer, 1 Customer)
- Staff Members: 2
- Customers: 1
- All users active

---

## ✅ MVP 2: Loan Management System (COMPLETE)

### Features Implemented

#### 1. Loan Product Management ✓
- **3 Product Categories**:
  - **Salary Advance** - KES 5,000 to 50,000 (1-6 months, 6% flat rate)
  - **Business Expansion Loan** - KES 50,000 to 500,000 (6-24 months, 12% reducing balance)
  - **Asset Financing** - KES 100,000 to 2,000,000 (12-36 months, 15% reducing balance)

- **Configurable Parameters**:
  - Interest calculation methods (Flat Rate / Reducing Balance)
  - Origination fees (percentage + fixed amount)
  - Processing fees
  - Penalty rates with grace periods
  - Min/max amounts and tenure
  - Guarantor requirements
  - Employer verification requirements
  - Minimum credit score thresholds

#### 2. Customer Profile Management ✓
- **KYC Information**:
  - Personal details (ID number, date of birth, address)
  - Employment information (status, employer, income, employment date)
  - Financial information (existing loans, bank details)
  - KYC verification status and history

- **Automated Calculations**:
  - Age calculation from date of birth
  - Total active loans count
  - Debt service ratio for credit assessment

#### 3. Credit Scoring Engine ✓
- **5-Factor Scientific Algorithm** (100 points total):
  - **Income Score** (30 points) - Debt service ratio analysis
    - ≤30% DSR = Excellent (30 pts)
    - 30-40% = Very Good (25 pts)
    - 40-50% = Good (20 pts)
    - 50-60% = Fair (15 pts)
    - >60% = Unaffordable (0 pts)
  
  - **Employment Score** (25 points) - Job stability assessment
    - Base score + duration bonuses + verification bonus
    - 2+ years employment = 8 bonus points
    - Employer verification = 2 bonus points
  
  - **Credit History** (20 points) - Past loan performance
    - 3+ paid loans = Excellent (20 pts)
    - 1-2 paid loans = Good (15 pts)
    - New customer = Fair (10 pts)
    - Any default = Disqualification
  
  - **Existing Obligations** (15 points) - Current debt load
    - 0% of income = Excellent (15 pts)
    - Linear reduction to >60% = 0 pts
  
  - **Age Score** (10 points) - Age appropriateness
    - Prime age 30-55 = 7 pts
    - Account maturity bonuses

- **Automated Recommendations**:
  - **75+ points** → APPROVED
  - **50-74 points** → CONDITIONAL (manual review)
  - **<50 points** → REJECTED

- **Manual Override Capability** with justification audit trail

#### 4. Loan Application Workflow ✓
- **11-Stage Application Process**:
  1. **DRAFT** - Customer creating application
  2. **SUBMITTED** - Initial submission
  3. **UNDER_REVIEW** - Preliminary document review
  4. **CREDIT_ANALYSIS** - Automated credit scoring
  5. **PENDING_APPROVAL** - Awaiting credit officer decision
  6. **APPROVED** - Approved with terms
  7. **EMPLOYER_VERIFICATION** - Third-party verification
  8. **GUARANTOR_CONFIRMATION** - Guarantor acceptance
  9. **DISBURSED** - Funds transferred (Loan created)
  10. **REJECTED** - Application declined
  11. **CANCELLED** - Cancelled by customer

- **Workflow Validation**:
  - State transition rules enforced
  - Required documents per stage
  - Guarantor requirements validation
  - Auto-generated application numbers (LA-YYYYMMDD-XXXX)

#### 5. Document Management ✓
- **Supported Document Types**:
  - National ID / Passport
  - Payslips (3 months)
  - Bank statements (6 months)
  - Employment letter
  - Business registration (for business loans)
  - KRA PIN certificate
  - Guarantor ID

- **Document Validation**:
  - File upload with validation
  - Document type categorization
  - Verification status tracking
  - Staff approval workflow

#### 6. Guarantor Management ✓
- **Guarantor Verification System**:
  - Guarantor information capture
  - Unique confirmation codes
  - Verification status tracking (PENDING/VERIFIED/DECLINED/WAIVED)
  - Guarantor acceptance workflow

#### 7. Loan Disbursement & Tracking ✓
- **Loan Creation from Approved Applications**:
  - Auto-generated loan numbers (LN-YYYYMMDD-XXXX)
  - Disbursement method tracking (Bank Transfer/M-Pesa/Cheque)
  - Reference number recording
  - Automated accounting entries (ready for MVP3 integration)

- **Active Loan Management**:
  - Principal and total amount tracking
  - Outstanding balance calculation
  - Payment progress percentage
  - Next payment date tracking
  - Maturity date calculation
  - Overdue status detection

#### 8. Repayment Tracking ✓
- **Payment Recording System**:
  - Auto-generated receipt numbers (RCP-YYYYMMDD-XXXX)
  - Payment allocation (principal + interest + penalties)
  - Payment method tracking
  - Payment date and reference recording

- **Repayment Calculations**:
  - Automatic payment allocation
  - Outstanding balance updates
  - Payment progress tracking
  - Repayment history

#### 9. Professional Templates ✓
- **Customer Templates (5 templates)**:
  - Loan dashboard with statistics
  - Customer profile with KYC status
  - Loan application form with real-time calculator
  - Applications list with status tracking
  - Active loans list with progress bars

- **Staff Templates (3 templates)**:
  - Staff loan dashboard with portfolio metrics
  - Application processing interface
  - Shared application/loan detail views

- **Real-time Features**:
  - JavaScript loan calculator (AJAX)
  - Live payment breakdown updates
  - Responsive Tailwind CSS design
  - Alba Capital branding throughout

#### 10. Django Admin Integration ✓
- **9 Models Registered** with professional interfaces:
  - LoanProduct, Customer, CreditScore
  - LoanApplication, Loan, LoanRepayment
  - EmployerVerification, GuarantorVerification, LoanDocument

- **Admin Features**:
  - Color-coded status badges (11 colors)
  - Collapsible fieldsets for organization
  - Linked relationships (clickable FKs)
  - Read-only timestamps and auto-fields
  - Searchable by multiple criteria
  - Custom list displays with calculated fields

#### 11. API Endpoints ✓
- **Loan Calculator API** (`/loans/api/calculate-loan/`):
  - Real-time loan calculation
  - Returns principal, interest, fees, total, installment
  - Supports both interest calculation methods
  - AJAX-ready JSON responses

### Test Results

```
MVP2 TEST SUMMARY
================================================================================
✓ Loan Products: 3 products created
✓ Fee Calculation: Working correctly
✓ Interest Calculation: Both methods working
✓ Database Statistics: All models accessible
✓ Model Methods: All __str__ methods working
✓ Admin Configuration: 5 main models registered
✓ URL Configuration: 11 routes configured
✓ Forms: 8 forms loaded successfully

RESULT: 18/18 core tests passed (100%)
```

### MVP2 Database Statistics
- **Loan Products**: 3 active products
- **Customers**: Ready for customer onboarding
- **Applications**: 11-stage workflow operational
- **Loans**: Disbursement system ready
- **Repayments**: Payment tracking configured
- **Database Indexes**: 27 indexes for performance optimization

### Technical Implementation
- **Models**: 9 comprehensive models (1,141 lines)
- **Credit Scoring**: 530+ lines of calculation logic
- **Forms**: 8 validated forms (438 lines)
- **Views**: 15 views (10 customer, 5 staff) - 593 lines
- **Templates**: 8 templates with 1,800+ lines of HTML/JavaScript
- **Admin**: Professional interfaces for all models
- **URL Routing**: Namespaced 'loans' app with 14 patterns
- **API**: RESTful calculator endpoint

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/Julius-3367/loan_system.git
cd loan_system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

Key settings in `.env`:
- `SECRET_KEY` - Already generated
- `DEBUG=True` for development
- `DB_ENGINE=sqlite` or `postgresql`
- Database credentials (if using PostgreSQL)

### 3. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser
python create_superuser.py
# Or manually: python manage.py createsuperuser
```

### 4. Run Development Server

```bash
python manage.py runserver 0.0.0.0:3000
```

Access the system:
- **Landing Page**: http://localhost:3000/ (Professional homepage)
- **Login**: http://localhost:3000/login/
- **Register**: http://localhost:3000/register/
- **Admin Panel**: http://localhost:3000/admin/

### 5. Test the System

```bash
# Run comprehensive MVP1 test suite
python test_mvp1.py

# Run comprehensive MVP2 test suite
python test_mvp2.py
```

### 6. Access the System

**Public Website**:
- Professional landing page at http://localhost:3000/
- Features: Services showcase, loan products comparison, how it works, testimonials
- Call-to-action buttons for sign up and login
- Responsive design with Alba Capital branding
- Auto-redirects authenticated users to appropriate dashboard
- **New registrations require admin approval** - see [User Approval Workflow](USER_APPROVAL_WORKFLOW.md)

**User Registration & Approval**:
- New customers can register at http://localhost:3000/register/
- All new registrations are **pending approval** (is_active=False)
- Users cannot login until an administrator approves their account
- Admins manage approvals from the Django Admin panel at `/admin/core/user/`
- See [USER_APPROVAL_WORKFLOW.md](USER_APPROVAL_WORKFLOW.md) for complete documentation

**Customer Portal (Loan Management)**:
- Login at http://localhost:3000/login/
- Navigate to "My Loans" from dashboard
- Complete profile at `/loans/profile/`
- Apply for loan at `/loans/apply/`
- Track applications at `/loans/applications/`
- View active loans at `/loans/my_loans/`

**Staff Portal (Loan Processing)**:
- Login as staff (admin or credit officer)
- Access loan management at `/loans/staff/`
- Process applications at `/loans/staff/applications/`
- View portfolio statistics
- Approve/reject applications

**Django Admin (Staff Creation)**:
- Access at http://localhost:3000/admin/
- Create staff users and assign roles
- Manage loan products
- Configure credit scoring parameters
- View all applications and loans

---

## 🔐 Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@albacapital.com | admin123 |
| Credit Officer | credit@albacapital.com | credit123 |
| Customer | customer@example.com | customer123 |

---

## 💼 Sample Loan Products (MVP2)

| Product | Amount Range | Interest Rate | Tenure | Requirements |
|---------|-------------|---------------|--------|--------------|
| **Salary Advance** | KES 5,000 - 50,000 | 6% Flat | 1-6 months | Credit Score 50+, No Guarantor |
| **Business Loan** | KES 50,000 - 500,000 | 12% Reducing | 6-24 months | Credit Score 65+, Guarantor Required, Employer Verification |
| **Asset Financing** | KES 100,000 - 2M | 15% Reducing | 12-36 months | Credit Score 70+, Guarantor Required, Employer Verification |

---

## 🔐 Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@albacapital.com | admin123 |
| Credit Officer | credit@albacapital.com | credit123 |
| Customer | customer@example.com | customer123 |

---

## 📊 SRS Compliance

### Implemented (MVP1 + MVP2)

**MVP1 - Authentication & RBAC:**
✅ **Section 2.2**: User Classes and Characteristics - All 7 roles implemented  
✅ **Section 4.1 (Security)**: Role-Based Access Control  
✅ **Section 4.1 (Security)**: Email-based authentication  
✅ **Section 4.1 (Security)**: Immutable audit trail  
✅ **Section 4.1 (Security)**: Session management  
✅ **Custom User Model**: Email as username field  
✅ **Permission Matrix**: Granular module-level permissions  
✅ **Admin Integration**: Full Django admin support  
✅ **Professional UI**: Tailwind CSS with Alba Capital branding  

**MVP2 - Loan Management System:**
✅ **Section 3.1.1**: Loan Product Configuration - 3 categories with full parameterization  
✅ **Section 3.1.2**: Loan Application System - 11-stage workflow  
✅ **Section 3.1.3**: Credit Scoring Engine - 5-factor algorithm (100 points)  
✅ **Section 3.1.4**: Document Management - 7 document types with validation  
✅ **Section 3.1.5**: Guarantor Verification - Confirmation codes and workflow  
✅ **Section 3.1.6**: Employer Verification - Third-party validation process  
✅ **Section 3.1.7**: Loan Disbursement - Multiple methods with tracking  
✅ **Section 3.1.8**: Repayment Tracking - Payment allocation and history  
✅ **Customer Profile**: KYC management with verification workflow  
✅ **Professional Templates**: 8 responsive templates with real-time features  
✅ **API Endpoints**: RESTful loan calculator  
✅ **Database Performance**: 27 indexes for query optimization  

### Roadmap (Next MVPs)

#### MVP 3: Financial Management & Accounting (SRS Section 3.2) - **NEXT**
- Chart of Accounts with 5 account types
- General Ledger with double-entry bookkeeping
- Journal entries (manual and automated from loans)
- Bank reconciliation workflow
- Financial reports (P&L, Balance Sheet, Cash Flow, Trial Balance)
- Period closing procedures

#### MVP 4: Customer Portal Enhanced (SRS Section 3.5)
- Online loan repayment interface
- Statement downloads (PDF generation)
- Real-time notifications (email + SMS)
- Payment reminders
- Document library

#### MVP 5: Payment Integration (SRS Section 3.4)
- M-Pesa integration
- Paybill services
- Bank feeds
- Payment reconciliation

#### MVP 6: Investor Reporting (SRS Section 3.6)
- Investment account management
- Compound interest calculations
- Withdrawal processing
- Investor statements

#### MVP 7: HR & Payroll (SRS Section 3.7)
- Employee records
- Payroll processing
- Leave management
- Statutory deductions

---

## 🏗️ System Architecture

### Django Project Structure

```
loan_system/
├── config/                 # Project configuration
│   ├── settings.py        # Django settings
│   ├── urls.py            # URL routing
│   ├── wsgi.py            # WSGI application
│   └── asgi.py            # ASGI application
├── core/                   # MVP1: Authentication & RBAC
│   ├── models.py          # User & AuditLog models
│   ├── views.py           # Authentication views
│   ├── forms.py           # Login & registration forms
│   ├── admin.py           # Django admin config
│   └── urls.py            # Core app URLs
├── templates/              # HTML templates
│   ├── base.html          # Base template with Tailwind
│   └── core/              # Authentication templates
│       ├── login.html
│       ├── register.html
│       ├── dashboard.html
│       └── customer_dashboard.html
├── static/                 # Static files (CSS, JS, images)
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── test_mvp1.py           # MVP1 test suite
└── README.md              # This file
```

### Database Schema (MVP1)

#### users Table
- `id` - Primary key
- `email` - Unique, used for authentication
- `first_name`, `last_name` - User name
- `phone` - Contact number
- `role` - User role (7 choices)
- `is_active`, `is_staff`, `is_superuser` - Status flags
- `password` - Hashed password
- `date_joined`, `last_login` - Timestamps

#### audit_logs Table
- `id` - Primary key
- `user_id` - Foreign key to users
- `action` - Action type (CREATE, UPDATE, DELETE, LOGIN, etc.)
- `model_name` - Model affected
- `object_id` - ID of affected object
- `description` - Human-readable description
- `ip_address`, `user_agent` - Request metadata
- `timestamp` - When action occurred

---

## 🔧 Configuration

### Database Configuration

**SQLite (Default - Development)**
```python
# In .env
DB_ENGINE=sqlite
```

**PostgreSQL (Production)**
```python
# In .env
DB_ENGINE=postgresql
DB_NAME=alba_capital_erp
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
```

### Email Configuration

```python
# Development (console backend)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Production (SMTP)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password
```

---

## 🧪 Testing

### Run Test Suite

```bash
# Activate virtual environment
source venv/bin/activate

# Run MVP1 comprehensive tests
python test_mvp1.py
```

### Manual Testing

1. **Register new customer**: http://localhost:3000/register/
2. **Login as customer**: Use registered credentials
3. **Verify customer dashboard**: Should see customer portal
4. **Logout and login as admin**: admin@albacapital.com / admin123
5. **Verify staff dashboard**: Should see system statistics
6. **Access Django admin**: http://localhost:3000/admin/
7. **Check audit logs**: Verify all actions logged

---

## 📚 API Documentation

While MVP1 focuses on web interface, the system is built with Django REST Framework for future API development.

### Future API Endpoints (MVP 2+)

```
/api/loans/               # Loan management
/api/applications/        # Loan applications
/api/customers/           # Customer management  
/api/accounting/          # Financial transactions
/api/investors/           # Investor accounts
/api/reports/             # Report generation
```

---

## 🔒 Security Features

### Implemented

- ✅ Email-based authentication
- ✅ Password hashing (Django PBKDF2)
- ✅ Session management
- ✅ CSRF protection
- ✅ Role-based access control (RBAC)
- ✅ Granular permissions
- ✅ Audit logging
- ✅ Secure password validators

### Production Recommendations

- Enable HTTPS (set `SESSION_COOKIE_SECURE=True`)
- Set `DEBUG=False`
- Configure proper `ALLOWED_HOSTS`
- Use strong `SECRET_KEY`
- Enable Multi-Factor Authentication (MFA) - planned for MVP8
- Set up SSL certificate
- Configure firewall rules
- Implement rate limiting
- Enable database backups

---

## 🚀 Deployment

### Production Checklist

- [ ] Set `DEBUG=False` in `.env`
- [ ] Configure PostgreSQL database
- [ ] Set strong `SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Enable HTTPS
- [ ] Set up Gunicorn/uWSGI
- [ ] Configure Nginx reverse proxy
- [ ] Set up static file serving
- [ ] Configure email backend
- [ ] Enable database backups
- [ ] Set up monitoring (Sentry)
- [ ] Configure log aggregation

### Sample Production Command

```bash
# Using Gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 👥 User Roles & Permissions

### Permission Matrix

| Module | Admin | Credit | Finance | HR | Management | Investor | Customer |
|--------|-------|--------|---------|----|-----------|---------|---------| 
| Loans | ✓ All | ✓ CRUD + Approve | ✓ View | ✗ | ✓ View | ✗ | ✗ |
| Accounting | ✓ All | ✗ | ✓ CRUD + Approve | ✗ | ✓ View | ✗ | ✗ |
| HR/Payroll | ✓ All | ✗ | ✗ | ✓ CRUD + Approve | ✓ View | ✗ | ✗ |
| Customers | ✓ All | ✓ CRUD | ✗ | ✗ | ✓ View | ✗ | ✗ |
| CRM | ✓ All | ✓ CRUD | ✗ | ✗ | ✓ View | ✗ | ✗ |
| Investors | ✓ All | ✗ | ✓ CRUD | ✗ | ✓ View | ✓ View | ✗ |
| Reports | ✓ All | ✓ View | ✓ View | ✓ View | ✓ View | ✓ Own | ✗ |
| Customer Portal | ✓ All | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ CRUD |
| Dashboards | ✓ All | ✓ Own | ✓ Own | ✓ Own | ✓ All | ✓ Own | ✓ Own |

**Legend**: ✓ = Has permission, ✗ = No permission, CRUD = Create/Read/Update/Delete

---

## 📝 Contributing

This is a client project for Alba Capital. Development follows strict MVP methodology:

1. Complete one module 100% before moving forward
2. All features must pass comprehensive testing
3. Code must follow PEP 8 style guidelines
4. All commits must reference SRS requirements
5. Database migrations must be reversible

---

## 📄 License

Proprietary - Alba Capital © 2026

---

## 📞 Support

For technical support or inquiries:

- **Client**: Alba Capital
- **Developer**: Softlink Options Ltd
- **Project Repository**: https://github.com/Julius-3367/loan_system

---

## 🎯 Current Status

**MVP 1: COMPLETE ✅** (Authentication & RBAC)  
**Next Phase: MVP 2** (Loan Management System - SRS Section 3.1)

---

*Built with ❤️ using Django, PostgreSQL, and Tailwind CSS*
