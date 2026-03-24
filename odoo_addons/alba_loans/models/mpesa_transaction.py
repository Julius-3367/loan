# -*- coding: utf-8 -*-
"""
alba.mpesa.transaction — M-Pesa transaction audit log for Alba Capital.

Every interaction with the Safaricom Daraja API — whether initiated by Odoo
(STK Push, B2C payout) or received as a callback (C2B confirmation, STK
callback) — is recorded here so that:

  • Operators have a complete, tamper-evident audit trail.
  • Payments can be reconciled to loan repayments from this list.
  • Duplicate callbacks from Safaricom are detected and ignored.
  • Failed or pending transactions can be monitored and retried.

Key methods
-----------
  AlbaMpesaTransaction.process_c2b_confirmation(data)   → record
  AlbaMpesaTransaction.process_stk_callback(data)       → record
  AlbaMpesaTransaction.process_b2c_result(data)         → record
  record.action_reconcile()                              → repayment form
  record.action_query_status()                           → notification
"""

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Selection list constants  (reused in views)
# ---------------------------------------------------------------------------

TRANSACTION_TYPES = [
    ("stk_push", "STK Push — Initiated"),
    ("stk_callback", "STK Push — Callback Received"),
    ("c2b", "C2B — Customer to Business"),
    ("b2c", "B2C — Business to Customer (Payout)"),
    ("b2c_result", "B2C — Result Callback"),
    ("query", "Status Query"),
]

TRANSACTION_STATUSES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled / Timeout"),
    ("reversed", "Reversed"),
]


