# Loan Management System API Documentation

## Overview

The Loan Management System provides RESTful API endpoints for loan operations, customer management, and administrative functions. All API endpoints require authentication and proper authorization.

## Base URL
```
http://localhost:8000/api/loans/
```

## Authentication

All API requests must include authentication:
```http
Authorization: Token your-api-token
# or
Authorization: Bearer your-jwt-token
```

## Response Format

All API responses follow this standard format:

### Success Response
```json
{
    "success": true,
    "data": {
        // Response data
    },
    "message": "Operation completed successfully",
    "timestamp": "2026-03-03T10:00:00Z"
}
```

### Error Response
```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "Error description",
        "details": {}
    },
    "timestamp": "2026-03-03T10:00:00Z"
}
```

## Endpoints

### 📊 Loan Calculator

Calculate loan details including interest, fees, and monthly payments.

**Endpoint**: `GET /api/calculate-loan/`

**Parameters**:
- `product_id` (int, required): Loan product ID
- `amount` (decimal, required): Loan amount
- `tenure` (int, required): Loan tenure in months

**Example Request**:
```http
GET /api/loans/calculate-loan/?product_id=1&amount=50000&tenure=12
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "principal": 50000.00,
        "interest_rate": 15.0,
        "interest_amount": 7500.00,
        "processing_fee": 1250.00,
        "total_amount": 58750.00,
        "monthly_installment": 4895.83,
        "effective_rate": 16.5
    }
}
```

### 👤 Customer Applications

Get customer's loan applications.

**Endpoint**: `GET /api/customer/applications/`

**Parameters**:
- `status` (string, optional): Filter by status
- `limit` (int, optional): Number of results (default: 20)
- `offset` (int, optional): Pagination offset

**Example Request**:
```http
GET /api/loans/customer/applications/?status=PENDING_APPROVAL&limit=10
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "applications": [
            {
                "id": 123,
                "application_number": "LN-20260303-0001",
                "status": "PENDING_APPROVAL",
                "requested_amount": 50000.00,
                "created_at": "2026-03-03T09:00:00Z",
                "loan_product": {
                    "name": "Personal Loan",
                    "interest_rate": 15.0
                }
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 0
    }
}
```

### 📋 Submit Application

Submit a new loan application.

**Endpoint**: `POST /api/customer/applications/`

**Request Body**:
```json
{
    "loan_product_id": 1,
    "requested_amount": 50000.00,
    "requested_tenure": 12,
    "purpose": "Home renovation",
    "guarantors": [
        {
            "full_name": "John Doe",
            "id_number": "12345678",
            "phone": "+254712345678",
            "email": "john@example.com",
            "relationship": "FRIEND"
        }
    ]
}
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "application_id": 124,
        "application_number": "LN-20260303-0002",
        "status": "SUBMITTED",
        "next_steps": [
            "Upload required documents",
            "Complete KYC verification"
        ]
    }
}
```

### 📄 Upload Document

Upload documents for loan application.

**Endpoint**: `POST /api/customer/applications/{id}/documents/`

**Request**:
- `Content-Type`: `multipart/form-data`
- `document_type`: Document type (ID_CARD, PASSPORT_PHOTO, etc.)
- `description`: Document description
- `file`: Document file

**Example Response**:
```json
{
    "success": true,
    "data": {
        "document_id": 456,
        "upload_status": "SUCCESS",
        "verification_status": "PENDING"
    }
}
```

### 🤖 Face Verification

Submit face photo for verification.

**Endpoint**: `POST /api/customer/face-verification/`

**Request**:
- `Content-Type`: `multipart/form-data`
- `face_photo`: Face photo file

**Example Response**:
```json
{
    "success": true,
    "data": {
        "verification_id": 789,
        "status": "SUBMITTED",
        "processing_time": "1.2 seconds",
        "next_steps": [
            "Wait for staff verification",
            "Check application status"
        ]
    }
}
```

### 📊 Staff Applications

Get all loan applications (staff only).

**Endpoint**: `GET /api/staff/applications/`

