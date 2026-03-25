# -*- coding: utf-8 -*-
"""
Alba Capital Loan Rules & Modifications
Based on Business Requirements Questionnaire Section C

Implements:
- Restructure (+3% fee)
- Reschedule (change dates)
- Early Settlement (full payoff)
- Default interest continuation
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta


class AlbaLoanRestructure(models.Model):
    """Loan Restructure - with 3% fee"""
    
    _name = "alba.loan.restructure"
    _description = "Loan Restructure"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    # Links
    loan_id = fields.Many2one("alba.loan", string="Loan", required=True, ondelete="restrict")
    customer_id = fields.Many2one("alba.customer", related="loan_id.customer_id", store=True)
    
    # Restructure Details
    restructure_date = fields.Date(string="Restructure Date", required=True, default=fields.Date.today)
    reason = fields.Text(string="Restructure Reason", required=True)
    
    # New Terms
    new_principal_amount = fields.Monetary(string="New Principal", currency_field="currency_id")
    new_interest_rate = fields.Float(string="New Interest Rate (%)", digits=(5, 2))
    new_tenure_months = fields.Integer(string="New Tenure (Months)")
    new_installment_amount = fields.Monetary(string="New Installment", currency_field="currency_id", compute="_compute_new_installment")
    
    # Fees
    restructure_fee_rate = fields.Float(string="Restructure Fee Rate (%)", default=3.0,
        help="Standard restructure fee is 3%")
    restructure_fee_amount = fields.Monetary(string="Restructure Fee", currency_field="currency_id", compute="_compute_fee")
    
    # Totals
    currency_id = fields.Many2one("res.currency", related="loan_id.currency_id", store=True)
    total_new_payable = fields.Monetary(string="Total New Payable", currency_field="currency_id", compute="_compute_totals")
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("pending", "Pending Approval"),
        ("approved", "Approved"),
        ("applied", "Applied"),
        ("rejected", "Rejected"),
    ], string="Status", default="draft", tracking=True)
    
    # Approval
    requested_by = fields.Many2one("res.users", string="Requested By", default=lambda self: self.env.user)
    approved_by = fields.Many2one("res.users", string="Approved By", readonly=True)
    approved_date = fields.Date(string="Approved Date")
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.restructure") or "New"
        return super().create(vals_list)
    
    @api.depends("new_principal_amount", "new_interest_rate", "new_tenure_months")
    def _compute_new_installment(self):
        for rec in self:
            if rec.new_tenure_months > 0:
                total = rec.new_principal_amount * (1 + (rec.new_interest_rate / 100) * rec.new_tenure_months / 12)
                rec.new_installment_amount = total / rec.new_tenure_months
            else:
                rec.new_installment_amount = 0
    
    @api.depends("loan_id", "restructure_fee_rate")
    def _compute_fee(self):
        for rec in self:
            rec.restructure_fee_amount = rec.loan_id.outstanding_balance * (rec.restructure_fee_rate / 100)
    
    @api.depends("new_principal_amount", "restructure_fee_amount")
    def _compute_totals(self):
        for rec in self:
            rec.total_new_payable = rec.new_principal_amount + rec.restructure_fee_amount
    
    def action_submit(self):
        """Submit restructure request"""
        for rec in self:
            # Validate loan can be restructured
            if rec.loan_id.state not in ["active", "overdue"]:
                raise UserError(_("Only active or overdue loans can be restructured."))
            
            # Check if already has pending restructure
            existing = self.search([
                ("loan_id", "=", rec.loan_id.id),
                ("state", "in", ["draft", "pending"]),
                ("id", "!=", rec.id),
            ])
            if existing:
                raise UserError(_("There is already a pending restructure for this loan."))
            
            rec.state = "pending"
            rec.loan_id.message_post(body=_("Restructure request %s submitted for approval.") % rec.name)
    
    def action_approve(self):
        """Approve restructure"""
        for rec in self:
            # Check approval authority
            if not self.env.user.has_group("alba_loans.group_operations_manager"):
                raise UserError(_("Only Operations Manager or above can approve restructures."))
            
            rec.write({
                "state": "approved",
                "approved_by": self.env.user.id,
                "approved_date": fields.Date.today(),
            })
            
            rec.loan_id.message_post(body=_("Restructure %s approved by %s.") % (rec.name, self.env.user.name))
    
    def action_apply(self):
        """Apply the restructure to the loan"""
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Restructure must be approved before applying."))
            
            # Apply new terms to loan
            rec.loan_id.write({
                "principal_amount": rec.new_principal_amount,
                "interest_rate": rec.new_interest_rate,
                "tenure_months": rec.new_tenure_months,
                "installment_amount": rec.new_installment_amount,
                "outstanding_balance": rec.total_new_payable,
            })
            
            # Create fee charge if applicable
            if rec.restructure_fee_amount > 0:
                self.env["alba.loan.fee"].create({
                    "loan_id": rec.loan_id.id,
                    "fee_type": "restructure",
                    "amount": rec.restructure_fee_amount,
                    "description": _("Restructure fee (%s%%)") % rec.restructure_fee_rate,
                })
            
            # Log the restructure
            rec.loan_id.message_post(body=_(
                "<b>LOAN RESTRUCTURED</b><br/>"
                "New Principal: KES %s<br/>"
                "New Rate: %s%%<br/>"
                "New Tenure: %s months<br/>"
                "Restructure Fee: KES %s<br/>"
                "Reference: %s"
            ) % (rec.new_principal_amount, rec.new_interest_rate, rec.new_tenure_months, rec.restructure_fee_amount, rec.name))
            
            rec.state = "applied"


class AlbaLoanReschedule(models.Model):
    """Loan Reschedule - change payment dates without changing amounts"""
    
    _name = "alba.loan.reschedule"
    _description = "Loan Reschedule"
    _order = "create_date desc"
    
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    loan_id = fields.Many2one("alba.loan", string="Loan", required=True)
    
    # Original Schedule
    original_payment_date = fields.Date(string="Original Payment Date", required=True)
    
    # New Schedule
    new_payment_date = fields.Date(string="New Payment Date", required=True)
    reason = fields.Text(string="Reschedule Reason", required=True)
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("applied", "Applied"),
    ], string="Status", default="draft")
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.reschedule") or "New"
        return super().create(vals_list)
    
    def action_apply(self):
        """Apply reschedule"""
        for rec in self:
            # Update repayment schedule
            schedule = self.env["alba.repayment.schedule"].search([
                ("loan_id", "=", rec.loan_id.id),
                ("due_date", "=", rec.original_payment_date),
            ], limit=1)
            
            if schedule:
                schedule.due_date = rec.new_payment_date
            
            # Log
            rec.loan_id.message_post(body=_(
                "Payment rescheduled from %s to %s.<br/>Reason: %s"
            ) % (rec.original_payment_date, rec.new_payment_date, rec.reason))
            
            rec.state = "applied"


class AlbaLoanEarlySettlement(models.Model):
    """Early Settlement - full payoff before maturity"""
    
    _name = "alba.loan.early.settlement"
    _description = "Early Settlement"
    _order = "create_date desc"
    
    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    
    loan_id = fields.Many2one("alba.loan", string="Loan", required=True)
    customer_id = fields.Many2one("alba.customer", related="loan_id.customer_id", store=True)
    
    # Settlement Calculation
    settlement_date = fields.Date(string="Settlement Date", required=True, default=fields.Date.today)
    principal_outstanding = fields.Monetary(string="Principal Outstanding", currency_field="currency_id", related="loan_id.outstanding_balance")
    accrued_interest = fields.Monetary(string="Accrued Interest", currency_field="currency_id", compute="_compute_settlement_amount")
    penalty_amount = fields.Monetary(string="Early Settlement Fee", currency_field="currency_id", compute="_compute_settlement_amount")
    total_settlement_amount = fields.Monetary(string="Total Settlement Amount", currency_field="currency_id", compute="_compute_settlement_amount")
    
    # Discounts
    discount_percentage = fields.Float(string="Interest Discount (%)", default=0.0,
        help="Discount on interest for early settlement")
    discount_amount = fields.Monetary(string="Discount Amount", currency_field="currency_id", compute="_compute_settlement_amount")
    
    # Final Amount
    final_settlement_amount = fields.Monetary(string="Final Settlement Amount", currency_field="currency_id", compute="_compute_settlement_amount")
    currency_id = fields.Many2one("res.currency", related="loan_id.currency_id", store=True)
    
    # Status
    state = fields.Selection([
        ("draft", "Draft"),
        ("quoted", "Quoted"),
        ("accepted", "Accepted"),
        ("paid", "Paid"),
    ], string="Status", default="draft")
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("alba.loan.early.settlement") or "New"
        return super().create(vals_list)
    
    @api.depends("loan_id", "settlement_date", "discount_percentage")
    def _compute_settlement_amount(self):
        for rec in self:
            # Calculate accrued interest up to settlement date
            loan = rec.loan_id
            days_to_settlement = (rec.settlement_date - loan.disbursement_date).days
            
            if loan.interest_method == "flat_rate":
                daily_interest = loan.interest_amount / (loan.tenure_months * 30)
                rec.accrued_interest = daily_interest * days_to_settlement
            else:
                # Reducing balance - complex calculation
                rec.accrued_interest = loan.accrued_interest
            
            # Early settlement fee (if any)
            rec.penalty_amount = 0  # No penalty for early settlement
            
            rec.total_settlement_amount = loan.outstanding_balance + rec.accrued_interest
            
            # Apply discount
            rec.discount_amount = rec.accrued_interest * (rec.discount_percentage / 100)
            rec.final_settlement_amount = rec.total_settlement_amount - rec.discount_amount
    
    def action_generate_quote(self):
        """Generate settlement quote"""
        for rec in self:
            rec.state = "quoted"
            
            # Send quote to customer
            rec.loan_id.message_post(body=_(
                "<b>EARLY SETTLEMENT QUOTE</b><br/>"
                "Quote Ref: %s<br/>"
                "Settlement Date: %s<br/>"
                "Principal: KES %s<br/>"
                "Accrued Interest: KES %s<br/>"
                "Discount: KES %s<br/>"
                "<b>Total to Pay: KES %s</b>"
            ) % (rec.name, rec.settlement_date, rec.principal_outstanding, rec.accrued_interest, rec.discount_amount, rec.final_settlement_amount))
    
    def action_accept(self):
        """Customer accepts quote"""
        for rec in self:
            rec.state = "accepted"
            rec.loan_id.message_post(body=_("Early settlement quote %s accepted.") % rec.name)
    
    def action_mark_paid(self):
        """Mark settlement as paid and close loan"""
        for rec in self:
            # Create final repayment
            repayment = self.env["alba.loan.repayment"].create({
                "loan_id": rec.loan_id.id,
                "payment_date": rec.settlement_date,
                "amount_paid": rec.final_settlement_amount,
                "payment_method": "bank_transfer",
                "notes": _("Early settlement - %s") % rec.name,
            })
            repayment.action_post()
            
            # Close loan
            rec.loan_id.action_close()
            
            rec.state = "paid"
            rec.loan_id.message_post(body=_("<b>LOAN SETTLED EARLY</b><br/>Settlement Reference: %s<br/>Final Amount: KES %s") % (rec.name, rec.final_settlement_amount))


class AlbaLoanFee(models.Model):
    """Additional loan fees (restructure, late payment, etc.)"""
    
    _name = "alba.loan.fee"
    _description = "Loan Fee"
    _order = "create_date desc"
    
    loan_id = fields.Many2one("alba.loan", string="Loan", required=True, ondelete="cascade")
    
    fee_type = fields.Selection([
        ("restructure", "Restructure Fee"),
        ("late_payment", "Late Payment Fee"),
        ("recovery", "Recovery Fee"),
        ("legal", "Legal Fee"),
        ("other", "Other"),
    ], string="Fee Type", required=True)
    
    amount = fields.Monetary(string="Amount", currency_field="currency_id", required=True)
    currency_id = fields.Many2one("res.currency", related="loan_id.currency_id", store=True)
    
    description = fields.Text(string="Description")
    date_applied = fields.Date(string="Date Applied", default=fields.Date.today)
    
    # Posting
    is_posted = fields.Boolean(string="Posted to GL", default=False)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    
    def action_post(self):
        """Post fee to general ledger"""
        for rec in self:
            if rec.is_posted:
                raise UserError(_("Fee is already posted."))
            
            # Create journal entry
            # DR: Loan Receivable (increase balance)
            # CR: Fee Income
            
            product = rec.loan_id.loan_product_id
            if not product.account_fees_income_id:
                raise UserError(_("Fee income account not configured for product %s") % product.name)
            
            move = self.env["account.move"].create({
                "journal_id": self.env["account.journal"].search([("type", "=", "general")], limit=1).id,
                "date": rec.date_applied,
                "ref": _("Fee: %s - %s") % (rec.fee_type, rec.loan_id.loan_number),
                "line_ids": [
                    (0, 0, {
                        "account_id": product.account_loan_receivable_id.id,
                        "partner_id": rec.loan_id.customer_id.partner_id.id,
                        "name": rec.description or rec.fee_type,
                        "debit": rec.amount,
                    }),
                    (0, 0, {
                        "account_id": product.account_fees_income_id.id,
                        "partner_id": rec.loan_id.customer_id.partner_id.id,
                        "name": rec.description or rec.fee_type,
                        "credit": rec.amount,
                    }),
                ],
            })
            move.action_post()
            
            rec.write({
                "is_posted": True,
                "move_id": move.id,
            })
            
            # Increase loan balance
            rec.loan_id.outstanding_balance += rec.amount


class AlbaLoan(models.Model):
    """Extend loan with rules functionality"""
    
    _inherit = "alba.loan"
    
    # Restructure tracking
    restructure_count = fields.Integer(string="Restructure Count", compute="_compute_modification_count")
    last_restructure_date = fields.Date(string="Last Restructure Date", compute="_compute_modification_count")
    
    # Reschedule tracking
    reschedule_count = fields.Integer(string="Reschedule Count", compute="_compute_modification_count")
    
    # Early settlement
    early_settlement_quote_ids = fields.One2many("alba.loan.early.settlement", "loan_id", string="Settlement Quotes")
    
    # Default interest continuation
    default_interest_continue = fields.Boolean(string="Continue Interest During Default", default=True,
        help="If checked, interest continues to accrue during default period")
    
    @api.depends("restructure_ids", "reschedule_ids")
    def _compute_modification_count(self):
        for rec in self:
            rec.restructure_count = len(rec.restructure_ids.filtered(lambda x: x.state == "applied"))
            rec.last_restructure_date = rec.restructure_ids.filtered(lambda x: x.state == "applied")[:1].restructure_date
            rec.reschedule_count = len(rec.reschedule_ids.filtered(lambda x: x.state == "applied"))
    
    # Links
    restructure_ids = fields.One2many("alba.loan.restructure", "loan_id", string="Restructures")
    reschedule_ids = fields.One2many("alba.loan.reschedule", "loan_id", string="Reschedules")
    fee_ids = fields.One2many("alba.loan.fee", "loan_id", string="Additional Fees")
    
    total_fees_charged = fields.Monetary(string="Total Fees Charged", currency_field="currency_id", 
        compute="_compute_total_fees")
    
    @api.depends("fee_ids")
    def _compute_total_fees(self):
        for rec in self:
            rec.total_fees_charged = sum(rec.fee_ids.mapped("amount"))


# CRON JOB: Continue interest during default
class AlbaLoanInterestCron(models.Model):
    """Handle default interest continuation"""
    
    _name = "alba.loan.interest.cron"
    _description = "Default Interest Continuation"
    
    @api.model
    def cron_continue_default_interest(self):
        """Daily cron to continue accruing interest for defaulted loans"""
        
        defaulted_loans = self.env["alba.loan"].search([
            ("state", "in", ["overdue", "npl"]),
            ("default_interest_continue", "=", True),
        ])
        
        for loan in defaulted_loans:
            # Continue interest accrual
            if loan.interest_method == "flat_rate":
                # Flat rate - interest continues on original principal
                daily_interest = loan.interest_amount / (loan.tenure_months * 30)
                loan.accrued_interest += daily_interest
            else:
                # Reducing balance - recalculate
                monthly_rate = loan.interest_rate / 100 / 12
                daily_rate = monthly_rate / 30
                loan.accrued_interest += loan.outstanding_balance * daily_rate
            
            # Log
            loan.message_post(body=_("Default interest accrued: KES %s") % loan.accrued_interest)
