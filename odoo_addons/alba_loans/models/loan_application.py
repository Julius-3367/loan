# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaLoanApplication(models.Model):
    _name = "alba.loan.application"
    _description = "Alba Capital Loan Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _rec_name = "application_number"

    # ── Identification ────────────────────────────────────────────────────────
    application_number = fields.Char(
        string="Application Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )
    django_application_id = fields.Integer(
        string="Django Application ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding LoanApplication record in the Django portal.",
    )

    # ── Parties ───────────────────────────────────────────────────────────────
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="customer_id.partner_id",
        store=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        required=True,
        ondelete="restrict",
        tracking=True,
    )

    # ── Loan Details ──────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    requested_amount = fields.Monetary(
        string="Requested Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    approved_amount = fields.Monetary(
        string="Approved Amount",
        currency_field="currency_id",
        tracking=True,
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
        tracking=True,
    )
    repayment_frequency = fields.Selection(
        selection=[
            ("weekly", "Weekly"),
            ("fortnightly", "Fortnightly"),
            ("monthly", "Monthly"),
        ],
        string="Repayment Frequency",
        required=True,
        default="monthly",
        tracking=True,
    )
    purpose = fields.Text(
        string="Loan Purpose",
        required=True,
    )

    # ── Computed totals (indicative) ──────────────────────────────────────────
    estimated_total_interest = fields.Monetary(
        string="Estimated Total Interest",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )
    estimated_total_fees = fields.Monetary(
        string="Estimated Total Fees",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )
    estimated_total_repayable = fields.Monetary(
        string="Estimated Total Repayable",
        currency_field="currency_id",
        compute="_compute_estimated_totals",
        store=False,
    )

    # ── Workflow State ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("credit_analysis", "Credit Analysis"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("employer_verification", "Employer Verification"),
            ("guarantor_confirmation", "Guarantor Confirmation"),
            ("disbursed", "Disbursed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )

    # ── Stage Timestamps ──────────────────────────────────────────────────────
    submitted_date = fields.Datetime(string="Submitted On", readonly=True, copy=False)
    reviewed_date = fields.Datetime(
        string="Review Started On", readonly=True, copy=False
    )
    credit_analysis_date = fields.Datetime(
        string="Credit Analysis On", readonly=True, copy=False
    )
    pending_approval_date = fields.Datetime(
        string="Sent for Approval On", readonly=True, copy=False
    )
    approved_date = fields.Datetime(string="Approved On", readonly=True, copy=False)
    employer_verification_date = fields.Datetime(
        string="Employer Verification On", readonly=True, copy=False
    )
    guarantor_confirmation_date = fields.Datetime(
        string="Guarantor Confirmation On", readonly=True, copy=False
    )
    disbursed_date = fields.Datetime(string="Disbursed On", readonly=True, copy=False)
    rejected_date = fields.Datetime(string="Rejected On", readonly=True, copy=False)
    cancelled_date = fields.Datetime(string="Cancelled On", readonly=True, copy=False)

    # ── Personnel ─────────────────────────────────────────────────────────────
    reviewed_by = fields.Many2one(
        "res.users",
        string="Reviewed By",
        readonly=True,
        tracking=True,
        copy=False,
    )
    approved_by = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
        tracking=True,
        copy=False,
    )
    disbursed_by = fields.Many2one(
        "res.users",
        string="Disbursed By",
        readonly=True,
        tracking=True,
        copy=False,
    )

    # ── Decision fields ───────────────────────────────────────────────────────
    rejection_reason = fields.Text(string="Rejection Reason", tracking=True)
    cancellation_reason = fields.Text(string="Cancellation Reason", tracking=True)
    internal_notes = fields.Text(string="Internal Notes")
    conditions_of_approval = fields.Text(
        string="Conditions of Approval",
        tracking=True,
        help="Any special conditions that must be met before disbursement.",
    )

    # ── Linked Loan ───────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Disbursed Loan",
        readonly=True,
        copy=False,
    )
    loan_count = fields.Integer(
        string="Loans",
        compute="_compute_loan_count",
    )

    # ── Company ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    # ── Boolean helpers for button visibility ─────────────────────────────────
    can_submit = fields.Boolean(compute="_compute_button_visibility")
    can_review = fields.Boolean(compute="_compute_button_visibility")
    can_credit_analysis = fields.Boolean(compute="_compute_button_visibility")
    can_pending_approval = fields.Boolean(compute="_compute_button_visibility")
    can_approve = fields.Boolean(compute="_compute_button_visibility")
    can_employer_verify = fields.Boolean(compute="_compute_button_visibility")
    can_guarantor_confirm = fields.Boolean(compute="_compute_button_visibility")
    can_disburse = fields.Boolean(compute="_compute_button_visibility")
    can_reject = fields.Boolean(compute="_compute_button_visibility")
    can_cancel = fields.Boolean(compute="_compute_button_visibility")

    # =========================================================================
    # Valid state transitions
    # =========================================================================

    _VALID_TRANSITIONS = {
        "draft": ["submitted", "cancelled"],
        "submitted": ["under_review", "cancelled"],
        "under_review": ["credit_analysis", "rejected"],
        "credit_analysis": ["pending_approval", "rejected"],
        "pending_approval": ["approved", "rejected"],
        "approved": ["employer_verification", "disbursed"],
        "employer_verification": ["guarantor_confirmation", "disbursed", "rejected"],
        "guarantor_confirmation": ["disbursed", "rejected"],
        "disbursed": [],
        "rejected": [],
        "cancelled": [],
    }

    def can_transition_to(self, new_state):
        self.ensure_one()
        return new_state in self._VALID_TRANSITIONS.get(self.state, [])

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("loan_product_id", "requested_amount", "tenure_months")
    def _compute_estimated_totals(self):
        for rec in self:
            product = rec.loan_product_id
            amount = rec.requested_amount or 0.0
            months = rec.tenure_months or 0
            if not product or amount <= 0 or months <= 0:
                rec.estimated_total_interest = 0.0
                rec.estimated_total_fees = 0.0
                rec.estimated_total_repayable = 0.0
                continue
            if product.interest_method == "flat_rate":
                interest = product.calculate_flat_interest(amount, months)
            else:
                schedule = product.calculate_reducing_schedule(amount, months)
                interest = sum(row["interest_due"] for row in schedule)
            fees = product.calculate_total_fees(amount)
            rec.estimated_total_interest = interest
            rec.estimated_total_fees = fees
            rec.estimated_total_repayable = amount + interest + fees

    def _compute_loan_count(self):
        for rec in self:
            rec.loan_count = 1 if rec.loan_id else 0

    @api.depends("state")
    def _compute_button_visibility(self):
        for rec in self:
            rec.can_submit = rec.state == "draft"
            rec.can_review = rec.state == "submitted"
            rec.can_credit_analysis = rec.state == "under_review"
            rec.can_pending_approval = rec.state == "credit_analysis"
            rec.can_approve = rec.state == "pending_approval"
            rec.can_employer_verify = rec.state == "approved"
            rec.can_guarantor_confirm = rec.state == "employer_verification"
            rec.can_disburse = rec.state in (
                "approved",
                "employer_verification",
                "guarantor_confirmation",
            )
            rec.can_reject = rec.state in (
                "under_review",
                "credit_analysis",
                "pending_approval",
                "employer_verification",
                "guarantor_confirmation",
            )
            rec.can_cancel = rec.state in ("draft", "submitted")

    # =========================================================================
    # Workflow action methods
    # =========================================================================

    def _assert_transition(self, target):
        self.ensure_one()
        if not self.can_transition_to(target):
            raise UserError(
                _("Cannot move application from '%s' to '%s'.") % (self.state, target)
            )

    def action_submit(self):
        for rec in self:
            rec._assert_transition("submitted")
            rec.write(
                {
                    "state": "submitted",
                    "submitted_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Application <b>submitted</b> by %s.") % self.env.user.name
            )
        return True

    def action_under_review(self):
        for rec in self:
            rec._assert_transition("under_review")
            rec.write(
                {
                    "state": "under_review",
                    "reviewed_date": fields.Datetime.now(),
                    "reviewed_by": self.env.uid,
                }
            )
            rec.message_post(body=_("Application moved to <b>Under Review</b>."))
        return True

    def action_credit_analysis(self):
        for rec in self:
            rec._assert_transition("credit_analysis")
            rec.write(
                {
                    "state": "credit_analysis",
                    "credit_analysis_date": fields.Datetime.now(),
                }
            )
            rec.message_post(body=_("Application moved to <b>Credit Analysis</b>."))
        return True

    def action_pending_approval(self):
        for rec in self:
            rec._assert_transition("pending_approval")
            rec.write(
                {
                    "state": "pending_approval",
                    "pending_approval_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Application forwarded for <b>Management Approval</b>.")
            )
        return True

    def action_approve(self):
        for rec in self:
            rec._assert_transition("approved")
            if not rec.approved_amount:
                rec.approved_amount = rec.requested_amount
            rec.write(
                {
                    "state": "approved",
                    "approved_date": fields.Datetime.now(),
                    "approved_by": self.env.uid,
                }
            )
            rec.message_post(
                body=_("Application <b>approved</b> for %s %s by %s.")
                % (rec.currency_id.name, rec.approved_amount, self.env.user.name)
            )
        return True

    def action_employer_verification(self):
        for rec in self:
            rec._assert_transition("employer_verification")
            rec.write(
                {
                    "state": "employer_verification",
                    "employer_verification_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Application sent for <b>Employer Verification</b>.")
            )
        return True

    def action_guarantor_confirmation(self):
        for rec in self:
            rec._assert_transition("guarantor_confirmation")
            rec.write(
                {
                    "state": "guarantor_confirmation",
                    "guarantor_confirmation_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Application sent for <b>Guarantor Confirmation</b>.")
            )
        return True

    def action_reject(self):
        for rec in self:
            rec._assert_transition("rejected")
            if not rec.rejection_reason:
                raise UserError(
                    _("Please provide a rejection reason before rejecting.")
                )
            rec.write(
                {
                    "state": "rejected",
                    "rejected_date": fields.Datetime.now(),
                }
            )
            rec.message_post(
                body=_("Application <b>rejected</b>. Reason: %s") % rec.rejection_reason
            )
        return True

    def action_cancel(self):
        for rec in self:
            rec._assert_transition("cancelled")
            rec.write(
                {
                    "state": "cancelled",
                    "cancelled_date": fields.Datetime.now(),
                }
            )
            rec.message_post(body=_("Application <b>cancelled</b>."))
        return True

    def action_open_disburse_wizard(self):
        """Open the disbursement wizard."""
        self.ensure_one()
        if self.state not in (
            "approved",
            "employer_verification",
            "guarantor_confirmation",
        ):
            raise UserError(_("Only approved applications can be disbursed."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Disburse Loan"),
            "res_model": "alba.loan.disburse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_application_id": self.id,
                "default_approved_amount": self.approved_amount
                or self.requested_amount,
            },
        }

    def action_view_loan(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan"),
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": self.loan_id.id,
        }

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("requested_amount", "loan_product_id")
    def _check_amount_within_product_limits(self):
        for rec in self:
            if not rec.loan_product_id:
                continue
            product = rec.loan_product_id
            if rec.requested_amount < product.min_amount:
                raise ValidationError(
                    _(
                        "Requested amount %s is below the minimum of %s for product '%s'."
                    )
                    % (rec.requested_amount, product.min_amount, product.name)
                )
            if rec.requested_amount > product.max_amount:
                raise ValidationError(
                    _("Requested amount %s exceeds the maximum of %s for product '%s'.")
                    % (rec.requested_amount, product.max_amount, product.name)
                )

    @api.constrains("tenure_months", "loan_product_id")
    def _check_tenure_within_product_limits(self):
        for rec in self:
            if not rec.loan_product_id:
                continue
            product = rec.loan_product_id
            if rec.tenure_months < product.min_tenure_months:
                raise ValidationError(
                    _(
                        "Tenure %s months is below the minimum of %s months for product '%s'."
                    )
                    % (rec.tenure_months, product.min_tenure_months, product.name)
                )
            if rec.tenure_months > product.max_tenure_months:
                raise ValidationError(
                    _(
                        "Tenure %s months exceeds the maximum of %s months for product '%s'."
                    )
                    % (rec.tenure_months, product.max_tenure_months, product.name)
                )

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("application_number", _("New")) == _("New"):
                vals["application_number"] = self.env["ir.sequence"].next_by_code(
                    "alba.loan.application.seq"
                ) or _("New")
        return super().create(vals_list)

    def name_get(self):
        return [
            (rec.id, "%s — %s" % (rec.application_number, rec.customer_id.display_name))
            for rec in self
        ]
