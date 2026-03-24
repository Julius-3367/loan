# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaRepaymentSchedule(models.Model):
    _name = "alba.repayment.schedule"
    _description = "Alba Capital Loan Repayment Schedule"
    _order = "loan_id, installment_number asc"
    _rec_name = "display_name"

    # ── Identification ────────────────────────────────────────────────────────
    display_name = fields.Char(
        string="Label",
        compute="_compute_display_name",
        store=True,
    )

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="loan_id.customer_id",
        store=True,
        readonly=True,
        index=True,
    )

    # ── Instalment Details ────────────────────────────────────────────────────
    installment_number = fields.Integer(
        string="Instalment #",
        required=True,
    )
    due_date = fields.Date(
        string="Due Date",
        required=True,
        index=True,
    )

    # ── Amounts ───────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
        store=True,
        readonly=True,
    )
    opening_balance = fields.Monetary(
        string="Opening Balance",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    principal_due = fields.Monetary(
        string="Principal Due",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    interest_due = fields.Monetary(
        string="Interest Due",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    total_due = fields.Monetary(
        string="Total Due",
        currency_field="currency_id",
        compute="_compute_total_due",
        store=True,
    )
    closing_balance = fields.Monetary(
        string="Closing Balance",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )

    # ── Paid Amounts ──────────────────────────────────────────────────────────
    principal_paid = fields.Monetary(
        string="Principal Paid",
        currency_field="currency_id",
        default=0.0,
    )
    interest_paid = fields.Monetary(
        string="Interest Paid",
        currency_field="currency_id",
        default=0.0,
    )
    total_paid = fields.Monetary(
        string="Total Paid",
        currency_field="currency_id",
        compute="_compute_total_paid",
        store=True,
    )

    # ── Balances ──────────────────────────────────────────────────────────────
    balance_due = fields.Monetary(
        string="Balance Due",
        currency_field="currency_id",
        compute="_compute_balance_due",
        store=True,
        help="Remaining amount to be paid for this instalment.",
    )
    days_overdue = fields.Integer(
        string="Days Overdue",
        compute="_compute_days_overdue",
        store=True,
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
            ("overdue", "Overdue"),
        ],
        string="Status",
        default="pending",
        compute="_compute_status",
        store=True,
        index=True,
    )

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "installment_loan_unique",
            "UNIQUE(loan_id, installment_number)",
            "Instalment number must be unique per loan.",
        ),
        (
            "principal_non_negative",
            "CHECK(principal_due >= 0)",
            "Principal due cannot be negative.",
        ),
        (
            "interest_non_negative",
            "CHECK(interest_due >= 0)",
            "Interest due cannot be negative.",
        ),
        (
            "principal_paid_non_negative",
            "CHECK(principal_paid >= 0)",
            "Principal paid cannot be negative.",
        ),
        (
            "interest_paid_non_negative",
            "CHECK(interest_paid >= 0)",
            "Interest paid cannot be negative.",
        ),
    ]

    # =========================================================================
    # Computed Methods
    # =========================================================================

    @api.depends("loan_id", "installment_number")
    def _compute_display_name(self):
        for rec in self:
            loan_ref = rec.loan_id.loan_number or "?"
            rec.display_name = _("Instalment %d — %s") % (
                rec.installment_number,
                loan_ref,
            )

    @api.depends("principal_due", "interest_due")
    def _compute_total_due(self):
        for rec in self:
            rec.total_due = rec.principal_due + rec.interest_due

    @api.depends("principal_paid", "interest_paid")
    def _compute_total_paid(self):
        for rec in self:
            rec.total_paid = rec.principal_paid + rec.interest_paid

    @api.depends("total_due", "total_paid")
    def _compute_balance_due(self):
        for rec in self:
            rec.balance_due = max(rec.total_due - rec.total_paid, 0.0)

    @api.depends("due_date", "balance_due")
    def _compute_days_overdue(self):
        today = fields.Date.today()
        for rec in self:
            if rec.balance_due > 0.0 and rec.due_date and rec.due_date < today:
                rec.days_overdue = (today - rec.due_date).days
            else:
                rec.days_overdue = 0

    @api.depends("balance_due", "total_paid", "total_due", "due_date")
    def _compute_status(self):
        today = fields.Date.today()
        for rec in self:
            if rec.balance_due <= 0.0:
                rec.status = "paid"
            elif rec.total_paid > 0.0:
                # Some payment received but not fully cleared
                if rec.due_date and rec.due_date < today:
                    rec.status = "overdue"
                else:
                    rec.status = "partial"
            elif rec.due_date and rec.due_date < today:
                rec.status = "overdue"
            else:
                rec.status = "pending"

    # =========================================================================
    # Constraint Methods
    # =========================================================================

    @api.constrains("principal_paid", "principal_due")
    def _check_principal_paid(self):
        for rec in self:
            if rec.principal_paid > rec.principal_due + 0.01:
                raise ValidationError(
                    _(
                        "Principal paid (%s) cannot exceed principal due (%s) "
                        "for instalment %d."
                    )
                    % (rec.principal_paid, rec.principal_due, rec.installment_number)
                )

    @api.constrains("interest_paid", "interest_due")
    def _check_interest_paid(self):
        for rec in self:
            if rec.interest_paid > rec.interest_due + 0.01:
                raise ValidationError(
                    _(
                        "Interest paid (%s) cannot exceed interest due (%s) "
                        "for instalment %d."
                    )
                    % (rec.interest_paid, rec.interest_due, rec.installment_number)
                )

    # =========================================================================
    # Business Logic
    # =========================================================================

    def apply_payment(self, amount_received):
        """
        Allocate a payment amount to this instalment.
        Returns the unapplied remainder (if any).

        Allocation order: interest first, then principal.
        """
        self.ensure_one()
        remainder = amount_received

        # Allocate interest first
        interest_outstanding = self.interest_due - self.interest_paid
        if interest_outstanding > 0.0:
            interest_apply = min(remainder, interest_outstanding)
            self.interest_paid += interest_apply
            remainder -= interest_apply

        # Then principal
        principal_outstanding = self.principal_due - self.principal_paid
        if principal_outstanding > 0.0 and remainder > 0.0:
            principal_apply = min(remainder, principal_outstanding)
            self.principal_paid += principal_apply
            remainder -= principal_apply

        return round(remainder, 2)

    def action_reset(self):
        """Reset paid amounts (e.g. after a payment reversal)."""
        self.ensure_one()
        self.write({"principal_paid": 0.0, "interest_paid": 0.0})
