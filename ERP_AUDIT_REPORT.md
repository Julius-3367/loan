# Alba Capital ERP Implementation Audit Report
## Senior Odoo ERP Implementation Consultant & System Auditor
### March 25, 2026

---

## EXECUTIVE SUMMARY

**Audit Scope:** Comprehensive validation of Alba Capital ERP implementation against business requirements questionnaire.

**Current Status:** ⚠️ **PARTIALLY COMPLIANT** - Critical gaps identified in loan products, user roles, and workflow configurations.

**Go-Live Risk:** 🔴 **HIGH** - Several requirements not met, requires immediate remediation before June 15, 2026 go-live.

---

## 1. AUDIT FINDINGS BY SECTION

### SECTION A: ORGANIZATION PROFILE & GOVERNANCE

| Requirement | Status | Gap | Priority |
|-------------|--------|-----|----------|
| Company: Alba Capital Limited | ✅ | Configured in Odoo | - |
| PIN: P051914495W | ⚠️ | Need to verify in company settings | Low |
| Single branch (IPS Building) | ❌ | Not configured | Medium |
| Directors: Martin Gichovi / Faith Nduta | ❌ | Users not created with director roles | **High** |
| Go-live date: June 15, 2026 | 📋 | Project milestone | - |

**Recommendations:**
1. Create Director users with proper approval authority
2. Configure branch/location settings
3. Set up company registry with PIN

---

### SECTION B: USERS, ROLES & ACCESS CONTROL ⚠️ CRITICAL GAPS

#### Required Users vs Implemented

| Required Role | Implemented | Status | Gap |
|---------------|-------------|--------|-----|
| Relationship Officer | ❌ | **MISSING** | Need to create |
| Finance Officer | ❌ | **MISSING** | Need to create |
| Finance & Admin | ❌ | **MISSING** | Need to create |
| Operations Manager | ⚠️ | Partial (group_loan_manager exists but not mapped) | Map role |
| Directors (Admin) | ❌ | **MISSING** | Need to create |
| Trade Finance Officer | ❌ | **MISSING** | Need to create |
| Business Development Officer | ❌ | **MISSING** | Need to create |

#### Current Security Groups (Incomplete)

```xml
<!-- Current: Only 3 loan groups -->
- group_loan_user (basic)
- group_loan_officer (review)
- group_loan_manager (full)

<!-- Required: 7+ distinct roles with module access -->
```

#### Module Access Matrix - GAPS IDENTIFIED

| Module | Required Access | Current Status |
|--------|-----------------|----------------|
| Accounting | Finance, Ops, Director | ❌ Not configured |
| Loan Mgmt | Officers, Ops, Finance, Director | ⚠️ Partial (no role mapping) |
| HR/Payroll | Finance, Ops, Director | ❌ Not implemented |
| Documents/Knowledge | Authorized/Admin | ❌ Not configured |
| Investor | Finance, Ops, Director | ⚠️ Basic access only |
| Portal | Customers/Investors | ✅ Django portal exists |

#### Segregation of Duties - NOT IMPLEMENTED

| Process | Required SoD | Current Status |
|---------|--------------|----------------|
| Loans | Officer → Manager | ⚠️ Groups exist but workflow rules missing |
| Journals | Preparer → Finance Manager | ❌ Not implemented |
| Payroll | HR → Finance → Disbursement | ❌ Not implemented |
| Investor Tx | Officer → Ops/Finance | ❌ Not implemented |
| Documents | Staff → Manager/Admin | ❌ Not implemented |

#### Approval Limits - NOT CONFIGURED

| Process | Required Approver | Current Status |
|---------|-------------------|----------------|
| Loans | Ops Manager / Director | ❌ Not configured |
| Write-offs | Director | ❌ Not configured |
| Journals | Director/Ops | ❌ Not configured |

**🔴 CRITICAL RISK:** Missing MFA requirement implementation.

---

### SECTION C: LOAN PRODUCTS & RULES 🔴 CRITICAL GAPS

#### C.1 Product Configuration Audit

