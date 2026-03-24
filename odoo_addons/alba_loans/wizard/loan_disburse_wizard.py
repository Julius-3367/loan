# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AlbaLoanDisburseWizard(models.TransientModel):
    _name = "alba.loan.disburse.wizard"
    _description = "Alba Capital — Loan Disbursement Wizard"

    # ── Application ───────────────────────────────────────────────────────────
    application_id = fields.Many2one(
        "alba.loan.application",
        string="Loan Application",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    application_number = fields.Char(
        string="Application Number",
        related="application_id.application_number",
        readonly=True,
    )
    customer_id = fields.Many2one(
        "alba.customer",
        string="Customer",
        related="application_id.customer_id",
        readonly=True,
    )
    loan_product_id = fields.Many2one(
        "alba.loan.product",
        string="Loan Product",
        related="application_id.loan_product_id",
        readonly=True,
    )

    # ── Disbursement Terms ────────────────────────────────────────────────────
    currency_id = fields.Many2one(
        "res.currency",
        related="application_id.currency_id",
        readonly=True,
    )
    approved_amount = fields.Monetary(
        string="Disbursement Amount",
        currency_field="currency_id",
        required=True,
        help="Amount to actually disburse. Defaults to the approved amount on the application.",
    )
    disbursement_date = fields.Date(
        string="Disbursement Date",
        required=True,
        default=fields.Date.today,
    )
    tenure_months = fields.Integer(
        string="Tenure (Months)",
        required=True,
        default=lambda self: self._default_tenure(),
    )
    repayment_frequency = fields.Selection(
        selection=[
            ("weekly", "Weekly"),
            ("fortnightly", "Fortnightly"),
            ("monthly", "Monthly"),
        ],
        string="Repayment Frequency",
        required=True,
        default=lambda self: self._default_frequency(),
    )
    interest_rate = fields.Float(
        string="Interest Rate (% p.m.)",
        digits=(5, 2),
        required=True,
        default=lambda self: self._default_interest_rate(),
        help="Monthly interest rate. Defaults to the loan product rate.",
    )
    interest_method = fields.Selection(
        selection=[
            ("flat_rate", "Flat Rate"),
            ("reducing_balance", "Reducing Balance"),
        ],
        string="Interest Method",
        required=True,
        default=lambda self: self._default_interest_method(),
    )

    # ── Journal ───────────────────────────────────────────────────────────────
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        required=True,
        domain="[('type', 'in', ['bank', 'cash'])]",
        help="Bank or Cash journal from which the loan amount will be paid out.",
    )

    # ── Schedule preview ──────────────────────────────────────────────────────
    generate_schedule = fields.Boolean(
        string="Auto-generate Repayment Schedule",
        default=True,
        help="If ticked, an amortisation schedule will be created immediately after disbursement.",
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = fields.Text(
        string="Disbursement Notes",
        help="Internal notes recorded on the loan and the application chatter.",
    )

    # ── Estimated totals (informational) ──────────────────────────────────────
    estimated_total_interest = fields.Monetary(
        string="Estimated Total Interest",
        currency_field="currency_id",
        compute="_compute_estimates",
    )
    estimated_total_repayable = fields.Monetary(
        string="Estimated Total Repayable",
        currency_field="currency_id",
        compute="_compute_estimates",
    )
    estimated_monthly_instalment = fields.Monetary(
        string="Estimated Monthly Instalment",
        currency_field="currency_id",
        compute="_compute_estimates",
    )

    # =========================================================================
    # Default helpers
    # =========================================================================

    def _default_tenure(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.tenure_months or 12
        return 12

    def _default_frequency(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.repayment_frequency or "monthly"
        return "monthly"

    def _default_interest_rate(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return app.loan_product_id.interest_rate if app.loan_product_id else 0.0
        return 0.0

    def _default_interest_method(self):
        ctx_app_id = self.env.context.get("default_application_id")
        if ctx_app_id:
            app = self.env["alba.loan.application"].browse(ctx_app_id)
            return (
                app.loan_product_id.interest_method
                if app.loan_product_id
                else "reducing_balance"
            )
        return "reducing_balance"

    # =========================================================================
    # Compute methods
    # =========================================================================

    @api.depends(
        "approved_amount",
        "tenure_months",
        "interest_rate",
        "interest_method",
        "loan_product_id",
    )
    def _compute_estimates(self):
        for rec in self:
            amount = rec.approved_amount or 0.0
            months = rec.tenure_months or 0
            rate = rec.interest_rate or 0.0
            method = rec.interest_method

            if amount <= 0 or months <= 0:
                rec.estimated_total_interest = 0.0
                rec.estimated_total_repayable = 0.0
                rec.estimated_monthly_instalment = 0.0
                continue

            if method == "flat_rate":
                total_interest = round(amount * (rate / 100) * months, 2)
                total_repayable = amount + total_interest
                monthly = round(total_repayable / months, 2)
            else:
                # Reducing balance — use annuity formula
                monthly_rate = rate / 100
                if monthly_rate == 0:
                    monthly = round(amount / months, 2)
                    total_interest = 0.0
                else:
                    monthly = round(
                        amount
                        * monthly_rate
                        * (1 + monthly_rate) ** months
                        / ((1 + monthly_rate) ** months - 1),
                        2,
                    )
                    total_interest = round(monthly * months - amount, 2)
                total_repayable = amount + total_interest

            rec.estimated_total_interest = total_interest
            rec.estimated_total_repayable = total_repayable
            rec.estimated_monthly_instalment = monthly

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains("approved_amount", "application_id")
    def _check_disbursement_amount(self):
        for rec in self:
            if rec.approved_amount <= 0:
                raise ValidationError(
                    _("Disbursement amount must be greater than zero.")
                )
            product = rec.application_id.loan_product_id
            if product:
                if rec.approved_amount < product.min_amount:
                    raise ValidationError(
                        _(
                            "Disbursement amount %s is below the minimum of %s "
                            "for product '%s'."
                        )
                        % (rec.approved_amount, product.min_amount, product.name)
                    )
                if rec.approved_amount > product.max_amount:
                    raise ValidationError(
                        _(
                            "Disbursement amount %s exceeds the maximum of %s "
                            "for product '%s'."
                        )
                        % (rec.approved_amount, product.max_amount, product.name)
                    )

    @api.constrains("tenure_months")
    def _check_tenure(self):
        for rec in self:
            if rec.tenure_months < 1:
                raise ValidationError(_("Tenure must be at least 1 month."))

    @api.constrains("interest_rate")
    def _check_interest_rate(self):
        for rec in self:
            if rec.interest_rate < 0:
                raise ValidationError(_("Interest rate cannot be negative."))

    # =========================================================================
    # Main disbursement action
    # =========================================================================

    def action_disburse(self):
        """
        Perform the full disbursement:
        1.  Validate the application is in a disbursable state.
        2.  Create the alba.loan record.
        3.  Post the disbursement accounting journal entry.
        4.  Optionally generate the repayment schedule.
        5.  Transition the application to 'disbursed' and link the new loan.
        6.  Return a form view of the newly created loan.
        """
        self.ensure_one()

        application = self.application_id
        disbursable_states = (
            "approved",
            "employer_verification",
            "guarantor_confirmation",
        )
        if application.state not in disbursable_states:
            raise UserError(
                _(
                    "Application %s is in state '%s' and cannot be disbursed. "
                    "It must be Approved, in Employer Verification, or "
                    "in Guarantor Confirmation."
                )
                % (application.application_number, application.state)
            )

        if application.loan_id:
            raise UserError(
                _("Application %s has already been disbursed as loan %s.")
                % (application.application_number, application.loan_id.loan_number)
            )

        # ── 1. Create alba.loan ───────────────────────────────────────────────
        loan_vals = {
            "application_id": application.id,
            "principal_amount": self.approved_amount,
            "interest_rate": self.interest_rate,
            "interest_method": self.interest_method,
            "tenure_months": self.tenure_months,
            "repayment_frequency": self.repayment_frequency,
            "disbursement_date": self.disbursement_date,
            "journal_id": self.journal_id.id,
            "state": "active",
            "notes": self.notes or "",
        }
        loan = self.env["alba.loan"].create(loan_vals)

        # ── 2. Post disbursement journal entry ───────────────────────────────
        loan.action_post_disbursement_entry()

        # ── 3. Generate repayment schedule ───────────────────────────────────
        if self.generate_schedule:
            loan.action_generate_schedule()

        # ── 4. Transition application → disbursed ────────────────────────────
        application.write(
            {
                "state": "disbursed",
                "approved_amount": self.approved_amount,
                "disbursed_date": fields.Datetime.now(),
                "disbursed_by": self.env.uid,
                "loan_id": loan.id,
            }
        )
        application.message_post(
            body=_(
                "Loan <b>%(loan_number)s</b> disbursed for "
                "<b>%(currency)s %(amount).2f</b> on %(date)s via %(journal)s. "
                "%(notes)s",
                loan_number=loan.loan_number,
                currency=self.currency_id.name,
                amount=self.approved_amount,
                date=self.disbursement_date,
                journal=self.journal_id.name,
                notes=self.notes or "",
            )
        )

        # ── 5. Return form view of the new loan ───────────────────────────────
        return {
            "type": "ir.actions.act_window",
            "name": _("Loan — %s") % loan.loan_number,
            "res_model": "alba.loan",
            "view_mode": "form",
            "res_id": loan.id,
            "target": "current",
        }