**Parameters**:
- `status` (string, optional): Filter by status
- `date_from` (date, optional): Filter by date range
- `date_to` (date, optional): Filter by date range
- `customer_id` (int, optional): Filter by customer

**Example Response**:
```json
{
    "success": true,
    "data": {
        "applications": [
            {
                "id": 123,
                "application_number": "LN-20260303-0001",
                "customer": {
                    "id": 456,
                    "name": "Jane Smith",
                    "email": "jane@example.com"
                },
                "status": "PENDING_APPROVAL",
                "credit_score": {
                    "total_score": 75,
                    "recommendation": "APPROVE"
                },
                "kyc_status": "VERIFIED",
                "created_at": "2026-03-03T09:00:00Z"
            }
        ],
        "summary": {
            "total": 50,
            "pending": 15,
            "approved": 25,
            "rejected": 10
        }
    }
}
```

### ✅ Process Application

Process loan application (staff only).

**Endpoint**: `POST /api/staff/applications/{id}/process/`

**Request Body**:
```json
{
    "action": "approve",
    "approved_amount": 50000.00,
    "internal_notes": "Customer has good credit history",
    "override_credit_score": false
}
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "application_id": 123,
        "new_status": "APPROVED",
        "approved_amount": 50000.00,
        "loan_id": 789,
        "next_steps": [
            "Proceed to disbursement",
            "Notify customer"
        ]
    }
}
```

### 💰 Disburse Loan

Disburse approved loan (staff only).

**Endpoint**: `POST /api/staff/applications/{id}/disburse/`

**Request Body**:
```json
{
    "disbursement_date": "2026-03-03",
    "disbursement_method": "BANK_TRANSFER",
    "reference_number": "BANK123456",
    "notes": "Disbursed via bank transfer"
}
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "loan_id": 789,
        "loan_number": "LN-20260303-0001-0001",
        "disbursement_status": "COMPLETED",
        "accounting_entries": [
            {
                "entry_number": "JE-20260303-0001",
                "amount": 50000.00,
                "account": "Cash/Bank"
            }
        ],
        "customer_notification": "SENT"
    }
}
```

### 🔍 KYC Verification

Get KYC verification queue (staff only).

**Endpoint**: `GET /api/staff/kyc-queue/`

**Example Response**:
```json
{
    "success": true,
    "data": {
        "queue": [
            {
                "customer_id": 456,
                "name": "Jane Smith",
                "face_photo_uploaded": true,
                "documents_uploaded": 5,
                "verification_status": "PENDING",
                "queue_position": 1
            }
        ],
        "summary": {
            "total_pending": 25,
            "verified_today": 15,
            "average_processing_time": "2.5 minutes"
        }
    }
}
```

### ✅ Verify KYC

Complete KYC verification (staff only).

**Endpoint**: `POST /api/staff/kyc/{customer_id}/verify/`

**Request Body**:
```json
{
    "action": "verify_face_recognition",
    "verification_notes": "Face photo matches ID document",
    "kyc_status": "APPROVED"
}
```

**Example Response**:
```json
{
    "success": true,
    "data": {
        "customer_id": 456,
        "kyc_status": "VERIFIED",
        "verification_timestamp": "2026-03-03T10:00:00Z",
        "verified_by": "John Staff"
    }
}
```

### 📊 Portfolio Analytics

Get portfolio analytics (admin only).

**Endpoint**: `GET /api/admin/portfolio-analytics/`

**Parameters**:
- `date_from` (date, optional): Start date for analytics
- `date_to` (date, optional): End date for analytics
- `group_by` (string, optional): Group results (day, week, month)

**Example Response**:
```json
{
    "success": true,
    "data": {
        "summary": {
            "total_portfolio": 5000000.00,
            "active_loans": 150,
            "performing_loans": 135,
            "delinquency_rate": 10.0,
            "yield_rate": 18.5
        },
        "risk_distribution": {
            "low_risk": 100,
            "medium_risk": 40,
            "high_risk": 10
        },
        "monthly_trends": [
            {
                "month": "2026-01",
                "disbursements": 500000.00,
                "repayments": 450000.00,
                "new_applications": 25
            }
        ]
    }
}
```