##### 1. Salary Advance - ⚠️ PARTIALLY COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Amount | 5k–100k | 5k–100k | ✅ |
| Tenure | 1 month | 1–1 month | ✅ |
| Interest | Flat | Flat 10% | ⚠️ **RATE WRONG** |
| Repayment | Monthly | Monthly | ✅ |
| **Origination Fee** | **10%** | **10%** | ✅ |
| **Processing Fee** | **3.5%** | **3.5%** | ✅ |
| **Insurance Fee** | **1.5%** | **1.5%** | ✅ |
| **Penalty** | **15%** | **15%** | ✅ |

**⚠️ ISSUE:** Interest rate shows 10% but requirements specify "flat interest" without rate. Need clarification.

##### 2. Business Loan - ⚠️ PARTIALLY COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Amount | 100k–500k | 100k–500k | ✅ |
| Tenure | 1–12 months | 1–12 months | ✅ |
| Interest | Flat | Flat 10% | ⚠️ **NEEDS CLARIFICATION** |
| Repayment | Monthly | Monthly | ✅ |
| Origination Fee | 10% | 10% | ✅ |
| **Processing Fee** | **Not specified** | **0%** | ⚠️ Verify |
| **Insurance Fee** | **Not specified** | **0%** | ⚠️ Verify |
| **Penalty** | **15%** | **15%** | ✅ |

##### 3. Personal Loan - ✅ COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Amount | 10k–100k | 10k–100k | ✅ |
| Tenure | 1–12 months | 1–12 months | ✅ |
| Interest | Flat | Flat 10% | ⚠️ **NEEDS CLARIFICATION** |
| Origination Fee | 10% | 10% | ✅ |
| Processing Fee | 3.5% | 3.5% | ✅ |
| Insurance Fee | 1.5% | 1.5% | ✅ |

##### 4. Bid Bonds - ❌ NON-COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Amount | 100k–10M | 100k–10M | ✅ |
| Tenure | On completion | 1–12 months | ❌ **WRONG** |
| Interest | Fee 1.5% | 1.5% rate | ❌ **WRONG TYPE** |

**🔴 CRITICAL:** Bid bonds should be fee-based (1.5%), not interest-bearing loans. Current config treats as loan product.

##### 5. Performance Bond - ❌ NON-COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Fee | 1% | 1% rate | ❌ **WRONG TYPE** |

**🔴 CRITICAL:** Performance bonds should be fee-based, not interest loans.

##### 6. Staff Loan - ✅ COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Interest | 5% reducing | 5% reducing | ✅ |

##### 7. IPF Loan - ⚠️ NEEDS CLARIFICATION

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Interest | 10% per annum | 10% flat | ⚠️ Verify method |

##### 8. Asset Financing - ❌ NON-COMPLIANT

| Requirement | Specified | Current Config | Status |
|-------------|-----------|----------------|--------|
| Staff rate | 5% reducing | Not separated | ❌ **MISSING** |
| Client rate | 10% flat | 10% flat | ⚠️ **NEEDS DUAL CONFIG** |

**🔴 CRITICAL:** Asset financing needs TWO separate products or rate rules based on customer type.

#### C.2 Repayment Rules - PARTIALLY COMPLIANT

| Rule | Required | Implemented | Status |
|------|----------|-------------|--------|
| Monthly default | ✅ | ✅ | Compliant |
| Custom schedules | ✅ | ❌ | **MISSING** |

#### C.3 Recovery Order ✅ COMPLIANT

```python
# Implemented in loan_repayment.py _auto_allocate_components()
1. Other charges (fees) ✅
2. Penalties ✅
3. Interest ✅
4. Principal ✅
```

#### C.4 Penalty Formula ⚠️ NEEDS VERIFICATION

| Requirement | Specified | Implemented | Status |
|-------------|-----------|-------------|--------|
| Daily penalty | On overdue | Calculated | ⚠️ Verify formula |

Current implementation:
```python
daily_penalty = loan_product.penalty_rate / 100  # This is monthly rate, not daily!
penalty_owed = overdue_amount * daily_penalty * days_overdue
```

