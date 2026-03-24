# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaLoan(models.Model):
    _name = "alba.loan"
    _description = "Alba Capital Active Loan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "loan_number"
    _order = "disbursement_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    loan_number = fields.Char(
        string="Loan Number",
        readonly=True,
        copy=False,
        index=True,
        default="New",
    )
    django_loan_id = fields.Integer(
        string="Django Loan ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding Loan record in the Django portal.",
    )

    # ── Application link ──────────────────────────────────────────────────────
    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )

    # ── Derived from application (stored for performance) ─────────────────────
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        store=True,
        index=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="application_id.loan_product_id",
        store=True,
        readonly=True,
    )

    # ── Loan Terms ────────────────────────────────────────────────────────────
    principal_amount = fields.Monetary(
        string="Principal Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    interest_rate = fields.Float(
        string="Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        tracking=True,
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default="reducing_balance",
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

    # ── Dates ─────────────────────────────────────────────────────────────────
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
        tracking=True,
    )
    maturity_date = fields.Date(
        string="Maturity Date",
        compute="_compute_maturity_date",
        store=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("closed", "Closed / Fully Repaid"),
            ("npl", "Non-Performing"),
            ("written_off", "Written Off"),
        ],
        string="Loan Status",
        default="active",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Financial Totals ──────────────────────────────────────────────────────
    total_repayable = fields.Monetary(
        string="Total Repayable",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
        help="Principal + all scheduled interest and fees.",
    )
    total_paid = fields.Monetary(
        string="Total Paid",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance",
        compute="_compute_financial_totals",
        store=True,
        currency_field="currency_id",
    )
    arrears_amount = fields.Monetary(
        string="Arrears Amount",
        compute="_compute_par",
        store=True,
        currency_field="currency_id",
        help="Sum of overdue but unpaid instalments.",
    )
    days_in_arrears = fields.Integer(
        string="Days in Arrears",
        compute="_compute_par",
        store=True,
        help="Number of days since the oldest overdue unpaid instalment.",
    )
    par_bucket = fields.Selection(
        selection=[
            ("current", "Current"),
            ("1_30", "1-30 Days"),
            ("31_60", "31-60 Days"),
            ("61_90", "61-90 Days"),
            ("91_180", "91-180 Days"),
            ("over_180", "Over 180 Days"),
        ],
        string="PAR Bucket",
        compute="_compute_par",
        store=True,
        tracking=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    repayment_schedule_ids = fields.One2many(
        "alba.repayment.schedule",
        "loan_id",
        string="Repayment Schedule",
    )
    repayment_ids = fields.One2many(
        "alba.loan.repayment",
        "loan_id",
        string="Repayment History",
    )
    move_ids = fields.One2many(
        "account.move",
        "ref",
        string="Journal Entries",
        domain="[('ref', 'like', loan_number)]",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
        help="Bank or Cash journal used when disbursing this loan.",
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
        store=True,
        readonly=True,
    )

    # ── Misc ──────────────────────────────────────────────────────────────────
    notes = fields.Text(string="Notes")
    schedule_generated = fields.Boolean(
        string="Schedule Generated",
        default=False,
        readonly=True,
        copy=False,
    )
    disbursement_move_id = fields.Many2one(
        "account.move",
        string="Disbursement Journal Entry",
        readonly=True,
        copy=False,
    )

    repayment_count = fields.Integer(
        string="Payments",
        compute="_compute_repayment_count",
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================
    _sql_constraints = [
        (
            "loan_number_unique",
            "UNIQUE(loan_number)",
            "A loan with this loan number already exists.",
        ),
        (
            "principal_positive",
            "CHECK(principal_amount > 0)",
            "Principal amount must be greater than zero.",
        ),
    ]

    # =========================================================================
    # Compute Methods
    # =========================================================================

    @api.depends("disbursement_date", "tenure_months")
    def _compute_maturity_date(self):
        for rec in self:
            if rec.disbursement_date and rec.tenure_months:
                d = rec.disbursement_date
                month = d.month + rec.tenure_months
                year = d.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                # Clamp day to last valid day of the target month
                import calendar

                last_day = calendar.monthrange(year, month)[1]
                rec.maturity_date = date(year, month, min(d.day, last_day))
            else:
                rec.maturity_date = False

    @api.depends(
        "principal_amount",
        "repayment_schedule_ids.total_due",
        "repayment_ids.state",
        "repayment_ids.amount_paid",
    )
    def _compute_financial_totals(self):
        for rec in self:
            schedule = rec.repayment_schedule_ids
            repayments = rec.repayment_ids.filtered(lambda r: r.state == "posted")
            rec.total_repayable = (
                sum(schedule.mapped("total_due")) or rec.principal_amount
            )
            rec.total_paid = sum(repayments.mapped("amount_paid"))
            rec.outstanding_balance = max(rec.total_repayable - rec.total_paid, 0.0)

    @api.depends(
        "repayment_schedule_ids.status",
        "repayment_schedule_ids.balance_due",
        "repayment_schedule_ids.due_date",
    )
    def _compute_par(self):
        today = fields.Date.today()
        for rec in self:
            overdue = rec.repayment_schedule_ids.filtered(
                lambda s: s.due_date < today and s.balance_due > 0
            )
            if not overdue:
                rec.arrears_amount = 0.0
                rec.days_in_arrears = 0
                rec.par_bucket = "current"
                continue

            rec.arrears_amount = sum(overdue.mapped("balance_due"))
            oldest_due = min(overdue.mapped("due_date"))
            rec.days_in_arrears = (today - oldest_due).days

            d = rec.days_in_arrears
            if d <= 30:
                rec.par_bucket = "1_30"
            elif d <= 60:
                rec.par_bucket = "31_60"
            elif d <= 90:
                rec.par_bucket = "61_90"
            elif d <= 180:
                rec.par_bucket = "91_180"
            else:
                rec.par_bucket = "over_180"

    def _compute_repayment_count(self):
        for rec in self:
            rec.repayment_count = len(rec.repayment_ids)

    # =========================================================================
    # ORM Overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("loan_number") or vals["loan_number"] == "New":
                vals["loan_number"] = seq.next_by_code("alba.loan.seq") or "New"
        return super().create(vals_list)

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_generate_schedule(self):
        """Generate the repayment schedule based on the loan product's method."""
        for rec in self:
            if rec.schedule_generated:
                raise UserError(
                    _(
                        "A repayment schedule has already been generated for loan %s. "
                        "Please delete the existing schedule before regenerating."
                    )
                    % rec.loan_number
                )
            if not rec.disbursement_date:
                raise UserError(
                    _("Please set a disbursement date before generating the schedule.")
                )

            product = rec.loan_product_id
            if not product:
                raise UserError(_("No loan product linked to this loan."))

            schedule_data = []
            if rec.interest_method == "flat_rate":
                monthly_interest = rec.principal_amount * (rec.interest_rate / 100)
                equal_principal = round(rec.principal_amount / rec.tenure_months, 2)
                balance = rec.principal_amount
                for i in range(rec.tenure_months):
                    principal = (
                        equal_principal
                        if i < rec.tenure_months - 1
                        else round(balance, 2)
                    )
                    schedule_data.append(
                        {
                            "installment_number": i + 1,
                            "opening_balance": round(balance, 2),
                            "principal_due": principal,
                            "interest_due": round(monthly_interest, 2),
                            "closing_balance": round(balance - principal, 2),
                        }
                    )
                    balance -= principal
            else:
                schedule_data = product.calculate_reducing_schedule(
                    rec.principal_amount, rec.tenure_months
                )

            # Build due dates
            schedule_vals = []
            for row in schedule_data:
                n = row["installment_number"]
                base = rec.disbursement_date
                import calendar

                month = base.month + n
                year = base.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                last_day = calendar.monthrange(year, month)[1]
                due = date(year, month, min(base.day, last_day))
                schedule_vals.append(
                    {
                        "loan_id": rec.id,
                        "installment_number": row["installment_number"],
                        "due_date": due,
                        "opening_balance": row["opening_balance"],
                        "principal_due": row["principal_due"],
                        "interest_due": row["interest_due"],
                        "closing_balance": row.get("closing_balance", 0.0),
                    }
                )

            self.env["alba.repayment.schedule"].create(schedule_vals)
            rec.write({"schedule_generated": True})
            rec.message_post(
                body=_(
                    "Repayment schedule generated: <b>%d</b> instalments from <b>%s</b> to <b>%s</b>."
                )
                % (
                    len(schedule_vals),
                    schedule_vals[0]["due_date"],
                    schedule_vals[-1]["due_date"],
                )
            )
        return True

    def action_post_disbursement_entry(self):
        """
        Post disbursement accounting journal entry:
            DR  Loan Receivable      (principal)
            CR  Bank / Cash Account  (principal)
        """
        self.ensure_one()
        if self.disbursement_move_id:
            raise UserError(
                _("A disbursement journal entry already exists for loan %s.")
                % self.loan_number
            )
        product = self.loan_product_id
        if not product.account_loan_receivable_id:
            raise UserError(
                _(
                    "Please configure the Loan Receivable account on the loan product '%s' "
                    "before posting the disbursement entry."
                )
                % product.name
            )
        if not self.journal_id:
            raise UserError(
                _("Please select a disbursement journal (Bank or Cash) on the loan.")
            )

        bank_account = self.journal_id.default_account_id
        if not bank_account:
            raise UserError(
                _("The selected journal '%s' has no default account configured.")
                % self.journal_id.name
            )

        move_vals = {
            "journal_id": self.journal_id.id,
            "date": self.disbursement_date,
            "ref": f"DISB/{self.loan_number}",
            "narration": _("Loan disbursement — %s — %s")
            % (self.loan_number, self.customer_id.display_name),
            "line_ids": [
                # DR Loan Receivable
                (
                    0,
                    0,
                    {
                        "account_id": product.account_loan_receivable_id.id,
                        "name": _("Loan Receivable — %s") % self.loan_number,
                        "debit": self.principal_amount,
                        "credit": 0.0,
                        "partner_id": self.customer_id.partner_id.id,
                    },
                ),
                # CR Bank / Cash
                (
                    0,
                    0,
                    {
                        "account_id": bank_account.id,
                        "name": _("Loan Disbursement — %s") % self.loan_number,
                        "debit": 0.0,
                        "credit": self.principal_amount,
                        "partner_id": self.customer_id.partner_id.id,
                    },
                ),
            ],
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.write({"disbursement_move_id": move.id})
        self.message_post(
            body=_("Disbursement journal entry <a href='#'>%s</a> posted for KES %s.")
            % (move.name, f"{self.principal_amount:,.2f}")
        )
        return move

    def action_mark_npl(self):
        self.ensure_one()
        self.write({"state": "npl"})
        self.message_post(body=_("Loan marked as <b>Non-Performing (NPL)</b>."))

    def action_write_off(self):
        self.ensure_one()
        self.write({"state": "written_off"})
        self.message_post(body=_("Loan has been <b>Written Off</b>."))

    def action_close(self):
        self.ensure_one()
        if self.outstanding_balance > 0.01:
            raise UserError(
                _("Cannot close loan %s — outstanding balance of %s remains.")
                % (self.loan_number, f"{self.outstanding_balance:,.2f}")
            )
        self.write({"state": "closed"})
        self.message_post(body=_("Loan marked as <b>Closed / Fully Repaid</b>."))

    def action_view_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayment Schedule — %s") % self.loan_number,
            "res_model": "alba.repayment.schedule",
            "view_mode": "list",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    def action_view_repayments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Repayments — %s") % self.loan_number,
            "res_model": "alba.loan.repayment",
            "view_mode": "list,form",
            "domain": [("loan_id", "=", self.id)],
            "context": {"default_loan_id": self.id},
        }

    # =========================================================================
    # Scheduled action (cron) — update PAR buckets daily
    # =========================================================================

    @api.model
    def action_update_par_buckets(self):
        """Called by daily cron to refresh PAR data on all active loans."""
        active_loans = self.search([("state", "=", "active")])
        active_loans._compute_par()
        # Auto-flag NPL for loans > 90 days in arrears
        for loan in active_loans:
            if loan.days_in_arrears > 90 and loan.state == "active":
                loan.action_mark_npl()

    # =========================================================================
    # Scheduled action (cron) — NPL monitor
    # =========================================================================

    @api.model
    def cron_flag_npl_loans(self):
        """
        Daily cron: move any active loan with days_in_arrears >= 90 to
        state='npl' and fire a Django webhook so the portal is updated.

        Loans already in 'npl', 'closed', or 'written_off' are skipped.
        """
        _logger = __import__("logging").getLogger(__name__)
        active_loans = self.search([("state", "=", "active")])
        active_loans._compute_par()

        npl_threshold = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("alba.loans.npl_threshold_days", "90")
        )

        newly_npl = self.browse()
        for loan in active_loans:
            if loan.days_in_arrears >= npl_threshold:
                loan.write({"state": "npl"})
                loan.message_post(
                    body=_(
                        "Loan automatically flagged as <b>Non-Performing</b> "
                        "by the daily NPL monitor cron — "
                        "<b>%d days</b> in arrears (threshold: %d)."
                    )
                    % (loan.days_in_arrears, npl_threshold)
                )
                newly_npl |= loan

        _logger.info("cron_flag_npl_loans: flagged %d loan(s) as NPL.", len(newly_npl))

        # Fire webhooks for newly flagged loans
        if newly_npl:
            self._fire_loan_status_webhooks(newly_npl, "loan.npl_flagged")

    # =========================================================================
    # Scheduled action (cron) — overdue payment alerts
    # =========================================================================

    @api.model
    def cron_send_overdue_alerts(self):
        """
        Daily cron: post chatter messages on loans that have instalments
        overdue by exactly 1, 3, 7, or 14 days, and log a sync event so
        the Django portal can notify the customer via email / SMS.

        Only active and NPL loans are checked.
        """
        import logging as _logging
        from datetime import timedelta

        _logger = _logging.getLogger(__name__)
        today = fields.Date.today()
        alert_days = [1, 3, 7, 14, 30]

        loans_alerted = 0
        for days_overdue in alert_days:
            target_date = today - timedelta(days=days_overdue)
            overdue_schedules = self.env["alba.repayment.schedule"].search(
                [
                    ("due_date", "=", target_date),
                    ("balance_due", ">", 0),
                    ("loan_id.state", "in", ("active", "npl")),
                ]
            )
            for schedule in overdue_schedules:
                loan = schedule.loan_id
                loan.message_post(
                    body=_(
                        "Overdue alert: instalment #<b>%d</b> "
                        "(KES <b>%.2f</b>) was due on <b>%s</b> "
                        "— now <b>%d day(s)</b> overdue."
                    )
                    % (
                        schedule.installment_number,
                        schedule.balance_due,
                        schedule.due_date,
                        days_overdue,
                    )
                )
                loans_alerted += 1

                # Push overdue event to Django
                self._fire_loan_status_webhooks(
                    loan,
                    "loan.instalment_overdue",
                    extra={
                        "days_overdue": days_overdue,
                        "instalment_number": schedule.installment_number,
                        "balance_due": float(schedule.balance_due),
                        "due_date": str(schedule.due_date),
                    },
                )

        _logger.info(
            "cron_send_overdue_alerts: sent %d overdue alert(s).", loans_alerted
        )

    # =========================================================================
    # Scheduled action (cron) — maturity reminders
    # =========================================================================

    @api.model
    def cron_send_maturity_reminders(self):
        """
        Weekly cron: notify officers (and push to Django) for loans
        maturing within the next 30 days so customers can be contacted
        about final repayment or renewal.
        """
        import logging as _logging
        from datetime import timedelta

        _logger = _logging.getLogger(__name__)
        today = fields.Date.today()
        window_end = today + timedelta(days=30)

        maturing = self.search(
            [
                ("state", "=", "active"),
                ("maturity_date", ">=", today),
                ("maturity_date", "<=", window_end),
                ("outstanding_balance", ">", 0),
            ]
        )
        for loan in maturing:
            days_left = (loan.maturity_date - today).days
            loan.message_post(
                body=_(
                    "Maturity reminder: loan matures on <b>%s</b> "
                    "(<b>%d day(s)</b> remaining).  "
                    "Outstanding balance: <b>KES %.2f</b>."
                )
                % (loan.maturity_date, days_left, loan.outstanding_balance)
            )

        _logger.info(
            "cron_send_maturity_reminders: %d loan(s) approaching maturity.",
            len(maturing),
        )
        if maturing:
            self._fire_loan_status_webhooks(maturing, "loan.maturing_soon")

    # =========================================================================
    # Scheduled action (cron) — auto-close fully repaid loans
    # =========================================================================

    @api.model
    def cron_close_repaid_loans(self):
        """
        Daily cron: close any active or NPL loan whose outstanding_balance
        has reached zero (i.e. the last repayment has been posted and all
        schedule entries are fully settled).
        """
        import logging as _logging

        _logger = _logging.getLogger(__name__)
        candidates = self.search([("state", "in", ("active", "npl"))])
        # Force recompute so we use fresh totals
        candidates._compute_financial_totals()

        closed = self.browse()
        for loan in candidates:
            if loan.outstanding_balance <= 0.01:  # 1-cent tolerance
                loan.write({"state": "closed"})
                loan.message_post(
                    body=_("Loan automatically <b>closed</b> — fully repaid.")
                )
                closed |= loan

        _logger.info("cron_close_repaid_loans: closed %d loan(s).", len(closed))
        if closed:
            self._fire_loan_status_webhooks(closed, "loan.closed")

    # =========================================================================
    # Scheduled action (cron) — push portfolio stats to Django
    # =========================================================================

    @api.model
    def cron_push_portfolio_stats(self):
        """
        Every-6-hours cron: compute aggregate portfolio metrics and push
        them to the Django portal via a webhook so dashboards stay current.

        Metrics pushed:
          • total_active_loans
          • total_disbursed (sum of principal_amount on active/npl loans)
          • total_outstanding (sum of outstanding_balance)
          • total_arrears
          • par_30  (outstanding balance of loans 1-30 days in arrears)
          • par_90  (outstanding balance of loans >90 days in arrears)
          • npl_count
        """
        import logging as _logging

        _logger = _logging.getLogger(__name__)

        active = self.search([("state", "in", ("active", "npl"))])
        if not active:
            return

        npl = active.filtered(lambda l: l.state == "npl")
        par_30 = active.filtered(lambda l: l.par_bucket in ("1_30",))
        par_90 = active.filtered(
            lambda l: l.par_bucket in ("61_90", "91_180", "over_180")
        )

        stats = {
            "total_active_loans": len(active.filtered(lambda l: l.state == "active")),
            "total_disbursed": float(sum(active.mapped("principal_amount"))),
            "total_outstanding": float(sum(active.mapped("outstanding_balance"))),
            "total_arrears": float(sum(active.mapped("arrears_amount"))),
            "par_30_balance": float(sum(par_30.mapped("outstanding_balance"))),
            "par_90_balance": float(sum(par_90.mapped("outstanding_balance"))),
            "npl_count": len(npl),
            "npl_balance": float(sum(npl.mapped("outstanding_balance"))),
        }

        api_key = (
            self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        )
        if api_key:
            api_key.send_webhook("portfolio.stats_updated", stats)
            _logger.info("cron_push_portfolio_stats: stats pushed to Django.")
        else:
            _logger.warning(
                "cron_push_portfolio_stats: no active API key found — skipping."
            )

    # =========================================================================
    # Private webhook helper
    # =========================================================================

    def _fire_loan_status_webhooks(self, loans, event_type, extra=None):
        """
        Fire a webhook for each loan in *loans* with the given *event_type*.

        Args:
            loans:      alba.loan recordset.
            event_type: Dot-separated event string, e.g. 'loan.npl_flagged'.
            extra:      Optional dict of extra fields merged into the payload.
        """
        api_key = (
            self.env["alba.api.key"].sudo().search([("is_active", "=", True)], limit=1)
        )
        if not api_key:
            return

        # Support both single records and recordsets
        loan_list = loans if hasattr(loans, "__iter__") else [loans]
        for loan in loan_list:
            payload = {
                "odoo_loan_id": loan.id,
                "loan_number": loan.loan_number or "",
                "django_loan_id": loan.django_loan_id or 0,
                "state": loan.state,
                "outstanding_balance": float(loan.outstanding_balance),
                "days_in_arrears": loan.days_in_arrears,
                "par_bucket": loan.par_bucket or "",
            }
            if extra:
                payload.update(extra)
            api_key.send_webhook(event_type, payload)
