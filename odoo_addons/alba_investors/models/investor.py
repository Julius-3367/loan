# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlbaInvestor(models.Model):
    _name = "alba.investor"
    _description = "Alba Capital Investor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"
    _order = "create_date desc"

    # ── Partner link ──────────────────────────────────────────────────────────
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

    # ── Investor Number ───────────────────────────────────────────────────────
    investor_number = fields.Char(
        string="Investor Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )

    # ── Django sync ───────────────────────────────────────────────────────────
    django_investor_id = fields.Integer(
        string="Django Investor ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding Investor record in the Django portal.",
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
    )
    nationality = fields.Char(string="Nationality", default="Kenyan")

    # ── KYC ───────────────────────────────────────────────────────────────────
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

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("blacklisted", "Blacklisted"),
        ],
        string="Status",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Banking / Payout ──────────────────────────────────────────────────────
    bank_name = fields.Char(string="Bank Name")
    bank_account_number = fields.Char(string="Bank Account Number")
    bank_branch = fields.Char(string="Bank Branch")
    mpesa_number = fields.Char(
        string="M-Pesa Number",
        help="Must start with 254 e.g. 254712345678",
    )
    preferred_payment_method = fields.Selection(
        selection=[
            ("bank_transfer", "Bank Transfer"),
            ("mpesa", "M-Pesa"),
            ("cheque", "Cheque"),
        ],
        string="Preferred Payout Method",
        default="bank_transfer",
        tracking=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    investment_ids = fields.One2many(
        "alba.investment",
        "investor_id",
        string="Investments",
    )

    # ── Computed Portfolio ────────────────────────────────────────────────────
    active_investment_count = fields.Integer(
        string="Active Investments",
        compute="_compute_portfolio",
        store=True,
    )
    total_invested = fields.Monetary(
        string="Total Principal Invested",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )
    total_interest_earned = fields.Monetary(
        string="Total Interest Accrued",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )
    current_portfolio_value = fields.Monetary(
        string="Current Portfolio Value",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
        help="Sum of all active investments' current values (principal + accrued interest).",
    )
    total_interest_paid_out = fields.Monetary(
        string="Total Interest Paid Out",
        compute="_compute_portfolio",
        store=True,
        currency_field="currency_id",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Currency",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Internal Notes")
    active = fields.Boolean(default=True)

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "investor_number_unique",
            "UNIQUE(investor_number)",
            "An investor with this investor number already exists.",
        ),
        (
            "unique_id_number",
            "UNIQUE(id_number)",
            "An investor with this ID / Passport number already exists.",
        ),
        (
            "unique_django_investor_id",
            "UNIQUE(django_investor_id)",
            "An investor with this Django Investor ID already exists.",
        ),
    ]

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("partner_id", "partner_id.name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.partner_id.name or _("New Investor")

    @api.depends("date_of_birth")
    def _compute_age(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_of_birth:
                rec.age = int((today - rec.date_of_birth).days / 365.25)
            else:
                rec.age = 0

    @api.depends(
        "investment_ids",
        "investment_ids.state",
        "investment_ids.principal_amount",
        "investment_ids.current_value",
        "investment_ids.total_interest_accrued",
        "investment_ids.total_interest_paid",
    )
    def _compute_portfolio(self):
        for rec in self:
            active = rec.investment_ids.filtered(lambda i: i.state == "active")
            all_inv = rec.investment_ids

            rec.active_investment_count = len(active)
            rec.total_invested = sum(active.mapped("principal_amount"))
            rec.total_interest_earned = sum(all_inv.mapped("total_interest_accrued"))
            rec.current_portfolio_value = sum(active.mapped("current_value"))
            rec.total_interest_paid_out = sum(all_inv.mapped("total_interest_paid"))

    # =========================================================================
    # Constraint methods
    # =========================================================================

    @api.constrains("mpesa_number")
    def _check_mpesa_number(self):
        for rec in self:
            if rec.mpesa_number and not rec.mpesa_number.startswith("254"):
                raise ValidationError(
                    _("M-Pesa number must start with 254 (e.g. 254712345678).")
                )

    # =========================================================================
    # Business actions
    # =========================================================================

    def action_verify_kyc(self):
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
        self.ensure_one()
        self.write({"kyc_status": "rejected"})
        self.message_post(
            body=_("KYC status marked as <b>Rejected</b> by %s.") % self.env.user.name
        )

    def action_suspend(self):
        self.ensure_one()
        self.write({"state": "suspended"})
        self.message_post(body=_("Investor account <b>suspended</b>."))

    def action_activate(self):
        self.ensure_one()
        self.write({"state": "active"})
        self.message_post(body=_("Investor account <b>reactivated</b>."))

    def action_blacklist(self):
        self.ensure_one()
        self.write({"state": "blacklisted"})
        self.message_post(body=_("Investor account has been <b>blacklisted</b>."))

    def action_view_investments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Investments — %s") % self.display_name,
            "res_model": "alba.investment",
            "view_mode": "list,kanban,form",
            "domain": [("investor_id", "=", self.id)],
            "context": {"default_investor_id": self.id},
        }

    def action_view_statements(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Statements — %s") % self.display_name,
            "res_model": "alba.investment.statement",
            "view_mode": "list,form",
            "domain": [("investor_id", "=", self.id)],
            "context": {"default_investor_id": self.id},
        }

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("investor_number", _("New")) == _("New"):
                vals["investor_number"] = seq.next_by_code("alba.investor.seq") or _(
                    "New"
                )
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "[%s] %s"
                % (rec.investor_number, rec.partner_id.name or _("New Investor")),
            )
            for rec in self
        ]