### 📤 Export Data

Export loan data (admin only).

**Endpoint**: `GET /api/admin/export/`

**Parameters**:
- `format` (string, required): Export format (csv, xlsx, json)
- `date_from` (date, optional): Start date
- `date_to` (date, optional): End date
- `data_type` (string, optional): Type of data (loans, applications, customers)

**Example Response**:
```json
{
    "success": true,
    "data": {
        "export_id": "EXP-20260303-0001",
        "download_url": "/api/admin/download/EXP-20260303-0001/",
        "file_format": "csv",
        "file_size": "2.5 MB",
        "records_count": 1500,
        "expires_at": "2026-03-04T10:00:00Z"
    }
}
```

## Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| AUTH_REQUIRED | Authentication required | 401 |
| PERMISSION_DENIED | Insufficient permissions | 403 |
| NOT_FOUND | Resource not found | 404 |
| VALIDATION_ERROR | Input validation failed | 400 |
| DUPLICATE_APPLICATION | Duplicate application submitted | 409 |
| INSUFFICIENT_CREDIT | Credit score too low | 422 |
| DOCUMENT_REQUIRED | Required documents missing | 422 |
| SYSTEM_ERROR | Internal system error | 500 |
| SERVICE_UNAVAILABLE | Service temporarily unavailable | 503 |

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- **Customer endpoints**: 100 requests per hour
- **Staff endpoints**: 500 requests per hour
- **Admin endpoints**: 1000 requests per hour

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1646330400
```

## Webhooks

Configure webhooks to receive real-time notifications:

### Application Status Update
```json
{
    "event": "application.status_updated",
    "data": {
        "application_id": 123,
        "old_status": "PENDING_APPROVAL",
        "new_status": "APPROVED",
        "timestamp": "2026-03-03T10:00:00Z"
    }
}
```

### Loan Disbursement
```json
{
    "event": "loan.disbursed",
    "data": {
        "loan_id": 789,
        "customer_id": 456,
        "amount": 50000.00,
        "disbursement_date": "2026-03-03",
        "timestamp": "2026-03-03T10:00:00Z"
    }
}
```

## SDK Examples

### Python SDK
```python
from loans_sdk import LoansAPI

# Initialize client
client = LoansAPI(api_key='your-api-key', base_url='http://localhost:8000/api/loans/')

# Calculate loan
result = client.calculate_loan(
    product_id=1,
    amount=50000,
    tenure=12
)

print(f"Monthly payment: {result['monthly_installment']}")

# Submit application
application = client.submit_application(
    loan_product_id=1,
    requested_amount=50000,
    requested_tenure=12,
    purpose="Home renovation"
)

print(f"Application ID: {application['application_id']}")
```

### JavaScript SDK
```javascript
import { LoansAPI } from 'loans-sdk-js';

// Initialize client
const client = new LoansAPI({
    apiKey: 'your-api-key',
    baseUrl: 'http://localhost:8000/api/loans/'
});

// Calculate loan
const result = await client.calculateLoan({
    productId: 1,
    amount: 50000,
    tenure: 12
});

console.log(`Monthly payment: ${result.monthlyInstallment}`);

// Submit application
const application = await client.submitApplication({
    loanProductId: 1,
    requestedAmount: 50000,
    requestedTenure: 12,
    purpose: "Home renovation"
});

console.log(`Application ID: ${application.applicationId}`);
```

## Testing

### Test Environment
- **URL**: `http://localhost:8000/api/loans/test/`
- **Authentication**: Use test credentials
- **Data**: Sandbox database with sample data

### Example Test Request
```bash
curl -X GET "http://localhost:8000/api/loans/test/calculate-loan/?product_id=1&amount=50000&tenure=12" \
     -H "Authorization: Token test-token" \
     -H "Content-Type: application/json"
```

## Support

For API support:
1. Check the error codes section
2. Review the SDK examples
3. Test in the sandbox environment
4. Contact the development team

---

**Note**: This API documentation is version 2.0.0 and corresponds to the current system version. For older versions, please refer to the appropriate documentation.
