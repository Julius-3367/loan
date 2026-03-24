# -*- coding: utf-8 -*-
"""
alba.webhook.log — Immutable audit trail for all webhook traffic handled by the
Alba Capital Django Integration Bridge.

Every HTTP interaction crossing the Odoo ↔ Django boundary is recorded here:

  • Outbound events fired by Odoo to the Django portal
    (application.status_changed, loan.disbursed, payment.matched, customer.kyc_verified)

  • Inbound requests received from the Django portal that could not be matched
    to a specific business flow (e.g. replay attempts, failed auth, etc.)

Records are written by ``alba.api.key.send_webhook()`` for outbound traffic and
by the controller's ``_log_inbound()`` helper for inbound traffic.  Log entries
are intentionally kept append-only from a business perspective — the security
groups grant ``perm_unlink`` only to Integration Admins for housekeeping
purposes.
"""

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AlbaWebhookLog(models.Model):
    """
    Append-only audit log for every webhook event sent to or received from the
    Django customer portal.

    Fields
    ------
    direction
        ``outbound`` — Odoo fired a webhook POST to Django.
        ``inbound``  — Django called an Odoo REST endpoint (logged on error /
                       unusual conditions).
    status
        ``pending``  — Request was queued / partially dispatched.
        ``success``  — Remote server returned HTTP 2xx.
        ``failed``   — Network error, timeout, or non-2xx HTTP status.
    """

    _name = "alba.webhook.log"
    _description = "Alba Integration Webhook Log"
    _rec_name = "event_type"
    _order = "timestamp desc, id desc"

    # Prevent accidental writes to existing log entries (they are append-only
    # by convention); override in specific maintenance methods if needed.
    # Note: we do NOT set _log_access = False so that Odoo's standard
    # create_date / write_date fields remain available for debugging.

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    api_key_id = fields.Many2one(
        "alba.api.key",
        string="API Key",
        ondelete="set null",
        index=True,
        help="The integration API key associated with this webhook event.",
    )

    direction = fields.Selection(
        selection=[
            ("outbound", "Outbound  (Odoo → Django)"),
            ("inbound", "Inbound   (Django → Odoo)"),
        ],
        string="Direction",
        required=True,
        index=True,
        help=(
            "Outbound: Odoo sent a webhook POST to the Django portal.\n"
            "Inbound: Django called an Odoo REST endpoint."
        ),
    )

    event_type = fields.Char(
        string="Event Type",
        required=True,
        index=True,
        help=(
            "Dot-separated event identifier.  Examples:\n"
            "  application.status_changed\n"
            "  loan.disbursed\n"
            "  payment.matched\n"
            "  customer.kyc_verified"
        ),
    )

    payload = fields.Text(
        string="Request Payload",
        help="Full JSON body that was sent (outbound) or received (inbound).",
    )

    response_body = fields.Text(
        string="Response Body",
        help=(
            "First 10 000 characters of the HTTP response body returned by the "
            "remote server (outbound) or the Odoo controller's reply (inbound)."
        ),
    )

    response_code = fields.Integer(
        string="HTTP Status Code",
        help="HTTP status code returned by the remote server.",
    )

    status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        string="Status",
        required=True,
        default="pending",
        index=True,
        help=(
            "pending — event was queued or partially dispatched.\n"
            "success — remote server responded with HTTP 2xx.\n"
            "failed  — network error, timeout, or non-2xx HTTP status."
        ),
    )

    error_message = fields.Text(
        string="Error Message",
        help="Human-readable description of the failure, if any.",
    )

    timestamp = fields.Datetime(
        string="Timestamp",
        default=fields.Datetime.now,
        required=True,
        index=True,
        readonly=True,
        help="Wall-clock time at which this log entry was created.",
    )

    duration_ms = fields.Integer(
        string="Duration (ms)",
        help=(
            "Total round-trip time in milliseconds from when the HTTP request "
            "was dispatched until the response (or timeout) was received."
        ),
    )

    related_model = fields.Char(
        string="Related Model",
        help=(
            "Technical name of the Odoo model that triggered or is associated "
            "with this webhook event, e.g. ``alba.loan.application``."
        ),
    )

    related_record_id = fields.Integer(
        string="Related Record ID",
        help=(
            "Database ID of the Odoo record that triggered or is associated "
            "with this webhook event.  Combine with Related Model to build a "
            "link to the source record."
        ),
    )

    # -------------------------------------------------------------------------
    # Computed / helper fields
    # -------------------------------------------------------------------------

    status_icon = fields.Char(
        string="Status Icon",
        compute="_compute_status_icon",
        store=False,
        help="Font-Awesome icon class derived from the delivery status.",
    )

    payload_preview = fields.Char(
        string="Payload Preview",
        compute="_compute_payload_preview",
        store=False,
        help="First 120 characters of the payload for tree-view display.",
    )

    response_code_display = fields.Char(
        string="Response",
        compute="_compute_response_code_display",
        store=False,
        help="Friendly HTTP status string, e.g. '200 OK' or '—' when absent.",
    )

    @api.depends("status")
    def _compute_status_icon(self):
        _icon_map = {
            "success": "fa fa-check-circle text-success",
            "failed": "fa fa-times-circle text-danger",
            "pending": "fa fa-clock-o text-warning",
        }
        for record in self:
            record.status_icon = _icon_map.get(record.status, "fa fa-question-circle")

    @api.depends("payload")
    def _compute_payload_preview(self):
        for record in self:
            raw = (record.payload or "").strip()
            if not raw:
                record.payload_preview = "—"
                continue
            # Attempt to pretty-print first-level keys for readability
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    preview = ", ".join(
                        f"{k}: {v!r}" for k, v in list(parsed.items())[:4]
                    )
                else:
                    preview = raw
            except (json.JSONDecodeError, ValueError):
                preview = raw
            record.payload_preview = preview[:120] + ("…" if len(preview) > 120 else "")

    @api.depends("response_code")
    def _compute_response_code_display(self):
        _http_labels = {
            200: "200 OK",
            201: "201 Created",
            204: "204 No Content",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            403: "403 Forbidden",
            404: "404 Not Found",
            408: "408 Timeout",
            422: "422 Unprocessable Entity",
            429: "429 Too Many Requests",
            500: "500 Server Error",
            502: "502 Bad Gateway",
            503: "503 Service Unavailable",
            504: "504 Gateway Timeout",
        }
        for record in self:
            code = record.response_code
            if not code:
                record.response_code_display = "—"
            else:
                record.response_code_display = _http_labels.get(code, str(code))

    # -------------------------------------------------------------------------
    # ORM helpers
    # -------------------------------------------------------------------------

    @api.model
    def create_inbound_log(
        self,
        *,
        api_key_id,
        event_type,
        payload_str,
        response_code,
        status,
        error_message="",
        duration_ms=0,
        related_model="",
        related_record_id=0,
    ):
        """
        Convenience factory for recording inbound API calls from Django.

        All parameters are keyword-only to prevent positional argument confusion
        when called from the controller layer.

        Args:
            api_key_id (int): ID of the matching ``alba.api.key`` record.
            event_type (str): Endpoint / action label, e.g. ``"customers.create"``.
            payload_str (str): Raw JSON request body.
            response_code (int): HTTP status code returned to the caller.
            status (str): ``"success"`` | ``"failed"`` | ``"pending"``.
            error_message (str): Optional failure description.
            duration_ms (int): Request processing time in milliseconds.
            related_model (str): Odoo model name of the affected record.
            related_record_id (int): Database ID of the affected record.

        Returns:
            alba.webhook.log: Newly created log record.
        """
        return self.sudo().create(
            {
                "api_key_id": api_key_id or False,
                "direction": "inbound",
                "event_type": event_type or "unknown",
                "payload": payload_str or "",
                "response_code": response_code or 0,
                "status": status or "pending",
                "error_message": error_message or "",
                "duration_ms": duration_ms or 0,
                "related_model": related_model or "",
                "related_record_id": related_record_id or 0,
            }
        )

    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------

    def get_parsed_payload(self):
        """
        Parse and return the stored JSON payload as a Python dict.

        Returns:
            dict: Parsed payload, or empty dict when parsing fails.
        """
        self.ensure_one()
        if not self.payload:
            return {}
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, ValueError):
            _logger.debug(
                "WebhookLog #%d: payload is not valid JSON — returning {}.", self.id
            )
            return {}

    def name_get(self):
        """Return a descriptive display name for list contexts."""
        result = []
        for record in self:
            ts = (
                record.timestamp.strftime("%Y-%m-%d %H:%M") if record.timestamp else "?"
            )
            label = f"[{record.direction[:3].upper()}] {record.event_type} @ {ts}"
            result.append((record.id, label))
        return result
