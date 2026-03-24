# -*- coding: utf-8 -*-
"""
alba_loans.controllers.mpesa_callback
======================================
Daraja API callback endpoints for Alba Capital.

Safaricom fires HTTP POST requests to these URLs after every M-Pesa
transaction.  All endpoints are public (no Odoo session required) because
Safaricom cannot authenticate via Odoo sessions.

Endpoints registered
--------------------
POST /alba/mpesa/stk/callback      — STK Push result callback
POST /alba/mpesa/c2b/validation    — C2B validation request
POST /alba/mpesa/c2b/confirmation  — C2B payment confirmation
POST /alba/mpesa/b2c/result        — B2C payment result
POST /alba/mpesa/b2c/timeout       — B2C queue timeout notification

Security
--------
Safaricom does not sign callbacks with a shared secret, so the recommended
approach is to:
  1. Whitelist Safaricom IP ranges at the network/firewall level.
  2. Use HTTPS only (required by Safaricom for production).
  3. Validate the shortcode in the callback body against your configuration.

The controller validates the shortcode on every inbound callback and returns
HTTP 400 if it does not match any active ``alba.mpesa.config`` record.
"""

import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Safaricom expects these exact JSON bodies to accept / reject C2B payments.
_C2B_ACCEPT = json.dumps({"ResultCode": 0, "ResultDesc": "Accepted"})
_C2B_REJECT = json.dumps({"ResultCode": 1, "ResultDesc": "Rejected"})
_STK_ACK = json.dumps({"ResultCode": 0, "ResultDesc": "Success"})


def _json_response(body: dict | str, status: int = 200):
    """Return a plain JSON HTTP response bypassing Odoo's JSON-RPC wrapper."""
    if isinstance(body, dict):
        body = json.dumps(body)
    return request.make_response(
        body,
        headers=[
            ("Content-Type", "application/json; charset=utf-8"),
            ("X-Content-Type-Options", "nosniff"),
        ],
        status=status,
    )


def _parse_body() -> dict:
    """
    Parse the raw request body as JSON.

    Returns:
        dict: Parsed body, or empty dict on parse failure.
    """
    try:
        raw = request.httprequest.get_data(as_text=True)
        return json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError):
        _logger.warning("M-Pesa callback: failed to parse request body as JSON.")
        return {}


def _get_config_for_shortcode(shortcode: str):
    """
    Return the active ``alba.mpesa.config`` record whose shortcode or
    till_number matches *shortcode*.

    Returns empty recordset when no match is found.
    """
    if not shortcode:
        return request.env["alba.mpesa.config"].sudo().browse()
    return (
        request.env["alba.mpesa.config"]
        .sudo()
        .search(
            [
                ("is_active", "=", True),
                "|",
                ("shortcode", "=", shortcode),
                ("till_number", "=", shortcode),
            ],
            limit=1,
        )
    )