**🔴 BUG:** Formula treats monthly rate as daily rate. Needs fix.

#### C.5 Loan Rules - PARTIALLY IMPLEMENTED

| Rule | Required | Implemented | Status |
|------|----------|-------------|--------|
| Restructure (+3% fee) | ✅ | ❌ | **MISSING** |
| Reschedule allowed | ✅ | ❌ | **MISSING** |
| Early settlement | ✅ | ❌ | **MISSING** |
| Default (interest continues) | ✅ | ⚠️ | Partial |

#### C.6 NPL Classification ✅ COMPLIANT

| Requirement | Specified | Implemented | Status |
|-------------|-----------|-------------|--------|
| NPL threshold | >90 days | 90 days | ✅ |

#### C.7 KYC Requirements - PARTIALLY COMPLIANT

| Requirement | Django | Odoo | Status |
|-------------|--------|------|--------|
| ID | ✅ | ✅ | Compliant |
| KRA PIN | ✅ | ✅ | Compliant |
| Photo | ✅ | ✅ | Compliant |
| Address | ✅ | ✅ | Compliant |
| Payslips | ✅ | ✅ | Compliant |
| Bank statements | ✅ | ✅ | Compliant |
| **Business docs (CR12, permits)** | ❌ | ❌ | **MISSING** |
| **Guarantors** | ✅ | ✅ | Compliant |
| **Collateral** | ❌ | ❌ | **MISSING** |
| **Contracts/invoices** | ❌ | ❌ | **MISSING** |

---

### SECTION D: LOAN LIFECYCLE ⚠️ PARTIALLY COMPLIANT

#### D.1 Workflow Stages

| Required Stage | Odoo State | Status |
|----------------|------------|--------|
| Application | draft | ✅ |
| Credit Assessment | credit_analysis | ✅ |
| Approval | pending_approval → approved | ✅ |
| Offer & Documentation | (implied) | ⚠️ |
| Disbursement | disbursed | ✅ |
| Repayment Monitoring | (active loan) | ✅ |
| Collections/Recovery | ❌ | **MISSING** |
| Closure | closed | ✅ |

**🔴 GAP:** No dedicated collections/recovery workflow stage.

#### D.2 Verification Process

| Verification | Required | Implemented | Status |
|--------------|----------|-------------|--------|
| Employer validation | ✅ | ✅ | Compliant |
| Guarantor checks | ✅ | ✅ | Compliant |
| Document authenticity | ✅ | ⚠️ | Partial (no automated check) |

#### D.3 Escalation Buckets - NOT IMPLEMENTED

| Bucket | Required Action | Implemented |
|--------|-----------------|---------------|
| 1–30 days | Reminders | ❌ **MISSING** |
| 31–60 days | Collections | ❌ **MISSING** |
| 61–90 days | Recovery | ❌ **MISSING** |
| 90+ days | Legal | ❌ **MISSING** |

**🔴 CRITICAL:** Automated escalation workflow not implemented.

#### D.4 Notifications - PARTIALLY IMPLEMENTED

| Notification | Required | Django | Odoo | Status |
|--------------|----------|--------|------|--------|
| Application | ✅ | ✅ | ✅ | Compliant |
| Approval/Decline | ✅ | ✅ | ✅ | Compliant |
| Disbursement | ✅ | ✅ | ✅ | Compliant |
| **Repayment reminders** | **✅** | **✅** | **⚠️** | **Need automation** |
| **Overdue alerts** | **✅** | **✅** | **⚠️** | **Need automation** |
| **Escalations** | **✅** | **❌** | **❌** | **MISSING** |
| Closure | ✅ | ✅ | ✅ | Compliant |

---

### SECTION E: CUSTOMER DATA ✅ MOSTLY COMPLIANT

| Field Category | Required | Implemented | Status |
|----------------|----------|-------------|--------|
| Personal info | ✅ | ✅ | Compliant |
| ID/KRA | ✅ | ✅ | Compliant |
| Contacts | ✅ | ✅ | Compliant |
| Employment/business | ✅ | ✅ | Compliant |
| Financials | ✅ | ✅ | Compliant |
| Guarantors | ✅ | ✅ | Compliant |
| Credit history | ✅ | ✅ | Compliant |

