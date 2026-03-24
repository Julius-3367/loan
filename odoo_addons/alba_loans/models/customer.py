# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaCustomer(models.Model):
    _name = "alba.customer"
    _description = "Alba Capital Customer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"
    _order = "create_date desc"

    # ── Partner link ─────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    display_name = fields.Char(
        string="Name",
        compute="_compute_display_name",
        store=True,
        index=True,
    )

    # ── Django sync ───────────────────────────────────────────────────────────
    django_customer_id = fields.Integer(
        string="Django Customer ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding Customer record in the Django portal database.",
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    id_number = fields.Char(string="ID / Passport Number", tracking=True)
    id_type = fields.Selection(
        selection=[
            ("national_id", "National ID"),
            ("passport", "Passport"),
            ("alien_id", "Alien ID / Foreign Certificate"),
        ],
        string="ID Type",
        default="national_id",
        tracking=True,
    )
    date_of_birth = fields.Date(string="Date of Birth")
    age = fields.Integer(string="Age", compute="_compute_age", store=False)
    gender = fields.Selection(
        selection=[
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other / Prefer not to say"),
        ],
        string="Gender",
        tracking=True,
    )
    marital_status = fields.Selection(
        selection=[
            ("single", "Single"),
            ("married", "Married"),
            ("divorced", "Divorced"),
            ("widowed", "Widowed"),
        ],
        string="Marital Status",
    )
    nationality = fields.Char(string="Nationality", default="Kenyan")

    # ── Location (Kenya) ──────────────────────────────────────────────────────
    county = fields.Char(string="County")
    sub_county = fields.Char(string="Sub-County")
    ward = fields.Char(string="Ward")

    # ── Employment ────────────────────────────────────────────────────────────
    employment_status = fields.Selection(
        selection=[
            ("employed", "Employed"),
            ("self_employed", "Self-Employed"),
            ("business_owner", "Business Owner"),
            ("unemployed", "Unemployed"),
            ("retired", "Retired"),
        ],
        string="Employment Status",
        tracking=True,
    )
    employer_name = fields.Char(string="Employer / Business Name")
    employer_phone = fields.Char(string="Employer Phone")
    job_title = fields.Char(string="Job Title")
    months_employed = fields.Integer(string="Months in Current Employment")
    monthly_income = fields.Monetary(
        string="Monthly Net Income",
        currency_field="currency_id",
    )
    other_income = fields.Monetary(
        string="Other Monthly Income",
        currency_field="currency_id",
    )

    # ── KYC & Risk ────────────────────────────────────────────────────────────
    kyc_status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("partial", "Partially Complete"),
            ("complete", "Complete — Awaiting Verification"),
            ("verified", "Verified"),
            ("rejected", "Rejected"),
        ],
        string="KYC Status",
        default="pending",
        tracking=True,
        index=True,
    )
    kyc_verified_by = fields.Many2one(
        "res.users",
        string="KYC Verified By",
        readonly=True,
        tracking=True,
    )
    kyc_verified_date = fields.Datetime(
        string="KYC Verified On",
        readonly=True,
        tracking=True,
    )
    credit_score = fields.Integer(
        string="Internal Credit Score",
        default=0,
        tracking=True,
        help="0-100 internal credit score assigned by the credit team.",
    )
    risk_rating = fields.Selection(
        selection=[
            ("low", "Low Risk"),
            ("medium", "Medium Risk"),
            ("high", "High Risk"),
            ("very_high", "Very High Risk"),
        ],
        string="Risk Rating",
        tracking=True,
    )
    blacklisted = fields.Boolean(
        string="Blacklisted",
        default=False,
        tracking=True,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )
    # ── Banking ───────────────────────────────────────────────────────────────
    bank_name = fields.Char(string="Bank Name")
    bank_account_number = fields.Char(string="Bank Account Number")
    bank_branch = fields.Char(string="Bank Branch")
    mpesa_number = fields.Char(
        string="M-Pesa Number",
        help="Must start with 254 e.g. 254712345678",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    loan_application_ids = fields.One2many(
        "alba.loan.application",
        "customer_id",
        string="Loan Applications",
    )
    loan_ids = fields.One2many(
        "alba.loan",
        "customer_id",
        string="Active Loans",
    )

    # ── Computed counters ─────────────────────────────────────────────────────
    loan_application_count = fields.Integer(
        string="Applications",
        compute="_compute_loan_stats",
        store=True,
    )
    active_loan_count = fields.Integer(
        string="Active Loans",
        compute="_compute_loan_stats",
        store=True,
    )
    total_borrowed = fields.Monetary(
        string="Total Disbursed",
        compute="_compute_loan_stats",
        store=True,
        currency_field="currency_id",
    )
    outstanding_balance = fields.Monetary(
        string="Total Outstanding",
        compute="_compute_loan_stats",
        store=True,
        currency_field="currency_id",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Currency",
        store=True,
        readonly=True,
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    # ...existing code...
    notes = fields.Text(string="Internal Notes")

    # ── SQL constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "unique_django_customer_id",
            "UNIQUE(django_customer_id)",
            "A customer with this Django Customer ID already exists.",
        ),
        (
            "unique_id_number",
            "UNIQUE(id_number)",
            "A customer with this ID / Passport number already exists.",
        ),
    ]

    # =========================================================================
    # Computed field methods
    # =========================================================================

    @api.depends("partner_id", "partner_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.partner_id.name or _("New Customer")

    @api.depends("date_of_birth")
    def _compute_age(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_of_birth:
                delta = today - rec.date_of_birth
                rec.age = int(delta.days / 365.25)
            else:
                rec.age = 0

    @api.depends(
        "loan_application_ids",
        "loan_ids",
        "loan_ids.state",
        "loan_ids.principal_amount",
        "loan_ids.outstanding_balance",
    )
    def _compute_loan_stats(self):
        for rec in self:
            applications = rec.loan_application_ids
            active_loans = rec.loan_ids.filtered(lambda l: l.state == "active")
            rec.loan_application_count = len(applications)
            rec.active_loan_count = len(active_loans)
            rec.total_borrowed = sum(active_loans.mapped("principal_amount"))
            rec.outstanding_balance = sum(active_loans.mapped("outstanding_balance"))

    # =========================================================================
    # Constraint methods
    # =========================================================================

    @api.constrains("credit_score")
    def _check_credit_score(self):
        for rec in self:
            if not (0 <= rec.credit_score <= 100):
                raise ValidationError(_("Credit score must be between 0 and 100."))

    @api.constrains("monthly_income")
    def _check_monthly_income(self):
        for rec in self:
            if rec.monthly_income < 0:
                raise ValidationError(_("Monthly income cannot be negative."))

    # =========================================================================
    # Business actions
    # =========================================================================

    def action_verify_kyc(self):
        """Mark KYC as verified by the current user."""
        self.ensure_one()
        self.write(
            {
                "kyc_status": "verified",
                "kyc_verified_by": self.env.uid,
                "kyc_verified_date": fields.Datetime.now(),
            }
        )
        self.message_post(
            body=_("KYC status marked as <b>Verified</b> by %s.") % self.env.user.name
        )

    def action_reject_kyc(self):
        """Mark KYC as rejected."""
        self.ensure_one()
        self.write({"kyc_status": "rejected"})
        self.message_post(
            body=_("KYC status marked as <b>Rejected</b> by %s.") % self.env.user.name
        )

    def action_blacklist(self):
        self.ensure_one()
        self.write({"blacklisted": True})
        self.message_post(body=_("Customer has been <b>blacklisted</b>."))

    def action_view_applications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan Applications — %s") % self.display_name,
            "res_model": "alba.loan.application",
            "view_mode": "list,kanban,form",
            "domain": [("customer_id", "=", self.id)],
            "context": {"default_customer_id": self.id},
        }

    def action_view_loans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Loans — %s") % self.display_name,
            "res_model": "alba.loan",
            "view_mode": "list,form",
            "domain": [("customer_id", "=", self.id)],
            "context": {"default_customer_id": self.id},
        }

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Sync name back to partner if partner not yet provided
            if vals.get("partner_id"):
                pass  # partner already supplied
        records = super().create(vals_list)
        return records

    def name_get(self):
        return [(rec.id, rec.partner_id.name or _("New Customer")) for rec in self]
