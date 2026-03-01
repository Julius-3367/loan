# User Registration Approval Workflow

## Overview

The Alba Capital ERP system now implements a user registration approval workflow where new customer registrations require administrator approval before users can access the system. This ensures proper vetting and control over who can access the loan management system.

## How It Works

### 1. User Registration
When a new customer registers through the public website:
- User fills out the registration form with email, name, phone, and password
- Account is created with `is_active=False` (inactive status)
- User sees message: *"Registration successful! Your account is pending approval. You will be notified when an admin approves your account."*
- User is redirected to the login page

### 2. Login Attempt (Before Approval)
If an unapproved user tries to login:
- System checks if the user account exists but is inactive
- User sees error message: *"Your account is pending approval. Please wait for an administrator to approve your account before you can login."*
- User cannot access the system

### 3. Admin Approval Process
Administrators can manage pending registrations from the Django Admin panel:

#### Viewing Pending Registrations
1. Login to Django Admin at `/admin/`
2. Navigate to **Users** section
3. Filter by **Active** status (select "No" to see pending registrations)
4. View user details: email, name, phone, registration date

#### Approving Users
**Method 1: Bulk Action**
1. Select one or more pending users (checkbox)
2. From "Action" dropdown, choose **"Approve selected users"**
3. Click "Go"
4. Success message: *"X user(s) have been approved and can now login."*

**Method 2: Individual Approval**
1. Click on a user's email to open their detail page
2. Check the **Active** checkbox in the Permissions section
3. Click "Save"
4. User is now approved and can login

#### Rejecting/Deactivating Users
**Method 1: Bulk Action**
1. Select one or more users (checkbox)
2. From "Action" dropdown, choose **"Reject/Deactivate selected users"**
3. Click "Go"
4. Warning message: *"X user(s) have been deactivated and cannot login."*

**Method 2: Individual Rejection**
1. Click on a user's email to open their detail page
2. Uncheck the **Active** checkbox in the Permissions section
3. Click "Save"
4. User account is now deactivated

### 4. Post-Approval Login
After admin approval:
- User's `is_active` status changes to `True`
- User can now successfully login with their credentials
- User sees welcome message: *"Welcome back, [Full Name]!"*
- User is redirected to their customer dashboard

## Admin Interface Features

### List Display
The User admin list shows:
- Email address
- Full name
- Role (Customer, Staff, Admin, etc.)
- **Active status** (✓ or ✗)
- Staff status
- Date joined

### Filters Available
- **Role**: Filter by user role (Admin, Credit Officer, Customer, etc.)
- **Active**: Filter by approval status (Yes/No)
- **Staff Status**: Filter by staff designation
- **Date Joined**: Filter by registration date

### Search Functionality
Search users by:
- Email address
- First name
- Last name
- Phone number

## Important Notes

### Staff User Creation
- **Staff users** (Admin, Credit Officer, Finance Officer, HR Officer, Management, Investor) are **NOT** affected by this workflow
- Staff users are created directly by administrators in the Django Admin panel
- Staff users are automatically active (`is_active=True`) when created
- They can login immediately without approval

### Customer Registration Only
- The approval workflow **only applies to customer registrations** from the public website
- Customers register at: `http://localhost:9000/register/`
- All customer registrations start as inactive and require approval

### Security Benefits
1. **Prevents Spam**: Stops automated bot registrations
2. **Identity Verification**: Admin can verify customer information before approval
3. **Access Control**: Complete control over who can access the loan system
4. **Audit Trail**: All registrations are logged with timestamps

## Testing

The approval workflow has been comprehensively tested with 6 test cases:

1. ✅ **New registration creates inactive user** - Verifies customers start as inactive
2. ✅ **Inactive user cannot login** - Verifies unapproved users see appropriate message
3. ✅ **Approved user can login** - Verifies activation enables login
4. ✅ **Admin-created users are active** - Verifies staff bypass approval workflow
5. ✅ **Complete workflow test** - Tests full cycle: register → blocked → approve → login
6. ✅ **Rejected user remains inactive** - Verifies deactivation prevents login

Run tests with:
```bash
python3 manage.py test tests.test_user_approval_workflow
```

## Access Points

### For Customers
- **Landing Page**: http://localhost:9000/
- **Registration**: http://localhost:9000/register/
- **Login**: http://localhost:9000/login/

### For Administrators
- **Admin Panel**: http://localhost:9000/admin/
- **User Management**: http://localhost:9000/admin/core/user/

## Files Modified

1. **core/views.py** - RegisterView sets `is_active=False`, LoginView checks inactive users
2. **core/admin.py** - Added `approve_users` and `reject_users` admin actions
3. **tests/test_user_approval_workflow.py** - Comprehensive test suite (6 tests)

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Customer Registration                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Account Created  │
            │  is_active=False  │
            └─────────┬─────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Cannot Login     │
            │  (Pending Msg)    │
            └─────────┬─────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Admin Reviews    │
            │  in Admin Panel   │
            └─────────┬─────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
  ┌─────────────┐          ┌─────────────┐
  │  APPROVE    │          │  REJECT     │
  │ is_active=  │          │ is_active=  │
  │    True     │          │   False     │
  └──────┬──────┘          └──────┬──────┘
         │                         │
         ▼                         ▼
  ┌─────────────┐          ┌─────────────┐
  │ Can Login   │          │ Cannot      │
  │ Successfully│          │ Login       │
  └─────────────┘          └─────────────┘
```

## Future Enhancements (Optional)

Potential improvements that could be added:
1. Email notifications when account is approved/rejected
2. Admin dashboard widget showing pending approval count
3. Approval reason/notes field for audit purposes
4. Automatic approval after identity verification
5. Time-limited approval requests (auto-expire after X days)
6. Approval queue with priority sorting

---

**Last Updated**: January 2025  
**Version**: 1.0  
**Feature Status**: ✅ Implemented and Tested