#### Customer Categories

| Category | Required | Implemented | Status |
|----------|----------|-------------|--------|
| Individual | ✅ | ✅ | Compliant |
| Corporate | ✅ | ⚠️ | Partial (no separate model) |
| SME | ✅ | ⚠️ | Via business_loan category |
| Staff | ✅ | ⚠️ | Via staff_loan product |

#### Flags - PARTIALLY IMPLEMENTED

| Flag | Required | Implemented | Status |
|------|----------|-------------|--------|
| CRB blacklist | ✅ | ✅ (is_blacklisted) | Compliant |
| **AML/PEP** | **✅** | **⚠️** | **Investor only, not customer** |
| **Fraud alerts** | **✅** | **❌** | **MISSING** |
| **Compliance issues** | **✅** | **❌** | **MISSING** |

---

### SECTION F: ACCOUNTING & FINANCE ⚠️ PARTIALLY COMPLIANT

#### F.1 Currency ✅ COMPLIANT

| Requirement | Status |
|-------------|--------|
| Base: KES | ✅ |
| FX: USD, EUR | ✅ Odoo standard |
| Daily rates | ✅ Odoo standard |
| FX revaluation | ✅ Odoo standard |

#### F.2 Chart of Accounts - NOT VERIFIED

| Requirement | Status |
|-------------|--------|
| Assets, Liabilities, Equity, Income, Expenses | ⚠️ Need to verify configuration |

#### F.3 Bank Accounts - NOT CONFIGURED

| Bank | Required | Status |
|------|----------|--------|
| KCB | ✅ | ❌ Not configured |
| Stanbic | ✅ | ❌ Not configured |
| Absa | ✅ | ❌ Not configured |

#### F.4 Account Types - PARTIALLY CONFIGURED

| Account Type | Required | Status |
|--------------|----------|--------|
| Loans receivable | ✅ | ⚠️ Product-level configuration |
| Income | ✅ | ⚠️ Product-level configuration |
| Penalties | ✅ | ⚠️ Product-level configuration |
| Write-offs | ✅ | ⚠️ Needs verification |

#### F.5 Taxes - NOT CONFIGURED

| Tax | Required | Status |
|-----|----------|--------|
| VAT | ✅ | ❌ Not configured |
| Withholding Tax | ✅ | ❌ Not configured |

#### F.6 Payment Methods ✅ COMPLIANT

| Method | Required | Implemented | Status |
|--------|----------|-------------|--------|
| EFT/RTGS | ✅ | ✅ | Via journal entries |
| MPesa Paybill | ✅ | ✅ | M-Pesa module |
| Cheque | ✅ | ✅ | Via journal entries |
| Standing Order | ✅ | ❌ | **MISSING** |

#### F.7 Accounting Policies - NOT IMPLEMENTED

| Policy | Required | Status |
|--------|----------|--------|
| Journal approval | ✅ | ❌ Not implemented |
| Reversals | ✅ | ✅ Implemented |
| Bank reconciliation | ✅ | ⚠️ Odoo standard |
| Period close | ✅ | ⚠️ Odoo standard |

---

### SECTION G: BUDGETING - NOT IMPLEMENTED ❌

| Requirement | Status |
|-------------|--------|
| Annual/Quarterly/Monthly budgets | ❌ Not implemented |
| Department owners | ❌ Not implemented |
| Budget vs actual tracking | ❌ Not implemented |
| Alerts for overspending | ❌ Not implemented |

---

### SECTION H: INVESTOR MANAGEMENT ✅ COMPLIANT

| Requirement | Status |
|-------------|--------|
| Personal/company details | ✅ |
| Bank info | ✅ |
| Investment terms | ✅ |
| Monthly interest | ✅ |
| Compounding | ✅ |
| Withdrawals (prorated) | ✅ |
| Statements | ✅ |
| Tax reports | ⚠️ Partial |
| ROI KPIs | ✅ |

---

