# -*- coding: utf-8 -*-
"""
alba_loans.wizard.mpesa_stk_push_wizard
=========================================
Transient wizard that lets a loan officer initiate an M-Pesa STK Push
payment prompt directly from a loan or repayment record inside Odoo.

Workflow
--------
1. Officer opens the wizard from the Loan form (button: "Request M-Pesa Payment").
2. Wizard pre-fills phone, amount, and account reference from the linked loan.
3. Officer adjusts values if needed and clicks "Send STK Push".
4. The wizard calls alba.mpesa.config.stk_push() and creates a pending
   alba.mpesa.transaction record.
5. Safaricom sends the payment prompt to the customer's handset.
6. The STK callback (handled by mpesa_callback.py) updates the transaction.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AlbaMpesaStkPushWizard(models.TransientModel):
    """
    Wizard: initiate an STK Push payment request for a loan instalment.

    The wizard is opened from:
      • The alba.loan form view  (button "Request M-Pesa Payment")
      • The alba.loan.repayment form view  (button "Send STK Push")

    It validates all inputs, calls the Daraja STK Push API, creates an
    alba.mpesa.transaction record, and returns a confirmation notification.
    """

    _name = "alba.mpesa.stk.push.wizard"
    _description = "M-Pesa STK Push — Request Payment Wizard"

    # =========================================================================
    # Fields
    # =========================================================================

    # ── Source loan ───────────────────────────────────────────────────────────

    loan_id = fields.Many2one(
        "alba.loan",
        string="Loan",
        required=True,
        ondelete="cascade",
        help="The loan for which payment is being requested.",
    )
    loan_number = fields.Char(
        string="Loan Number",
        related="loan_id.loan_number",
        readonly=True,
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance",
        related="loan_id.outstanding_balance",
        currency_field="currency_id",
        readonly=True,
    )

    # ── M-Pesa config ─────────────────────────────────────────────────────────

    config_id = fields.Many2one(
        "alba.mpesa.config",
        string="M-Pesa Configuration",
        required=True,
        help="The Daraja configuration to use for this STK Push.",
    )
    shortcode_display = fields.Char(
        string="Paybill / Till",
        compute="_compute_shortcode_display",
        help="Short code that will be shown to the customer.",
    )

    # ── Payment details ───────────────────────────────────────────────────────

    phone_number = fields.Char(
        string="Customer Phone Number",
        required=True,
        help=(
            "The customer's Safaricom number.  "
            "Accepted formats: 0712345678 / 254712345678 / +254712345678."
        ),
    )
    amount = fields.Monetary(
        string="Amount to Collect (KES)",
        currency_field="currency_id",
        required=True,
        help=(
            "Amount in KES to request from the customer.  "
            "Daraja requires a whole-number value — fractional shillings "
            "are rounded up automatically."
        ),
    )
    account_reference = fields.Char(
        string="Account Reference",
        required=True,
        help=(
            "Reference shown on the customer's phone and used to auto-match "
            "the payment to a loan.  Maximum 12 characters.  "
            "Defaults to the loan number."
        ),
    )
    transaction_desc = fields.Char(
        string="Transaction Description",
        required=True,
        default="Loan Repayment",
        help=(
            "Short description shown in the STK Push prompt on the customer's "
            "handset.  Maximum 13 characters."
        ),
    )

    # ── Currency / Company ────────────────────────────────────────────────────

    company_id = fields.Many2one(
        "res.company",
        related="loan_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="loan_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Result (populated after a successful push) ────────────────────────────

    checkout_request_id = fields.Char(
        string="Checkout Request ID",
        readonly=True,
        help="Populated after a successful STK Push submission.",
    )
    merchant_request_id = fields.Char(
        string="Merchant Request ID",
        readonly=True,
    )
    transaction_id = fields.Many2one(
        "alba.mpesa.transaction",
        string="Transaction Record",
        readonly=True,
        help="The alba.mpesa.transaction record created for this push.",
    )

    # =========================================================================
    # Defaults and on-change
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        """
        Pre-fill wizard fields from the active loan record in context.

        Expected context keys:
          default_loan_id  — ID of the alba.loan record that opened the wizard.
        """
        vals = super().default_get(fields_list)

        # Load the loan
        loan_id = vals.get("loan_id") or self.env.context.get("default_loan_id")
        if loan_id:
            loan = self.env["alba.loan"].browse(loan_id)
            if loan.exists():
                # Pre-fill phone from customer profile
                phone = ""
                customer = loan.customer_id
                if customer and customer.partner_id:
                    phone = (
                        customer.partner_id.mobile or customer.partner_id.phone or ""
                    )
                # If no phone on partner, try mpesa_number on customer model
                if not phone and hasattr(customer, "mpesa_number"):
                    phone = customer.mpesa_number or ""

                # Next instalment amount
                next_instalment = loan.repayment_schedule_ids.filtered(
                    lambda s: s.balance_due > 0
                )
                amount = (
                    next_instalment[0].total_due
                    if next_instalment
                    else loan.outstanding_balance
                )

                vals.update(
                    {
                        "phone_number": phone,
                        "amount": amount,
                        "account_reference": (loan.loan_number or "")[:12],
                        "transaction_desc": "Loan Repayment"[:13],
                    }
                )

        # Auto-select the active M-Pesa config for the current company
        if not vals.get("config_id"):
            config = self.env["alba.mpesa.config"].get_active_config()
            if config:
                vals["config_id"] = config.id

        return vals

    @api.depends("config_id")
    def _compute_shortcode_display(self):
        for rec in self:
            if rec.config_id:
                if rec.config_id.account_type == "till" and rec.config_id.till_number:
                    rec.shortcode_display = f"Till: {rec.config_id.till_number}"
                else:
                    rec.shortcode_display = f"Paybill: {rec.config_id.shortcode}"
            else:
                rec.shortcode_display = ""

    @api.onchange("loan_id")
    def _onchange_loan_id(self):
        """Refresh account_reference and amount when the loan changes."""
        if self.loan_id:
            self.account_reference = (self.loan_id.loan_number or "")[:12]
            next_inst = self.loan_id.repayment_schedule_ids.filtered(
                lambda s: s.balance_due > 0
            )
            if next_inst:
                self.amount = next_inst[0].total_due
            else:
                self.amount = self.loan_id.outstanding_balance

    # =========================================================================
    # Python constraints
    # =========================================================================

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("STK Push amount must be greater than zero."))

    @api.constrains("account_reference")
    def _check_account_reference(self):
        for rec in self:
            if rec.account_reference and len(rec.account_reference) > 12:
                raise ValidationError(
                    _(
                        "Account Reference must not exceed 12 characters "
                        "(Daraja limit).  Current length: %d."
                    )
                    % len(rec.account_reference)
                )

    @api.constrains("transaction_desc")
    def _check_transaction_desc(self):
        for rec in self:
            if rec.transaction_desc and len(rec.transaction_desc) > 13:
                raise ValidationError(
                    _(
                        "Transaction Description must not exceed 13 characters "
                        "(Daraja limit).  Current length: %d."
                    )
                    % len(rec.transaction_desc)
                )

    # =========================================================================
    # Action: Send STK Push
    # =========================================================================

    def action_send_stk_push(self):
        """
        Validate inputs, call the Daraja STK Push API, and create a pending
        ``alba.mpesa.transaction`` record.

        Returns:
            dict: An ``ir.actions.client`` notification action with the
                  result, or a form action to display the created transaction.

        Raises:
            UserError: On configuration or API errors.
        """
        self.ensure_one()

        # ── Pre-flight checks ────────────────────────────────────────────
        if not self.config_id:
            raise UserError(
                _(
                    "No M-Pesa configuration selected.  "
                    "Please configure a Daraja profile under Loans → M-Pesa → Configuration."
                )
            )
        if not self.config_id.is_active:
            raise UserError(
                _("The selected M-Pesa configuration '%s' is inactive.")
                % self.config_id.name
            )
        if self.loan_id.state not in ("active", "npl"):
            raise UserError(
                _(
                    "STK Push can only be initiated for active or non-performing loans.  "
                    "Loan %s is currently '%s'."
                )
                % (self.loan_id.loan_number, self.loan_id.state)
            )

        # ── Create pending transaction record BEFORE calling Daraja ──────
        # This ensures we have a record even if the API call fails or the
        # callback arrives before we finish processing the response.
        txn = self.env["alba.mpesa.transaction"].create(
            {
                "transaction_type": "stk_push",
                "status": "pending",
                "amount": self.amount,
                "phone_number": self.phone_number,
                "account_reference": self.account_reference,
                "description": self.transaction_desc,
                "loan_id": self.loan_id.id,
                "config_id": self.config_id.id,
                "raw_request": "{}",  # will be updated below
            }
        )

        # ── Call Daraja STK Push API ──────────────────────────────────────
        try:
            result = self.config_id.stk_push(
                phone_number=self.phone_number,
                amount=self.amount,
                account_reference=self.account_reference,
                transaction_desc=self.transaction_desc,
            )
        except UserError as exc:
            # Mark the transaction as failed and propagate the error
            txn.write(
                {
                    "status": "failed",
                    "failure_reason": str(exc),
                }
            )
            raise

        # ── Populate the transaction with the Daraja response ─────────────
        checkout_id = result.get("CheckoutRequestID", "")
        merchant_id = result.get("MerchantRequestID", "")
        response_code = str(result.get("ResponseCode", "-1"))

        if response_code != "0":
            txn.write(
                {
                    "status": "failed",
                    "result_code": response_code,
                    "result_desc": result.get("ResponseDescription", ""),
                    "failure_reason": result.get(
                        "ResponseDescription", "Unknown error"
                    ),
                    "raw_response": str(result),
                }
            )
            raise UserError(
                _("Daraja rejected the STK Push request.  ResponseCode: %s — %s")
                % (response_code, result.get("ResponseDescription", ""))
            )

        import json as _json

        txn.write(
            {
                "checkout_request_id": checkout_id,
                "merchant_request_id": merchant_id,
                "status": "pending",
                "result_code": response_code,
                "result_desc": result.get("CustomerMessage", "Request accepted"),
                "raw_response": _json.dumps(result),
            }
        )

        # Update wizard fields so the user sees the result
        self.write(
            {
                "checkout_request_id": checkout_id,
                "merchant_request_id": merchant_id,
                "transaction_id": txn.id,
            }
        )

        _logger.info(
            "STK Push sent: loan=%s phone=%s amount=%.2f checkout_id=%s",
            self.loan_id.loan_number,
            self.phone_number,
            self.amount,
            checkout_id,
        )

        # Post a chatter message on the loan
        self.loan_id.message_post(
            body=_(
                "STK Push initiated for <b>KES %(amount).2f</b> to "
                "<b>%(phone)s</b>.  "
                "CheckoutRequestID: <code>%(checkout)s</code>.  "
                "The customer should receive a payment prompt shortly."
            )
            % {
                "amount": self.amount,
                "phone": self.phone_number,
                "checkout": checkout_id,
            }
        )

        # Open the transaction record so the officer can track the outcome
        return {
            "type": "ir.actions.act_window",
            "name": _("STK Push Transaction"),
            "res_model": "alba.mpesa.transaction",
            "res_id": txn.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_cancel(self):
        """Close the wizard without sending anything."""
        return {"type": "ir.actions.act_window_close"}
