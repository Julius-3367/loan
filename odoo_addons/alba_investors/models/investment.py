# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaInvestment(models.Model):
    _name = "alba.investment"
    _description = "Alba Capital Investment Account"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "investment_number"
    _order = "start_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    investment_number = fields.Char(
        string="Investment Number",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("New"),
    )

    # ── Investor Link ─────────────────────────────────────────────────────────
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="investor_id.partner_id",
        store=True,
        readonly=True,
    )

    # ── Investment Type ───────────────────────────────────────────────────────
    investment_type = fields.Selection(
        selection=[
            ("fixed_term", "Fixed Term"),
            ("open_ended", "Open Ended"),
        ],
        string="Investment Type",
        required=True,
        default="fixed_term",
        tracking=True,
    )

    # ── Terms ─────────────────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    interest_rate = fields.Float(
        string="Annual Interest Rate (%)",
        digits=(5, 4),
        required=True,
        tracking=True,
        help="Annual interest rate as a percentage e.g. 12.0000 for 12% per annum.",
    )
    compounding_frequency = fields.Selection(
        selection=[
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annually", "Annually"),
        ],
        string="Compounding Frequency",
        required=True,
        default="monthly",
        tracking=True,
    )

    # ── Dates ─────────────────────────────────────────────────────────────────
    start_date = fields.Date(
        string="Start Date",
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    maturity_date = fields.Date(
        string="Maturity Date",
        tracking=True,
        help="Required for Fixed Term investments. Leave blank for Open Ended.",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("matured", "Matured"),
            ("withdrawn", "Withdrawn"),
            ("suspended", "Suspended"),
        ],
        string="Status",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Financial Totals (computed) ───────────────────────────────────────────
    current_value = fields.Monetary(
        string="Current Value",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
        help="Principal + total interest accrued to date.",
    )
    total_interest_accrued = fields.Monetary(
        string="Total Interest Accrued",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
    )
    total_interest_paid = fields.Monetary(
        string="Total Interest Paid Out",
        currency_field="currency_id",
        compute="_compute_financials",
        store=True,
    )
    accrual_count = fields.Integer(
        string="Accruals",
        compute="_compute_accrual_count",
    )
    statement_count = fields.Integer(
        string="Statements",
        compute="_compute_statement_count",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    accrual_ids = fields.One2many(
        "alba.interest.accrual",
        "investment_id",
        string="Interest Accruals",
    )
    statement_ids = fields.One2many(
        "alba.investment.statement",
        "investment_id",
        string="Statements",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    account_interest_expense_id = fields.Many2one(
        "account.account",
        string="Interest Expense Account",
        tracking=True,
        domain="[('account_type', '=', 'expense')]",
        help="Account debited when interest is accrued (DR Interest Expense).",
    )
    account_interest_payable_id = fields.Many2one(
        "account.account",
        string="Interest Payable Account",
        tracking=True,
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        help="Account credited when interest is accrued (CR Interest Payable).",
    )
    account_investment_liability_id = fields.Many2one(
        "account.account",
        string="Investment Liability Account",
        tracking=True,
        domain="[('account_type', 'in', ['liability_current', 'liability_non_current'])]",
        help="Liability account representing funds received from investors.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Accrual Journal",
        domain="[('type', '=', 'general')]",
        help="General journal used for interest accrual entries.",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="investor_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "investment_number_unique",
            "UNIQUE(investment_number)",
            "An investment with this number already exists.",
        ),
        (
            "principal_positive",
            "CHECK(principal_amount > 0)",
            "Principal amount must be greater than zero.",
        ),
        (
            "interest_rate_non_negative",
            "CHECK(interest_rate >= 0)",
            "Interest rate cannot be negative.",
        ),
    ]

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends(
        "principal_amount",
        "accrual_ids",
        "accrual_ids.state",
        "accrual_ids.interest_amount",
    )
    def _compute_financials(self):
        for rec in self:
            posted_accruals = rec.accrual_ids.filtered(lambda a: a.state == "posted")
            total_accrued = sum(posted_accruals.mapped("interest_amount"))
            # total interest paid = accruals where payout has been made
            # (for now we track this separately; defaulting to 0 until payout model added)
            rec.total_interest_accrued = total_accrued
            rec.total_interest_paid = 0.0
            rec.current_value = rec.principal_amount + total_accrued

    def _compute_accrual_count(self):
        for rec in self:
            rec.accrual_count = len(rec.accrual_ids)

    def _compute_statement_count(self):
        for rec in self:
            rec.statement_count = len(rec.statement_ids)

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("investment_type", "maturity_date")
    def _check_maturity_date(self):
        for rec in self:
            if rec.investment_type == "fixed_term" and not rec.maturity_date:
                raise ValidationError(
                    _("A Maturity Date is required for Fixed Term investments.")
                )
            if (
                rec.maturity_date
                and rec.start_date
                and rec.maturity_date <= rec.start_date
            ):
                raise ValidationError(_("Maturity Date must be after the Start Date."))

    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if rec.interest_rate < 0:
                raise ValidationError(_("Interest rate cannot be negative."))
            if rec.interest_rate > 100:
                raise ValidationError(_("Interest rate cannot exceed 100%."))

    # =========================================================================
    # Compound Interest Engine
    # =========================================================================

    def _get_periods_per_year(self):
        """Return the number of compounding periods per year."""
        self.ensure_one()
        return {
            "monthly": 12,
            "quarterly": 4,
            "annually": 1,
        }.get(self.compounding_frequency, 12)

    def compute_compound_interest_for_period(self):
        """
        Calculate compound interest for one compounding period.

        Formula: I = P_current × ( (1 + r/n) - 1 )
        Where:
            P_current = current investment value (principal + previously accrued interest)
            r         = annual interest rate / 100
            n         = compounding periods per year
        Returns:
            float: interest amount for one period
        """
        self.ensure_one()
        n = self._get_periods_per_year()
        r = self.interest_rate / 100.0
        current = self.current_value
        period_interest = current * ((1 + r / n) - 1)
        return round(period_interest, 2)

    def action_accrue_monthly_interest(self):
        """
        Accrue one month's compound interest on this investment.
        Creates an alba.interest.accrual record and posts its journal entry.
        Returns the new accrual record.
        """
        self.ensure_one()
        if self.state != "active":
            raise UserError(
                _("Cannot accrue interest on investment %s — status is '%s'.")
                % (self.investment_number, self.state)
            )

        today = fields.Date.today()
        period_interest = self.compute_compound_interest_for_period()

        if period_interest <= 0:
            raise UserError(
                _("Computed interest for investment %s is zero or negative.")
                % self.investment_number
            )

        # Determine period start/end (previous month start → today)
        import calendar

        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
        last_day = calendar.monthrange(year, month)[1]
        from datetime import date

        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)

        accrual_vals = {
            "investment_id": self.id,
            "accrual_date": today,
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance": self.current_value,
            "interest_amount": period_interest,
        }
        accrual = self.env["alba.interest.accrual"].create(accrual_vals)
        accrual.action_post()

        self.message_post(
            body=_(
                "Monthly interest accrual posted: <b>%(currency)s %(amount).2f</b> "
                "for period %(start)s – %(end)s. New portfolio value: %(currency)s %(value).2f.",
                currency=self.currency_id.name,
                amount=period_interest,
                start=period_start,
                end=period_end,
                value=self.current_value,
            )
        )
        return accrual

    def action_mature(self):
        """Mark the investment as matured."""
        self.ensure_one()
        self.write({"state": "matured"})
        self.message_post(body=_("Investment marked as <b>Matured</b>."))

    def action_withdraw(self):
        """Mark the investment as withdrawn."""
        self.ensure_one()
        self.write({"state": "withdrawn"})
        self.message_post(body=_("Investment marked as <b>Withdrawn</b>."))

    def action_suspend(self):
        """Suspend the investment."""
        self.ensure_one()
        self.write({"state": "suspended"})
        self.message_post(body=_("Investment <b>suspended</b>."))

    def action_reactivate(self):
        """Reactivate a suspended investment."""
        self.ensure_one()
        self.write({"state": "active"})
        self.message_post(body=_("Investment <b>reactivated</b>."))

    # =========================================================================
    # Scheduled action (cron) — accrue interest on ALL active investments
    # =========================================================================

    @api.model
    def action_accrue_all_active_investments(self):
        """
        Called by the monthly cron on the 1st of each month.
        Accrues compound interest on every active investment.
        """
        active_investments = self.search([("state", "=", "active")])
        errors = []
        for inv in active_investments:
            try:
                inv.action_accrue_monthly_interest()
            except Exception as e:
                errors.append("Investment %s: %s" % (inv.investment_number, str(e)))

        if errors:
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                "alba.investment: Monthly accrual completed with errors:\n%s",
                "\n".join(errors),
            )

        return True

    # =========================================================================
    # ORM overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("investment_number", _("New")) == _("New"):
                vals["investment_number"] = seq.next_by_code(
                    "alba.investment.seq"
                ) or _("New")
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "[%s] %s" % (rec.investment_number, rec.investor_id.display_name),
            )
            for rec in self
        ]