class AlbaMpesaTransaction(models.Model):
    """
    Audit log for every M-Pesa / Daraja API interaction.

    Lifecycle
    ---------
    STK Push flow:
      1. Wizard creates a record with transaction_type='stk_push',
         status='pending', checkout_request_id populated.
      2. When Safaricom fires the callback, process_stk_callback() finds
         the record by checkout_request_id and sets status='completed'
         (or 'failed') plus mpesa_code.
      3. Operator (or cron) calls action_reconcile() to create the
         alba.loan.repayment and link it.

    C2B flow:
      1. Safaricom POSTs to the C2B confirmation URL.
      2. process_c2b_confirmation() creates a record with
         status='completed' and tries to auto-match the loan.
      3. Operator reconciles any unmatched records manually.

    B2C flow:
      1. Investor payout wizard calls config.b2c_payment() and records
         a 'b2c' / status='pending' transaction.
      2. Safaricom fires the result callback; process_b2c_result()
         updates status.
    """

    _name = "alba.mpesa.transaction"
    _description = "M-Pesa Transaction Log"
    _inherit = ["mail.thread"]
    _order = "create_date desc, id desc"
    _rec_name = "mpesa_code"

    # =========================================================================
    # Fields
    # =========================================================================

    # ── M-Pesa Identifiers ────────────────────────────────────────────────────

    mpesa_code = fields.Char(
        string="M-Pesa Code",
        index=True,
        copy=False,
        tracking=True,
        help=(
            "Safaricom transaction receipt number, e.g. QGH7YXXXXX.  "
            "Populated after the transaction completes."
        ),
    )
    checkout_request_id = fields.Char(
        string="Checkout Request ID",
        index=True,
        copy=False,
        help=(
            "Daraja CheckoutRequestID returned when an STK Push is initiated.  "
            "Used to match the subsequent STK callback."
        ),
    )
    merchant_request_id = fields.Char(
        string="Merchant Request ID",
        index=True,
        copy=False,
        help="Daraja MerchantRequestID returned alongside CheckoutRequestID.",
    )
    conversation_id = fields.Char(
        string="Conversation ID",
        index=True,
        copy=False,
        help="Daraja ConversationID returned for B2C transactions.",
    )
    originator_conversation_id = fields.Char(
        string="Originator Conversation ID",
        copy=False,
        help="Daraja OriginatorConversationID for B2C.",
    )

    # ── Transaction Details ───────────────────────────────────────────────────

    transaction_type = fields.Selection(
        selection=TRANSACTION_TYPES,
        string="Transaction Type",
        required=True,
        index=True,
        tracking=True,
    )
    status = fields.Selection(
        selection=TRANSACTION_STATUSES,
        string="Status",
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string="Amount (KES)",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    phone_number = fields.Char(
        string="Phone Number",
        index=True,
        tracking=True,
        help="Safaricom number in 254XXXXXXXXX format.",
    )
    account_reference = fields.Char(
        string="Account Reference",
        index=True,
        help="Loan number or repayment reference sent with the transaction.",
    )
    description = fields.Char(
        string="Transaction Description",
        help="Short description shown on the customer's phone (STK Push).",
    )
    sender_name = fields.Char(
        string="Sender Name",
        help="Customer name as reported by Safaricom (from C2B callback).",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────

    initiated_at = fields.Datetime(
        string="Initiated At",
        default=fields.Datetime.now,
        readonly=True,
        help="When Odoo sent the request to Daraja (or when the callback arrived).",
    )
    completed_at = fields.Datetime(
        string="Completed At",
        readonly=True,
        tracking=True,
        help="When the transaction was confirmed by Safaricom.",
    )

    # ── Daraja Result ─────────────────────────────────────────────────────────

    result_code = fields.Char(
        string="Result Code",
        help="Daraja ResultCode.  0 = success; non-zero = failure.",
    )
    result_desc = fields.Char(
        string="Result Description",
        help="Human-readable result description from Safaricom.",
    )
    failure_reason = fields.Text(
        string="Failure Reason",
        help="Populated when status = failed.  Combines result_desc and any extra detail.",
    )
    retry_count = fields.Integer(
        string="Query Retries",
        default=0,
        help="Number of times the status query has been retried by the cron job.",
    )

    # ── Raw Payloads ──────────────────────────────────────────────────────────

    raw_request = fields.Text(
        string="Raw Request Payload",
        help="JSON payload sent to the Daraja API (or received as a callback).",
    )
    raw_response = fields.Text(
        string="Raw Response / Callback",
        help="JSON response received from Daraja, or the raw callback body.",
    )

    # ── Links ─────────────────────────────────────────────────────────────────

    loan_id = fields.Many2one(
        "alba.loan",
        string="Linked Loan",
        index=True,
        ondelete="set null",
        tracking=True,
        help="Set manually or auto-matched via account_reference (loan number).",
    )
    repayment_id = fields.Many2one(
        "alba.loan.repayment",
        string="Linked Repayment",
        index=True,
        ondelete="set null",
        tracking=True,
        help="Populated after the transaction is reconciled to a repayment record.",
    )
    config_id = fields.Many2one(
        "alba.mpesa.config",
        string="M-Pesa Config",
        ondelete="restrict",
        help="The Daraja configuration record used for this transaction.",
    )
    investor_id = fields.Many2one(
        "alba.investor",
        string="Investor",
        index=True,
        ondelete="set null",
        help="Populated for B2C payouts to investors.",
    )

    # ── Currency / Company ────────────────────────────────────────────────────

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    # ── Computed helpers ──────────────────────────────────────────────────────

    is_reconciled = fields.Boolean(
        string="Reconciled",
        compute="_compute_is_reconciled",
        store=True,
        help="True when this transaction has been linked to a repayment record.",
    )
    needs_attention = fields.Boolean(
        string="Needs Attention",
        compute="_compute_needs_attention",
        store=True,
        help=(
            "True for completed C2B / STK transactions that are not yet "
            "reconciled to a repayment or loan."
        ),
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================

    _sql_constraints = [
        (
            "mpesa_code_unique",
            "UNIQUE(mpesa_code)",
            "A transaction with this M-Pesa code already exists.",
        ),
        (
            "checkout_request_id_unique",
            "UNIQUE(checkout_request_id)",
            "A transaction with this Checkout Request ID already exists.",
        ),
        (
            "conversation_id_unique",
            "UNIQUE(conversation_id)",
            "A transaction with this Conversation ID already exists.",
        ),
    ]

    # =========================================================================
    # Python-level constraints
    # =========================================================================

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(
                    _("Transaction amount must be greater than zero.")
                )

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("repayment_id")
    def _compute_is_reconciled(self):
        for rec in self:
            rec.is_reconciled = bool(rec.repayment_id)

    @api.depends("status", "transaction_type", "repayment_id", "loan_id")
    def _compute_needs_attention(self):
        inbound_types = {"stk_callback", "c2b"}
        for rec in self:
            rec.needs_attention = (
                rec.status == "completed"
                and rec.transaction_type in inbound_types
                and not rec.repayment_id
            )

    # =========================================================================
    # ORM overrides
    # =========================================================================

    def name_get(self):
        result = []
        for rec in self:
            name = rec.mpesa_code or rec.checkout_request_id or f"TXN#{rec.id}"
            result.append((rec.id, name))
        return result

    # =========================================================================
    # Business Logic
    # =========================================================================

    def action_reconcile(self):
        """
        Create an ``alba.loan.repayment`` draft from this completed M-Pesa
        transaction and link the two records together.

        Raises:
            UserError: When the transaction is not completed, is already
                       reconciled, or no loan is linked.
        """
        self.ensure_one()
        if self.status != "completed":
            raise UserError(
                _("Only completed transactions can be reconciled.  Current status: %s.")
                % self.status
            )
        if self.repayment_id:
            raise UserError(
                _("Transaction %s is already reconciled to repayment %s.")
                % (self.mpesa_code or self.id, self.repayment_id.payment_reference)
            )
        if not self.loan_id:
            raise UserError(
                _(
                    "Please link a loan to this transaction before reconciling.  "
                    "Use the 'Linked Loan' field or run auto-match."
                )
            )

        payment_date = (
            self.completed_at.date() if self.completed_at else fields.Date.today()
        )
        repayment = self.env["alba.loan.repayment"].create(
            {
                "loan_id": self.loan_id.id,
                "payment_date": payment_date,
                "amount_paid": self.amount,
                "payment_method": "mpesa",
                "mpesa_transaction_id": self.mpesa_code,
                "payment_reference": self.mpesa_code or f"MPESA-{self.id}",
                "state": "draft",
                "notes": _("Auto-created from M-Pesa transaction %s (phone: %s).")
                % (self.mpesa_code or self.id, self.phone_number or "—"),
            }
        )
        self.write({"repayment_id": repayment.id})
        self.message_post(
            body=_(
                "Reconciled to repayment <b>%s</b> (draft).  "
                "Open the repayment to review allocation and post it."
            )
            % repayment.payment_reference
        )
        _logger.info(
            "M-Pesa txn %s reconciled → repayment id=%d.",
            self.mpesa_code,
            repayment.id,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "alba.loan.repayment",
            "res_id": repayment.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_query_status(self):
        """
        Query Safaricom for the current status of an STK Push transaction.

        Only applicable to records with transaction_type in ('stk_push',
        'stk_callback') and status 'pending'.  Calls
        config.query_stk_status() and updates the record in-place.
        """
        self.ensure_one()
        if self.transaction_type not in ("stk_push", "stk_callback"):
            raise UserError(
                _("Status query is only available for STK Push transactions.")
            )
        if not self.checkout_request_id:
            raise UserError(_("No Checkout Request ID is set on this transaction."))
        if not self.config_id:
            raise UserError(_("No M-Pesa configuration is linked to this transaction."))

        try:
            result = self.config_id.query_stk_status(self.checkout_request_id)
        except UserError as exc:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Query Failed"),
                    "message": str(exc),
                    "type": "danger",
                    "sticky": True,
                },
            }

        result_code = str(result.get("ResultCode", "-1"))
        result_desc = result.get("ResultDesc", "")

        new_status = self.status
        if result_code == "0":
            new_status = "completed"
        elif result_code in ("1032", "1037"):
            # 1032 = cancelled by user, 1037 = timeout
            new_status = "cancelled"
        elif result_code != "0":
            new_status = "failed"

        self.write(
            {
                "status": new_status,
                "result_code": result_code,
                "result_desc": result_desc,
                "retry_count": self.retry_count + 1,
                "raw_response": json.dumps(result),
                "completed_at": fields.Datetime.now()
                if new_status == "completed"
                else self.completed_at,
            }
        )
        self.message_post(
            body=_(
                "STK status queried.  ResultCode: <b>%s</b> — %s.  "
                "New status: <b>%s</b>."
            )
            % (result_code, result_desc, new_status)
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("STK Status Updated"),
                "message": _("ResultCode %s: %s.  Status → %s.")
                % (result_code, result_desc, new_status),
                "type": "success" if new_status == "completed" else "warning",
                "sticky": False,
            },
        }

    def action_auto_match_loan(self):
        """
        Attempt to auto-match this transaction to a loan by comparing
        ``account_reference`` against ``alba.loan.loan_number``.

        Updates ``loan_id`` if a unique match is found.
        """
        self.ensure_one()
        if self.loan_id:
            raise UserError(_("A loan is already linked to this transaction."))
        if not self.account_reference:
            raise UserError(
                _(
                    "No account reference is set on this transaction.  "
                    "Cannot auto-match."
                )
            )

        loan = self.env["alba.loan"].search(
            [("loan_number", "=", self.account_reference.strip())],
            limit=1,
        )
        if loan:
            self.write({"loan_id": loan.id})
            self.message_post(
                body=_("Auto-matched to loan <b>%s</b> via account reference.")
                % loan.loan_number
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Loan Matched"),
                    "message": _("Linked to loan %s.") % loan.loan_number,
                    "type": "success",
                    "sticky": False,
                },
            }
        else:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Match Found"),
                    "message": _(
                        "No active loan found with number '%s'.  "
                        "Please link the loan manually."
                    )
                    % self.account_reference,
                    "type": "warning",
                    "sticky": True,
                },
            }

    # =========================================================================
    # Class-level processing methods  (called from the Daraja callback controller)
    # =========================================================================

    @api.model
    def process_c2b_confirmation(self, data: dict):
        """
        Process an incoming Safaricom C2B confirmation payload and create
        (or deduplicate) the transaction record.

        Expected Daraja C2B confirmation keys:
          TransID, TransAmount, MSISDN, BillRefNumber, TransTime,
          BusinessShortCode, FirstName, MiddleName, LastName

        Args:
            data (dict): Parsed JSON body from the C2B confirmation POST.

        Returns:
            alba.mpesa.transaction: The created or existing record.
        """
        mpesa_code = (data.get("TransID") or "").strip()
        amount = float(data.get("TransAmount") or 0)
        phone = str(data.get("MSISDN") or "").strip()
        account_ref = str(data.get("BillRefNumber") or "").strip()
        first_name = str(data.get("FirstName") or "").strip()
        middle_name = str(data.get("MiddleName") or "").strip()
        last_name = str(data.get("LastName") or "").strip()
        sender_name = " ".join(filter(None, [first_name, middle_name, last_name]))

        # ── Deduplicate ────────────────────────────────────────────────────
        if mpesa_code:
            existing = self.sudo().search([("mpesa_code", "=", mpesa_code)], limit=1)
            if existing:
                _logger.info(
                    "C2B confirmation duplicate ignored: mpesa_code=%s", mpesa_code
                )
                return existing

        # ── Create transaction record ──────────────────────────────────────
        txn = self.sudo().create(
            {
                "mpesa_code": mpesa_code or False,
                "transaction_type": "c2b",
                "status": "completed",
                "amount": amount,
                "phone_number": phone,
                "account_reference": account_ref,
                "sender_name": sender_name,
                "description": f"C2B payment from {sender_name or phone}",
                "raw_response": json.dumps(data),
                "result_code": "0",
                "result_desc": "C2B confirmation received",
                "completed_at": fields.Datetime.now(),
            }
        )

        # ── Auto-match loan by account reference ──────────────────────────
        if account_ref:
            loan = (
                self.env["alba.loan"]
                .sudo()
                .search([("loan_number", "=", account_ref)], limit=1)
            )
            if loan:
                txn.write({"loan_id": loan.id})
                _logger.info(
                    "C2B txn %s auto-matched to loan %s.",
                    mpesa_code,
                    loan.loan_number,
                )
            else:
                _logger.warning(
                    "C2B txn %s: no loan found for account_reference '%s'.",
                    mpesa_code,
                    account_ref,
                )

        _logger.info(
            "C2B confirmation processed: code=%s amount=%.2f phone=%s ref=%s",
            mpesa_code,
            amount,
            phone,
            account_ref,
        )
        return txn

    @api.model
    def process_stk_callback(self, data: dict):
        """
        Process an incoming Safaricom STK Push callback.

        Expected structure::

            {
                "Body": {
                    "stkCallback": {
                        "MerchantRequestID": "...",
                        "CheckoutRequestID": "ws_CO_...",
                        "ResultCode": 0,
                        "ResultDesc": "The service request is processed successfully.",
                        "CallbackMetadata": {
                            "Item": [
                                {"Name": "Amount",               "Value": 100.00},
                                {"Name": "MpesaReceiptNumber",   "Value": "QGH7Y..."},
                                {"Name": "TransactionDate",      "Value": 20240115123456},
                                {"Name": "PhoneNumber",          "Value": 254712345678}
                            ]
                        }
                    }
                }
            }

        Args:
            data (dict): Parsed JSON callback body.

        Returns:
            alba.mpesa.transaction: Updated record, or empty recordset when no
                                    matching pending transaction is found.
        """
        callback = data.get("Body", {}).get("stkCallback", {})
        checkout_id = (callback.get("CheckoutRequestID") or "").strip()
        merchant_id = (callback.get("MerchantRequestID") or "").strip()
        result_code = str(callback.get("ResultCode", "-1"))
        result_desc = (callback.get("ResultDesc") or "").strip()

        # ── Find the pending STK Push record ──────────────────────────────
        txn = self.sudo().search([("checkout_request_id", "=", checkout_id)], limit=1)
        if not txn:
            _logger.warning(
                "STK callback for unknown CheckoutRequestID '%s' — creating orphan record.",
                checkout_id,
            )
            # Create an orphan record so the data is not lost
            txn = self.sudo().create(
                {
                    "checkout_request_id": checkout_id or False,
                    "merchant_request_id": merchant_id or False,
                    "transaction_type": "stk_callback",
                    "status": "pending",
                    "amount": 0.0,
                    "raw_response": json.dumps(data),
                }
            )

        update_vals = {
            "result_code": result_code,
            "result_desc": result_desc,
            "raw_response": json.dumps(data),
            "transaction_type": "stk_callback",
        }

        if result_code == "0":
            # Extract CallbackMetadata items into a dict
            items = callback.get("CallbackMetadata", {}).get("Item", [])
            meta = {item.get("Name"): item.get("Value") for item in items}

            mpesa_code = str(meta.get("MpesaReceiptNumber") or "").strip()
            amount = float(meta.get("Amount") or txn.amount)
            phone = str(meta.get("PhoneNumber") or txn.phone_number or "").strip()

            update_vals.update(
                {
                    "status": "completed",
                    "mpesa_code": mpesa_code or False,
                    "amount": amount,
                    "phone_number": phone or txn.phone_number,
                    "completed_at": fields.Datetime.now(),
                }
            )
            _logger.info(
                "STK callback success: checkout_id=%s mpesa_code=%s amount=%.2f",
                checkout_id,
                mpesa_code,
                amount,
            )
        elif result_code in ("1032", "1037"):
            update_vals["status"] = "cancelled"
            update_vals["failure_reason"] = result_desc
            _logger.info(
                "STK callback cancelled by user: checkout_id=%s code=%s",
                checkout_id,
                result_code,
            )
        else:
            update_vals["status"] = "failed"
            update_vals["failure_reason"] = f"ResultCode {result_code}: {result_desc}"
            _logger.warning(
                "STK callback failed: checkout_id=%s code=%s desc=%s",
                checkout_id,
                result_code,
                result_desc,
            )

        txn.write(update_vals)

        # Auto-match loan if account_reference is set but loan_id is not
        if not txn.loan_id and txn.account_reference:
            loan = (
                self.env["alba.loan"]
                .sudo()
                .search([("loan_number", "=", txn.account_reference.strip())], limit=1)
            )
            if loan:
                txn.write({"loan_id": loan.id})

        return txn

    @api.model
    def process_b2c_result(self, data: dict):
        """
        Process an incoming Safaricom B2C result callback.

        Expected structure::

            {
                "Result": {
                    "ResultType": 0,
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "OriginatorConversationID": "...",
                    "ConversationID": "...",
                    "TransactionID": "QGH7YXXXXX",
                    "ResultParameters": {
                        "ResultParameter": [...]
                    }
                }
            }

        Args:
            data (dict): Parsed JSON callback body.

        Returns:
            alba.mpesa.transaction: Updated record, or empty recordset.
        """
        result = data.get("Result", {})
        conversation_id = (result.get("ConversationID") or "").strip()
        originator_id = (result.get("OriginatorConversationID") or "").strip()
        result_code = str(result.get("ResultCode", "-1"))
        result_desc = (result.get("ResultDesc") or "").strip()
        mpesa_code = (result.get("TransactionID") or "").strip()

        # Find the pending B2C record
        txn = self.sudo().search(
            [
                "|",
                ("conversation_id", "=", conversation_id),
                ("originator_conversation_id", "=", originator_id),
            ],
            limit=1,
        )
        if not txn:
            _logger.warning(
                "B2C result for unknown ConversationID '%s' / OriginatorID '%s'.",
                conversation_id,
                originator_id,
            )
            return self.browse()

        update_vals = {
            "result_code": result_code,
            "result_desc": result_desc,
            "raw_response": json.dumps(data),
            "transaction_type": "b2c_result",
        }

        if result_code == "0":
            # Extract result parameters
            params = result.get("ResultParameters", {}).get("ResultParameter", [])
            param_dict = {p.get("Key"): p.get("Value") for p in params}
            amount = float(param_dict.get("TransactionAmount") or txn.amount)

            update_vals.update(
                {
                    "status": "completed",
                    "mpesa_code": mpesa_code or False,
                    "amount": amount,
                    "completed_at": fields.Datetime.now(),
                }
            )
            _logger.info(
                "B2C result success: conversation_id=%s mpesa_code=%s",
                conversation_id,
                mpesa_code,
            )
        else:
            update_vals["status"] = "failed"
            update_vals["failure_reason"] = f"ResultCode {result_code}: {result_desc}"
            _logger.warning(
                "B2C result failed: conversation_id=%s code=%s desc=%s",
                conversation_id,
                result_code,
                result_desc,
            )

        txn.write(update_vals)
        return txn

    # =========================================================================
    # Scheduled action  (cron)
    # =========================================================================

    @api.model
    def cron_query_pending_stk_transactions(self):
        """
        Scheduled action: query Safaricom for all STK Push transactions that
        are still in 'pending' state and have a checkout_request_id.

        Called by a daily/hourly cron job.  Records that exceed the
        configured max_stk_retries on their linked config are marked
        'cancelled'.
        """
        pending = self.sudo().search(
            [
                ("status", "=", "pending"),
                ("transaction_type", "in", ("stk_push", "stk_callback")),
                ("checkout_request_id", "!=", False),
            ]
        )
        _logger.info(
            "cron_query_pending_stk_transactions: found %d pending records.",
            len(pending),
        )
        for txn in pending:
            config = txn.config_id
            if not config:
                _logger.warning("Pending STK txn %s has no config — skipping.", txn.id)
                continue

            max_retries = config.max_stk_retries or 3
            if txn.retry_count >= max_retries:
                txn.write(
                    {
                        "status": "cancelled",
                        "failure_reason": _("Marked cancelled after %d query retries.")
                        % txn.retry_count,
                    }
                )
                _logger.info(
                    "STK txn %s cancelled after %d retries.",
                    txn.checkout_request_id,
                    txn.retry_count,
                )
                continue

            try:
                result = config.query_stk_status(txn.checkout_request_id)
                result_code = str(result.get("ResultCode", "-1"))
                result_desc = result.get("ResultDesc", "")

                if result_code == "0":
                    txn.write(
                        {
                            "status": "completed",
                            "result_code": result_code,
                            "result_desc": result_desc,
                            "completed_at": fields.Datetime.now(),
                            "retry_count": txn.retry_count + 1,
                            "raw_response": json.dumps(result),
                        }
                    )
                elif result_code in ("1032", "1037"):
                    txn.write(
                        {
                            "status": "cancelled",
                            "result_code": result_code,
                            "result_desc": result_desc,
                            "failure_reason": result_desc,
                            "retry_count": txn.retry_count + 1,
                        }
                    )
                else:
                    txn.write(
                        {
                            "retry_count": txn.retry_count + 1,
                            "result_code": result_code,
                            "result_desc": result_desc,
                        }
                    )
            except Exception as exc:
                _logger.warning(
                    "STK status query failed for txn %s: %s",
                    txn.checkout_request_id,
                    exc,
                )
                txn.write({"retry_count": txn.retry_count + 1})

    @api.model
    def cron_auto_reconcile(self):
        """
        Hourly cron: for every completed, unreconciled inbound M-Pesa
        transaction that has a loan linked (or an account_reference that
        matches a loan number), automatically create a draft repayment
        and link it.

        Only creates the repayment — it does NOT post it.  An officer
        must open the repayment, review the allocation, and click Post.
        This prevents accidental double-posting while still reducing
        manual reconciliation work.
        """
        _logger.info("cron_auto_reconcile: starting auto-reconciliation pass.")

        unreconciled = self.sudo().search(
            [
                ("status", "=", "completed"),
                ("transaction_type", "in", ("c2b", "stk_callback")),
                ("repayment_id", "=", False),
                ("mpesa_code", "!=", False),
            ]
        )

        reconciled_count = 0
        for txn in unreconciled:
            # Ensure a loan is linked — try auto-match first if missing
            if not txn.loan_id and txn.account_reference:
                loan = (
                    self.env["alba.loan"]
                    .sudo()
                    .search(
                        [("loan_number", "=", txn.account_reference.strip())],
                        limit=1,
                    )
                )
                if loan:
                    txn.write({"loan_id": loan.id})

            if not txn.loan_id:
                _logger.debug(
                    "cron_auto_reconcile: txn %s has no matched loan — skipping.",
                    txn.mpesa_code,
                )
                continue

            # Skip loans in terminal states
            if txn.loan_id.state in ("closed", "written_off"):
                _logger.debug(
                    "cron_auto_reconcile: loan %s is %s — skipping txn %s.",
                    txn.loan_id.loan_number,
                    txn.loan_id.state,
                    txn.mpesa_code,
                )
                continue

            # Guard against duplicate mpesa_transaction_id on repayments
            existing_repayment = (
                self.env["alba.loan.repayment"]
                .sudo()
                .search(
                    [("mpesa_transaction_id", "=", txn.mpesa_code)],
                    limit=1,
                )
            )
            if existing_repayment:
                txn.write({"repayment_id": existing_repayment.id})
                _logger.info(
                    "cron_auto_reconcile: txn %s linked to existing repayment %s.",
                    txn.mpesa_code,
                    existing_repayment.payment_reference,
                )
                continue

            try:
                payment_date = (
                    txn.completed_at.date() if txn.completed_at else fields.Date.today()
                )
                repayment = (
                    self.env["alba.loan.repayment"]
                    .sudo()
                    .create(
                        {
                            "loan_id": txn.loan_id.id,
                            "payment_date": payment_date,
                            "amount_paid": txn.amount,
                            "payment_method": "mpesa",
                            "mpesa_transaction_id": txn.mpesa_code,
                            "payment_reference": txn.mpesa_code,
                            "state": "draft",
                            "notes": _(
                                "Auto-created by reconciliation cron from "
                                "M-Pesa transaction %s (phone: %s, type: %s)."
                            )
                            % (
                                txn.mpesa_code,
                                txn.phone_number or "—",
                                txn.transaction_type,
                            ),
                        }
                    )
                )
                txn.write({"repayment_id": repayment.id})
                reconciled_count += 1
                _logger.info(
                    "cron_auto_reconcile: txn %s → repayment %s (draft).",
                    txn.mpesa_code,
                    repayment.payment_reference,
                )
            except Exception as exc:
                _logger.warning(
                    "cron_auto_reconcile: failed to reconcile txn %s — %s",
                    txn.mpesa_code,
                    exc,
                )

        _logger.info(
            "cron_auto_reconcile: reconciled %d transaction(s).", reconciled_count
        )
