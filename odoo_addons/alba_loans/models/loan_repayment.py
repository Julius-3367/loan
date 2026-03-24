# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaLoanRepayment(models.Model):
    _name = "alba.loan.repayment"
    _description = "Alba Capital Loan Repayment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "payment_reference"
    _order = "payment_date desc, id desc"

    # ── Identification ────────────────────────────────────────────────────────
    payment_reference = fields.Char(
        string="Payment Reference",
        copy=False,
        index=True,
        tracking=True,
        help="Unique reference for this payment (e.g. M-Pesa code, bank ref).",
    )
    django_payment_id = fields.Integer(
        string="Django Payment ID",
        index=True,
        copy=False,
        help="Primary key of the corresponding repayment record in the Django portal.",
    )

    # ── Loan Link ─────────────────────────────────────────────────────────────
    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="restrict",
        tracking=True,
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
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="loan_id.customer_id.partner_id",
        store=True,
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="loan_id.loan_product_id",
        store=True,
        readonly=True,
    )

    # ── Payment Details ───────────────────────────────────────────────────────
    payment_date = fields.Date(
        string="Payment Date",
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    amount_paid = fields.Monetary(
        string="Amount Paid",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )

    # ── Allocation ────────────────────────────────────────────────────────────
    principal_component = fields.Monetary(
        string="Principal Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    interest_component = fields.Monetary(
        string="Interest Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    fees_component = fields.Monetary(
        string="Fees Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    penalty_component = fields.Monetary(
        string="Penalty / Late Fee Component",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    total_allocated = fields.Monetary(
        string="Total Allocated",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
    )
    unallocated_amount = fields.Monetary(
        string="Unallocated Amount",
        currency_field="currency_id",
        compute="_compute_total_allocated",
        store=True,
        help="Difference between amount paid and total allocation across components.",
    )

    # ── Payment Method ────────────────────────────────────────────────────────
    payment_method = fields.Selection(
        selection=[
            ("mpesa", "M-Pesa"),
            ("bank_transfer", "Bank Transfer"),
            ("cash", "Cash"),
            ("cheque", "Cheque"),
            ("rtgs", "RTGS / EFT"),
        ],
        string="Payment Method",
        required=True,
        default="mpesa",
        tracking=True,
    )
    mpesa_transaction_id = fields.Char(
        string="M-Pesa Transaction ID",
        copy=False,
        index=True,
        tracking=True,
    )
    bank_transaction_id = fields.Char(
        string="Bank Transaction ID / Cheque No.",
        copy=False,
    )
    received_by = fields.Many2one(
        "res.users",
        string="Received By",
        default=lambda self: self.env.uid,
        tracking=True,
    )

    # ── Workflow State ────────────────────────────────────────────────────────
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
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ['bank', 'cash'])]",
        tracking=True,
        help="Bank or Cash journal into which this payment was received.",
    )

    # ── Currency / Company ────────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="loan_id.company_id",
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
    notes = fields.Text(string="Notes / Remarks")
    reversal_reason = fields.Text(string="Reversal Reason")

    # ── SQL Constraints ───────────────────────────────────────────────────────
    _sql_constraints = [
        (
            "amount_positive",
            "CHECK(amount_paid > 0)",
            "Payment amount must be greater than zero.",
        ),
        (
            "unique_mpesa_transaction",
            "UNIQUE(mpesa_transaction_id)",
            "A repayment with this M-Pesa transaction ID already exists.",
        ),
        (
            "unique_django_payment_id",
            "UNIQUE(django_payment_id)",
            "A repayment with this Django Payment ID already exists.",
        ),
    ]

    # =========================================================================
    # Computed Methods
    # =========================================================================

    @api.depends(
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
        "amount_paid",
    )
    def _compute_total_allocated(self):
        for rec in self:
            allocated = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            rec.total_allocated = allocated
            rec.unallocated_amount = max(rec.amount_paid - allocated, 0.0)

    # =========================================================================
    # Constraint Methods
    # =========================================================================

    @api.constrains(
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
    )
    def _check_components_non_negative(self):
        for rec in self:
            if any(
                val < 0
                for val in [
                    rec.principal_component,
                    rec.interest_component,
                    rec.fees_component,
                    rec.penalty_component,
                ]
            ):
                raise ValidationError(
                    _("Repayment component amounts cannot be negative.")
                )

    @api.constrains(
        "amount_paid",
        "principal_component",
        "interest_component",
        "fees_component",
        "penalty_component",
    )
    def _check_allocation_not_exceed_payment(self):
        for rec in self:
            allocated = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            if allocated > rec.amount_paid + 0.01:
                raise ValidationError(
                    _(
                        "Total allocated (%(allocated).2f) cannot exceed the amount paid (%(paid).2f).",
                        allocated=allocated,
                        paid=rec.amount_paid,
                    )
                )

    @api.constrains("mpesa_transaction_id")
    def _check_mpesa_transaction_unique(self):
        for rec in self:
            if not rec.mpesa_transaction_id:
                continue
            duplicate = self.search(
                [
                    ("mpesa_transaction_id", "=", rec.mpesa_transaction_id),
                    ("id", "!=", rec.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "M-Pesa transaction ID '%s' is already recorded on repayment %s.",
                        rec.mpesa_transaction_id,
                        duplicate.payment_reference,
                    )
                )

    # =========================================================================
    # Business Logic
    # =========================================================================

    def _auto_allocate_components(self):
        """
        Auto-allocate payment amount to components in priority order:
        1. Fees & penalties (oldest overdue first)
        2. Interest
        3. Principal
        Uses the linked repayment schedule to drive allocation.
        """
        self.ensure_one()
        remaining = self.amount_paid
        fees = 0.0
        penalty = 0.0
        interest = 0.0
        principal = 0.0

        # Pull overdue/pending schedule entries ordered by due_date asc
        schedule = self.env["alba.repayment.schedule"].search(
            [
                ("loan_id", "=", self.loan_id.id),
                ("balance_due", ">", 0),
            ],
            order="due_date asc",
        )

        for entry in schedule:
            if remaining <= 0:
                break
            # Interest first within each instalment
            interest_owed = entry.interest_due - entry.interest_paid
            if interest_owed > 0:
                pay_interest = min(remaining, interest_owed)
                interest += pay_interest
                remaining -= pay_interest
            # Then principal
            principal_owed = entry.principal_due - entry.principal_paid
            if principal_owed > 0 and remaining > 0:
                pay_principal = min(remaining, principal_owed)
                principal += pay_principal
                remaining -= pay_principal

        self.write(
            {
                "principal_component": round(principal, 2),
                "interest_component": round(interest, 2),
                "fees_component": round(fees, 2),
                "penalty_component": round(penalty, 2),
            }
        )

    def action_post(self):
        """
        Post the repayment:
        1. Auto-allocate components if not already set.
        2. Post accounting journal entry:
               DR  Bank / Cash Account       (amount_paid)
               CR  Loan Receivable           (principal_component)
               CR  Interest Income           (interest_component)
               CR  Fee Income                (fees_component)
               CR  Penalty Income            (penalty_component)
        3. Update the repayment schedule entries.
        4. Close the loan if fully repaid.
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Only draft repayments can be posted. '%s' is already %s.")
                    % (rec.payment_reference or rec.id, rec.state)
                )
            if not rec.loan_id:
                raise UserError(_("A loan must be linked before posting a repayment."))
            if rec.loan_id.state == "written_off":
                raise UserError(
                    _("Cannot post a repayment against a written-off loan.")
                )

            # Auto-allocate if components are all zero
            total_comp = (
                rec.principal_component
                + rec.interest_component
                + rec.fees_component
                + rec.penalty_component
            )
            if total_comp == 0.0:
                rec._auto_allocate_components()

            # Validate journal
            if not rec.journal_id:
                raise UserError(
                    _("Please select a Payment Journal (Bank or Cash) before posting.")
                )
            bank_account = rec.journal_id.default_account_id
            if not bank_account:
                raise UserError(
                    _("Journal '%s' has no default account configured.")
                    % rec.journal_id.name
                )

            product = rec.loan_product_id
            if not product.account_loan_receivable_id:
                raise UserError(
                    _("Please configure the Loan Receivable account on product '%s'.")
                    % product.name
                )

            # Build journal entry lines
            line_ids = [
                # DR Bank / Cash
                (
                    0,
                    0,
                    {
                        "account_id": bank_account.id,
                        "name": _("Repayment — %s")
                        % (rec.payment_reference or rec.loan_id.loan_number),
                        "debit": rec.amount_paid,
                        "credit": 0.0,
                        "partner_id": rec.partner_id.id,
                    },
                ),
            ]

            # CR Loan Receivable (principal)
            if rec.principal_component > 0:
                line_ids.append(
                    (
                        0,
                        0,
                        {
                            "account_id": product.account_loan_receivable_id.id,
                            "name": _("Principal repayment — %s")
                            % rec.loan_id.loan_number,
                            "debit": 0.0,
                            "credit": rec.principal_component,
                            "partner_id": rec.partner_id.id,
                        },
                    )
                )

            # CR Interest Income
            if rec.interest_component > 0:
                interest_account = product.account_interest_income_id
                if not interest_account:
                    raise UserError(
                        _(
                            "Please configure the Interest Income account on product '%s'."
                        )
                        % product.name
                    )
                line_ids.append(
                    (
                        0,
                        0,
                        {
                            "account_id": interest_account.id,
                            "name": _("Interest collected — %s")
                            % rec.loan_id.loan_number,
                            "debit": 0.0,
                            "credit": rec.interest_component,
                            "partner_id": rec.partner_id.id,
                        },
                    )
                )

            # CR Fee Income
            if rec.fees_component > 0:
                fee_account = product.account_fees_income_id
                if not fee_account:
                    raise UserError(
                        _("Please configure the Fee Income account on product '%s'.")
                        % product.name
                    )
                line_ids.append(
                    (
                        0,
                        0,
                        {
                            "account_id": fee_account.id,
                            "name": _("Fees collected — %s") % rec.loan_id.loan_number,
                            "debit": 0.0,
                            "credit": rec.fees_component,
                            "partner_id": rec.partner_id.id,
                        },
                    )
                )

            # CR Penalty Income (use fee account as fallback if no dedicated account)
            if rec.penalty_component > 0:
                penalty_account = (
                    product.account_fees_income_id or product.account_interest_income_id
                )
                if not penalty_account:
                    raise UserError(
                        _(
                            "Please configure the Fee Income account on product '%s' to post penalty income."
                        )
                        % product.name
                    )
                line_ids.append(
                    (
                        0,
                        0,
                        {
                            "account_id": penalty_account.id,
                            "name": _("Penalty collected — %s")
                            % rec.loan_id.loan_number,
                            "debit": 0.0,
                            "credit": rec.penalty_component,
                            "partner_id": rec.partner_id.id,
                        },
                    )
                )

            move_vals = {
                "journal_id": rec.journal_id.id,
                "date": rec.payment_date,
                "ref": f"RPMT/{rec.loan_id.loan_number}/{rec.payment_reference or rec.id}",
                "narration": _("Loan repayment — %s — %s")
                % (rec.loan_id.loan_number, rec.customer_id.display_name),
                "line_ids": line_ids,
            }
            move = rec.env["account.move"].create(move_vals)
            move.action_post()

            rec.write({"state": "posted", "move_id": move.id})

            # Update repayment schedule
            rec._update_schedule_entries()

            # Auto-close loan if outstanding balance is zero
            loan = rec.loan_id
            if loan.outstanding_balance <= 0.01 and loan.state == "active":
                loan.action_close()

            rec.message_post(
                body=_(
                    "Repayment of <b>%(currency)s %(amount).2f</b> posted. "
                    "Journal entry: <b>%(move)s</b>. "
                    "Principal: %(principal).2f | Interest: %(interest).2f | Fees: %(fees).2f",
                    currency=rec.currency_id.name,
                    amount=rec.amount_paid,
                    move=move.name,
                    principal=rec.principal_component,
                    interest=rec.interest_component,
                    fees=rec.fees_component,
                )
            )

        return True

    def _update_schedule_entries(self):
        """
        Mark schedule entries as paid/partial based on the posted repayment
        components.  Allocates principal and interest across the oldest
        unpaid/partial instalments first.
        """
        self.ensure_one()
        remaining_principal = self.principal_component
        remaining_interest = self.interest_component

        schedule = self.env["alba.repayment.schedule"].search(
            [
                ("loan_id", "=", self.loan_id.id),
                ("balance_due", ">", 0),
            ],
            order="due_date asc",
        )

        for entry in schedule:
            if remaining_principal <= 0 and remaining_interest <= 0:
                break

            interest_owed = entry.interest_due - entry.interest_paid
            principal_owed = entry.principal_due - entry.principal_paid

            interest_pay = min(remaining_interest, max(interest_owed, 0.0))
            principal_pay = min(remaining_principal, max(principal_owed, 0.0))

            if interest_pay == 0.0 and principal_pay == 0.0:
                continue

            new_interest_paid = round(entry.interest_paid + interest_pay, 2)
            new_principal_paid = round(entry.principal_paid + principal_pay, 2)

            entry.write(
                {
                    "interest_paid": new_interest_paid,
                    "principal_paid": new_principal_paid,
                }
            )
            # Recompute status
            entry._compute_status()

            remaining_interest -= interest_pay
            remaining_principal -= principal_pay

    def action_reverse(self):
        """Reverse a posted repayment and its journal entry."""
        self.ensure_one()
        if self.state != "posted":
            raise UserError(_("Only posted repayments can be reversed."))
        if not self.reversal_reason:
            raise UserError(_("Please provide a reversal reason before reversing."))

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
            body=_("Repayment <b>reversed</b>. Reason: %s") % self.reversal_reason
        )
        return True

    # =========================================================================
    # ORM Overrides
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("payment_reference"):
                vals["payment_reference"] = (
                    seq.next_by_code("alba.loan.repayment.seq") or "New"
                )
        return super().create(vals_list)

    def name_get(self):
        return [
            (
                rec.id,
                "%s — %s"
                % (
                    rec.payment_reference or str(rec.id),
                    rec.loan_id.loan_number if rec.loan_id else "",
                ),
            )
            for rec in self
        ]