### SECTION I: HR & PAYROLL - NOT IMPLEMENTED ❌

| Requirement | Status |
|-------------|--------|
| Employee data | ❌ Not implemented |
| Payroll (PAYE, NSSF, SHIF, HELB) | ❌ Not implemented |
| Leave (21 days/year) | ❌ Not implemented |
| Staff loans (50% salary max) | ❌ Not implemented |
| Payslips | ❌ Not implemented |
| GL integration | ❌ Not implemented |

---

### SECTION J: ASSETS & DOCUMENTS - NOT IMPLEMENTED ❌

| Requirement | Status |
|-------------|--------|
| Asset categories + depreciation | ❌ Not implemented |
| Document role-based access | ❌ Not implemented |
| Audit trail | ⚠️ Partial (Odoo standard) |
| Knowledge Base (SOPs) | ❌ Not implemented |

---

### SECTION K: CRM & PORTAL ✅ COMPLIANT

| Requirement | Status |
|-------------|--------|
| Pipeline (Lead → Closed) | ⚠️ Use Odoo CRM |
| Templates | ✅ |
| Gmail integration | ✅ |
| Onfon SMS | ⚠️ Need integration |
| Portal Phase 1 | ✅ Django implemented |
| Portal Phase 2 | 📋 Future phase |

---

### SECTION L: DATA MIGRATION - READY ✅

| Requirement | Status |
|-------------|--------|
| Source: MFI Expert | ⚠️ Need extraction scripts |
| 924 customers | ✅ Ready |
| 400-600 loans | ✅ Ready |
| 100-200 investors | ✅ Ready |
| 24 months GL | ⚠️ Need COA first |

---

### SECTION M: NON-FUNCTIONAL - NEEDS VERIFICATION ⚠️

| Requirement | Status |
|-------------|--------|
| Cloud hosting | ⚠️ Verify deployment |
| MFA, encryption | ❌ MFA not implemented |
| Backup 5-7 years | ⚠️ Verify backup policy |
| RTO: 2-3 hrs | ⚠️ Verify |
| RPO: 24 hrs | ⚠️ Verify |
| 99.5% uptime | ⚠️ Verify SLA |
| Audit logs | ✅ Odoo standard |
| Regulatory compliance | ⚠️ In progress |

---

## 2. CRITICAL GAPS SUMMARY

### 🔴 CRITICAL (Must Fix Before Go-Live)

1. **User Roles & Security**
   - Missing 7 required user roles
   - No MFA implemented
   - Approval limits not configured
   - Segregation of duties not enforced

2. **Loan Products**
   - Bid bonds & Performance bonds: Wrong configuration (fee vs interest)
   - Asset financing: Missing dual-rate (staff vs client)
   - Penalty formula bug: Monthly rate treated as daily

3. **Collections Workflow**
   - Missing escalation buckets (1-30, 31-60, 61-90, 90+)
   - No automated reminders
   - No recovery workflow

4. **Accounting Setup**
   - Bank accounts not configured
   - Taxes not configured
   - COA not verified
   - Journal approval not configured

### 🟡 HIGH (Should Fix Before Go-Live)

1. HR/Payroll module not implemented
2. Budgeting not implemented
3. Asset management not implemented
4. Document management not configured
5. Missing business document types (CR12, permits, collateral)

### 🟢 MEDIUM (Can Fix Post Go-Live)

1. Fraud alerts
2. Compliance flags
3. Standing orders
4. Advanced reporting

---

## 3. RECOMMENDATIONS

### Immediate Actions (Next 2 Weeks)

1. **Fix Loan Products**
   ```
   - Create separate "Bid Bond Fee" and "Performance Bond Fee" products
   - Fix penalty formula (divide monthly rate by 30 for daily)
   - Create dual Asset Financing products (Staff/Client)
   ```

2. **Configure User Roles**
   ```
   - Create all 7 required user roles
   - Map to security groups
   - Configure approval limits
   - Enable MFA
   ```

3. **Setup Accounting**
   ```
   - Configure bank accounts (KCB, Stanbic, Absa)
   - Setup VAT and withholding tax
   - Verify COA alignment
   ```