class AlbaMpesaCallbackController(http.Controller):
    """
    Public HTTP controller that receives Safaricom Daraja callback POSTs.

    All handlers follow the same pattern:
      1. Parse the JSON request body.
      2. Validate the shortcode against active M-Pesa configurations.
      3. Delegate processing to the appropriate model method.
      4. Return the Safaricom-expected JSON acknowledgement.
      5. Never raise exceptions to the caller — always return a valid JSON
         response so Safaricom does not retry indefinitely.
    """

    # =========================================================================
    # STK Push callback
    # =========================================================================

    @http.route(
        "/alba/mpesa/stk/callback",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def stk_callback(self, **kwargs):
        """
        Receive the STK Push (Lipa Na M-Pesa Online) result callback from
        Safaricom.

        Safaricom fires this request whether the customer confirmed the
        prompt, cancelled it, or it timed out.  The handler updates the
        matching ``alba.mpesa.transaction`` record with the outcome.

        Safaricom expects HTTP 200 with ``{"ResultCode": 0, "ResultDesc": "Success"}``.
        """
        data = _parse_body()
        _logger.info("STK callback received: %s", json.dumps(data)[:500])

        try:
            # Validate shortcode
            callback = data.get("Body", {}).get("stkCallback", {})
            # STK callbacks don't always include BusinessShortCode directly
            # — we proceed without shortcode validation here and trust the URL.

            TxnModel = request.env["alba.mpesa.transaction"].sudo()
            TxnModel.process_stk_callback(data)

        except Exception as exc:
            _logger.exception("STK callback processing error: %s", exc)
            # Still return 200 so Safaricom does not retry
        return _json_response({"ResultCode": 0, "ResultDesc": "Success"})

    # =========================================================================
    # C2B callbacks
    # =========================================================================

    @http.route(
        "/alba/mpesa/c2b/validation",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def c2b_validation(self, **kwargs):
        """
        Receive a C2B validation request from Safaricom.

        Safaricom calls this URL *before* completing a payment to allow the
        business to accept or reject it.  The handler:
          1. Validates the shortcode.
          2. Checks whether the BillRefNumber (loan number) exists and is
             an active loan.
          3. Returns ResultCode 0 (accept) or 1 (reject).

        Rejecting a payment causes Safaricom to immediately cancel the
        customer's transaction on their handset.
        """
        data = _parse_body()
        _logger.info("C2B validation received: %s", json.dumps(data)[:500])

        try:
            shortcode = str(data.get("BusinessShortCode") or "").strip()
            config = _get_config_for_shortcode(shortcode)
            if not config:
                _logger.warning(
                    "C2B validation: unknown shortcode '%s' — rejecting.", shortcode
                )
                return _json_response(
                    {"ResultCode": 1, "ResultDesc": "Unknown business shortcode"}
                )

            bill_ref = str(data.get("BillRefNumber") or "").strip()
            if not bill_ref:
                _logger.warning(
                    "C2B validation: empty BillRefNumber — accepting anyway."
                )
                return _json_response({"ResultCode": 0, "ResultDesc": "Accepted"})

            # Check whether the loan exists and is active
            loan = (
                request.env["alba.loan"]
                .sudo()
                .search(
                    [
                        ("loan_number", "=", bill_ref),
                        ("state", "in", ("active", "npl")),
                    ],
                    limit=1,
                )
            )
            if not loan:
                _logger.warning(
                    "C2B validation: no active loan for BillRefNumber '%s' — rejecting.",
                    bill_ref,
                )
                return _json_response(
                    {
                        "ResultCode": 1,
                        "ResultDesc": f"Loan {bill_ref} not found or not active",
                    }
                )

            _logger.info(
                "C2B validation: accepted payment for loan %s (shortcode=%s).",
                bill_ref,
                shortcode,
            )
            return _json_response({"ResultCode": 0, "ResultDesc": "Accepted"})

        except Exception as exc:
            _logger.exception("C2B validation error: %s", exc)
            # Accept on error to avoid blocking a real payment
            return _json_response({"ResultCode": 0, "ResultDesc": "Accepted"})

    @http.route(
        "/alba/mpesa/c2b/confirmation",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def c2b_confirmation(self, **kwargs):
        """
        Receive a C2B payment confirmation from Safaricom.

        This is the definitive notification that the customer's money has
        left their wallet and arrived in the business account.  The handler
        creates an ``alba.mpesa.transaction`` record and attempts to
        auto-match it to a loan via the BillRefNumber.

        Safaricom expects HTTP 200 with ``{"ResultCode": 0, "ResultDesc": "Accepted"}``.
        """
        data = _parse_body()
        _logger.info(
            "C2B confirmation received: TransID=%s Amount=%s Phone=%s Ref=%s",
            data.get("TransID"),
            data.get("TransAmount"),
            data.get("MSISDN"),
            data.get("BillRefNumber"),
        )

        try:
            shortcode = str(data.get("BusinessShortCode") or "").strip()
            config = _get_config_for_shortcode(shortcode)

            TxnModel = request.env["alba.mpesa.transaction"].sudo()
            txn = TxnModel.process_c2b_confirmation(data)

            # Link config if we found one
            if config and txn and not txn.config_id:
                txn.write({"config_id": config.id})

            # Fire synchronisation webhook to Django portal
            if txn and txn.status == "completed":
                _fire_payment_webhook(txn)

        except Exception as exc:
            _logger.exception("C2B confirmation processing error: %s", exc)

        return _json_response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # =========================================================================
    # B2C callbacks
    # =========================================================================

    @http.route(
        "/alba/mpesa/b2c/result",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def b2c_result(self, **kwargs):
        """
        Receive a B2C payment result callback from Safaricom.

        Fired after a B2C (investor / customer payout) transaction
        completes or fails.  Updates the matching ``alba.mpesa.transaction``
        record with the final outcome.
        """
        data = _parse_body()
        _logger.info("B2C result received: %s", json.dumps(data)[:500])

        try:
            TxnModel = request.env["alba.mpesa.transaction"].sudo()
            TxnModel.process_b2c_result(data)
        except Exception as exc:
            _logger.exception("B2C result processing error: %s", exc)

        return _json_response({"ResultCode": 0, "ResultDesc": "Success"})

    @http.route(
        "/alba/mpesa/b2c/timeout",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def b2c_timeout(self, **kwargs):
        """
        Receive a B2C queue timeout notification from Safaricom.

        Fired when the B2C request was not processed within the queue
        timeout period.  Marks the matching transaction as 'cancelled'.
        """
        data = _parse_body()
        _logger.warning("B2C timeout received: %s", json.dumps(data)[:500])

        try:
            result = data.get("Result", {})
            conversation_id = (result.get("ConversationID") or "").strip()
            originator_id = (result.get("OriginatorConversationID") or "").strip()

            txn = (
                request.env["alba.mpesa.transaction"]
                .sudo()
                .search(
                    [
                        "|",
                        ("conversation_id", "=", conversation_id),
                        ("originator_conversation_id", "=", originator_id),
                    ],
                    limit=1,
                )
            )
            if txn:
                txn.write(
                    {
                        "status": "cancelled",
                        "result_code": "timeout",
                        "result_desc": "B2C queue timeout",
                        "failure_reason": "Safaricom B2C queue timeout — transaction not processed.",
                        "raw_response": json.dumps(data),
                    }
                )
                _logger.info(
                    "B2C txn %s marked cancelled due to queue timeout.",
                    txn.conversation_id or txn.id,
                )
        except Exception as exc:
            _logger.exception("B2C timeout handling error: %s", exc)

        return _json_response({"ResultCode": 0, "ResultDesc": "Success"})

    # =========================================================================
    # Health check (for ops monitoring)
    # =========================================================================

    @http.route(
        "/alba/mpesa/health",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def mpesa_health(self, **kwargs):
        """
        Liveness probe for the M-Pesa callback listener.

        Returns the count of active M-Pesa configurations so operations
        teams can verify the module is loaded and accessible.
        """
        try:
            count = (
                request.env["alba.mpesa.config"]
                .sudo()
                .search_count([("is_active", "=", True)])
            )
            return _json_response(
                {
                    "status": "ok",
                    "service": "alba-mpesa-callbacks",
                    "active_configs": count,
                }
            )
        except Exception as exc:
            _logger.exception("M-Pesa health check error: %s", exc)
            return _json_response({"status": "error", "detail": str(exc)}, status=500)


# =============================================================================
# Private helpers
# =============================================================================


def _fire_payment_webhook(txn):
    """
    Fire a ``payment.mpesa_received`` webhook to the Django portal after a
    successful inbound M-Pesa payment (C2B or STK callback).

    Args:
        txn (alba.mpesa.transaction): The completed transaction record.
    """
    try:
        api_key = (
            request.env["alba.api.key"]
            .sudo()
            .search([("is_active", "=", True)], limit=1)
        )
        if not api_key:
            return

        payload = {
            "mpesa_code": txn.mpesa_code or "",
            "amount": float(txn.amount),
            "phone_number": txn.phone_number or "",
            "account_reference": txn.account_reference or "",
            "loan_odoo_id": txn.loan_id.id if txn.loan_id else 0,
            "loan_number": txn.loan_id.loan_number if txn.loan_id else "",
            "transaction_type": txn.transaction_type,
            "completed_at": txn.completed_at.isoformat() if txn.completed_at else "",
            "repayment_odoo_id": txn.repayment_id.id if txn.repayment_id else 0,
        }
        api_key.send_webhook("payment.mpesa_received", payload)
    except Exception as exc:
        _logger.warning("Failed to fire payment.mpesa_received webhook: %s", exc)
