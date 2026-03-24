# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaInterestAccrual(models.Model):
    _name = "alba.interest.accrual"
    _description = "Alba Capital Investment Interest Accrual"
    _inherit = ["mail.thread"]
    _rec_name = "display_name"
    _order = "accrual_date desc, id desc"

    # ── Display ───────────────────────────────────────────────────────────────
    display_name = fields.Char(
        string="Reference",
        compute="_compute_display_name",
        store=True,
    )

    # ── Investment Link ───────────────────────────────────────────────────────
    investment_id = fields.Many2one(
        "alba.investment",
        string="Investment",
        required=True,
        ondelete="cascade",
        tracking=True,
        index=True,
    )
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        related="investment_id.investor_id",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="investment_id.investor_id.partner_id",
        store=True,
        readonly=True,
    )

    # ── Period ────────────────────────────────────────────────────────────────
    accrual_date = fields.Date(
        string="Accrual Date",
        required=True,
        default=fields.Date.today,
        index=True,
        tracking=True,
    )
    period_start = fields.Date(
        string="Period Start",
        required=True,
    )
    period_end = fields.Date(
        string="Period End",
        required=True,
    )

    # ── Amounts ───────────────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="investment_id.currency_id",
        store=True,
        readonly=True,
    )
    opening_balance = fields.Monetary(
        string="Opening Balance",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Investment value at the start of the accrual period.",
    )
    interest_amount = fields.Monetary(
        string="Interest Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
        help="Compound interest accrued for this period.",
    )
    closing_balance = fields.Monetary(
        string="Closing Balance",
        currency_field="currency_id",
        compute="_compute_closing_balance",
        store=True,
        help="Opening balance + accrued interest.",
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("reversed", "Reversed"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    reversal_move_id = fields.Many2one(
        "account.move",
        string="Reversal Journal Entry",
        readonly=True,
        copy=False,
    )

    # ── Company ───────────────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="investment_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Char(string="Notes")
    reversal_reason = fields.Text(string="Reversal Reason")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "interest_amount_positive",
            "CHECK(interest_amount > 0)",
            "Interest amount must be greater than zero.",
        ),
        (
            "opening_balance_non_negative",
            "CHECK(opening_balance >= 0)",
            "Opening balance cannot be negative.",
        ),
        (
            "period_dates_check",
            "CHECK(period_end >= period_start)",
            "Period end date must be on or after period start date.",
        ),
    ]

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("investment_id", "accrual_date", "period_start", "period_end")
    def _compute_display_name(self):
        for rec in self:
            inv_num = rec.investment_id.investment_number if rec.investment_id else "?"
            period = ""
            if rec.period_start and rec.period_end:
                period = " (%s – %s)" % (
                    rec.period_start.strftime("%b %Y"),
                    rec.period_end.strftime("%b %Y"),
                )
            rec.display_name = "Accrual — %s%s" % (inv_num, period)

    @api.depends("opening_balance", "interest_amount")
    def _compute_closing_balance(self):
        for rec in self:
            rec.closing_balance = rec.opening_balance + rec.interest_amount

    # =========================================================================
    # Constraint methods
    # =========================================================================

    @api.constrains("period_start", "period_end")
    def _check_period_dates(self):
        for rec in self:
            if rec.period_start and rec.period_end:
                if rec.period_end < rec.period_start:
                    raise ValidationError(
                        _("Period end date must be on or after period start date.")
                    )

    @api.constrains("interest_amount")
    def _check_interest_amount(self):
        for rec in self:
            if rec.interest_amount <= 0:
                raise ValidationError(_("Interest amount must be greater than zero."))

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_post(self):
        """
        Post the interest accrual:
        1. Validate required accounting configuration on the investment.
        2. Create and post journal entry:
               DR  Interest Expense Account   (interest_amount)
               CR  Interest Payable Account   (interest_amount)
        3. Set state to 'posted'.
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Only draft accruals can be posted. '%s' is already %s.")
                    % (rec.display_name, rec.state)
                )

            investment = rec.investment_id

            # Validate accounting configuration
            if not investment.account_interest_expense_id:
                raise UserError(
                    _(
                        "Please configure the Interest Expense account on investment '%s' "
                        "before posting the accrual."
                    )
                    % investment.investment_number
                )
            if not investment.account_interest_payable_id:
                raise UserError(
                    _(
                        "Please configure the Interest Payable account on investment '%s' "
                        "before posting the accrual."
                    )
                    % investment.investment_number
                )

            journal = investment.journal_id
            if not journal:
                # Fall back to first general journal in the company
                journal = rec.env["account.journal"].search(
                    [
                        ("type", "=", "general"),
                        ("company_id", "=", rec.company_id.id),
                    ],
                    limit=1,
                )
            if not journal:
                raise UserError(
                    _(
                        "No General journal found for company '%s'. "
                        "Please create one or configure the Accrual Journal on investment '%s'."
                    )
                    % (rec.company_id.name, investment.investment_number)
                )

            move_vals = {
                "journal_id": journal.id,
                "date": rec.accrual_date,
                "ref": "ACCR/%s/%s"
                % (
                    investment.investment_number,
                    rec.accrual_date.strftime("%Y%m") if rec.accrual_date else "",
                ),
                "narration": _(
                    "Monthly compound interest accrual — %(investment)s — %(period)s",
                    investment=investment.investment_number,
                    period="%s to %s" % (rec.period_start, rec.period_end),
                ),
                "line_ids": [
                    # DR Interest Expense
                    (
                        0,
                        0,
                        {
                            "account_id": investment.account_interest_expense_id.id,
                            "name": _(
                                "Interest expense — %(inv)s — %(period)s",
                                inv=investment.investment_number,
                                period=rec.period_start.strftime("%b %Y")
                                if rec.period_start
                                else "",
                            ),
                            "debit": rec.interest_amount,
                            "credit": 0.0,
                            "partner_id": rec.partner_id.id,
                        },
                    ),
                    # CR Interest Payable
                    (
                        0,
                        0,
                        {
                            "account_id": investment.account_interest_payable_id.id,
                            "name": _(
                                "Interest payable — %(inv)s — %(period)s",
                                inv=investment.investment_number,
                                period=rec.period_start.strftime("%b %Y")
                                if rec.period_start
                                else "",
                            ),
                            "debit": 0.0,
                            "credit": rec.interest_amount,
                            "partner_id": rec.partner_id.id,
                        },
                    ),
                ],
            }
            move = rec.env["account.move"].create(move_vals)
            move.action_post()

            rec.write({"state": "posted", "move_id": move.id})
            rec.message_post(
                body=_(
                    "Accrual posted: <b>%(currency)s %(amount).2f</b>. "
                    "Journal entry: <b>%(move)s</b>.",
                    currency=rec.currency_id.name,
                    amount=rec.interest_amount,
                    move=move.name,
                )
            )

        return True

    def action_reverse(self):
        """Reverse a posted accrual and its journal entry."""
        self.ensure_one()
        if self.state != "posted":
            raise UserError(_("Only posted accruals can be reversed."))
        if not self.reversal_reason:
            raise UserError(
                _("Please provide a reversal reason before reversing this accrual.")
            )

        if self.move_id:
            reversal = self.move_id._reverse_moves(
                [
                    {
                        "date": fields.Date.today(),
                        "journal_id": self.move_id.journal_id.id,
                        "reason": self.reversal_reason,
                    }
                ]
            )
            reversal.action_post()
            self.write({"reversal_move_id": reversal.id})

        self.write({"state": "reversed"})
        self.message_post(
            body=_("Accrual <b>reversed</b>. Reason: %s") % self.reversal_reason
        )
        return True

    def action_reset_to_draft(self):
        """Reset a reversed accrual back to draft for correction."""
        self.ensure_one()
        if self.state != "reversed":
            raise UserError(_("Only reversed accruals can be reset to draft."))
        self.write({"state": "draft", "move_id": False, "reversal_move_id": False})
        self.message_post(body=_("Accrual reset to <b>Draft</b>."))
        return True