4. **Implement Collections**
   ```
   - Create cron jobs for reminder notifications
   - Setup escalation workflow
   - Configure collection stages
   ```

### Phase 2 (Post Go-Live)

1. HR/Payroll module
2. Budgeting module
3. Asset management
4. Advanced CRM features
5. Document management system

---

## 4. GO-LIVE READINESS ASSESSMENT

| Area | Score | Status |
|------|-------|--------|
| Loan Products | 70% | ⚠️ Needs fixes |
| Customer/KYC | 85% | ✅ Ready |
| Workflow | 75% | ⚠️ Needs collections |
| Accounting | 60% | ❌ Needs setup |
| Security/Roles | 40% | ❌ Critical gap |
| Investor | 90% | ✅ Ready |
| Portal | 90% | ✅ Ready |
| **OVERALL** | **73%** | ⚠️ **NOT READY** |

---

## 5. DETAILED FIX SPECIFICATIONS

### Fix 1: Loan Product Corrections

```xml
<!-- Bid Bond - Fee-based, not loan -->
<record id="bid_bond_fee" model="alba.loan.product">
    <field name="name">Bid Bond (Fee-based)</field>
    <field name="category">bid_bond</field>
    <field name="interest_method">fee_only</field>  <!-- New method -->
    <field name="origination_fee_percentage">1.5</field>
    <field name="interest_rate">0</field>
</record>

<!-- Asset Financing - Staff -->
<record id="asset_financing_staff" model="alba.loan.product">
    <field name="name">Asset Financing - Staff</field>
    <field name="interest_rate">5</field>
    <field name="interest_method">reducing_balance</field>
</record>

<!-- Asset Financing - Client -->
<record id="asset_financing_client" model="alba.loan.product">
    <field name="name">Asset Financing - Client</field>
    <field name="interest_rate">10</field>
    <field name="interest_method">flat_rate</field>
</record>
```

### Fix 2: Penalty Formula Correction

```python
# In loan_repayment.py
def _auto_allocate_components(self):
    ...
    # FIX: Daily penalty rate = monthly rate / 30
    daily_penalty_rate = (loan_product.penalty_rate / 100) / 30
    penalty_owed = overdue_amount * daily_penalty_rate * days_overdue
```

### Fix 3: Security Groups Expansion

```xml
<!-- Add to security.xml -->
<record id="group_relationship_officer" model="res.groups">
    <field name="name">Relationship Officer</field>
</record>

<record id="group_finance_officer" model="res.groups">
    <field name="name">Finance Officer</field>
</record>

<record id="group_operations_manager" model="res.groups">
    <field name="name">Operations Manager</field>
</record>

<record id="group_director" model="res.groups">
    <field name="name">Director</field>
</record>
```

---

## 6. COMPLIANCE RISK ASSESSMENT

| Risk | Level | Mitigation |
|------|-------|------------|
| Unauthorized loan approvals | 🔴 High | Implement approval limits |
| Incorrect penalty calculations | 🔴 High | Fix formula immediately |
| Missing audit trail | 🔴 High | Enable detailed logging |
| Tax compliance | 🟡 Medium | Configure taxes before go-live |
| Data security | 🟡 Medium | Enable MFA |
| Regulatory reporting | 🟡 Medium | Plan for CBK reports |

---

## 7. CONCLUSION

**Current State:** The Alba Capital ERP implementation is approximately **73% complete** with critical gaps in:
1. User roles and security
2. Loan product configurations
3. Collections workflow
4. Accounting setup

**Recommendation:** 
- **DO NOT proceed with June 15 go-live** without addressing critical gaps
- Minimum 4-6 weeks needed to fix critical issues
- Consider phased go-live: Loans first, HR/Payroll later

**Next Steps:**
1. Prioritize critical fixes (loan products, security, accounting)
2. Conduct UAT after fixes
3. Plan for 2-week hypercare period
4. Schedule final go-live for late July 2026

---

*Report Generated: March 25, 2026*
*Auditor: Senior Odoo ERP Implementation Consultant*
