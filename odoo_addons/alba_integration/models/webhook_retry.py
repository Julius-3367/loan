# -*- coding: utf-8 -*-
"""
alba.webhook.retry — Outbound webhook retry queue for Alba Capital.

When an outbound webhook delivery fails (network error, non-2xx response,
timeout), instead of silently dropping the event the system creates an
``alba.webhook.retry`` record so that the event can be retried automatically
by a cron job and inspected / manually retried by operators.

Retry strategy
--------------
Exponential back-off with jitter:
  Attempt 1 : 2  minutes after failure
  Attempt 2 : 5  minutes
  Attempt 3 : 15 minutes
  Attempt 4 : 60 minutes
  Attempt 5+: 240 minutes (4 hours)

After ``max_attempts`` (default 5) the record is moved to status='dead' and
no further automatic retries occur.  Operators can still click "Retry Now" to
attempt one more delivery.

Public surface
--------------
  AlbaWebhookRetry.enqueue(api_key, event_type, payload_dict)  → record
  record.action_retry_now()                                     → notification
  AlbaWebhookRetry.cron_process_retry_queue()                   → None
"""

import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry back-off schedule  (attempt_number → delay in minutes)
# ---------------------------------------------------------------------------
_BACKOFF_MINUTES = {
    1: 2,
    2: 5,
    3: 15,
    4: 60,
}
_DEFAULT_BACKOFF = 240  # minutes for attempt 5+
_DEFAULT_MAX_ATTEMPTS = 5


def _next_retry_at(attempt_number: int) -> object:
    """Return a Datetime *attempt_number* attempts into the back-off schedule."""
    delay = _BACKOFF_MINUTES.get(attempt_number, _DEFAULT_BACKOFF)
    return fields.Datetime.now() + timedelta(minutes=delay)


class AlbaWebhookRetry(models.Model):
    """
    Outbound webhook retry queue entry.

    Each record represents one pending or exhausted delivery attempt for a
    specific event payload destined for the Django portal.

    Lifecycle
    ---------
    1. A failed send_webhook() call creates a record via enqueue() with
       status='pending' and next_retry_at set per the back-off schedule.
    2. cron_process_retry_queue() picks up records whose next_retry_at has
       passed, calls send_webhook() again, and either:
         a. Marks the record status='delivered' on success.
         b. Increments attempt_count, updates next_retry_at, and leaves
            status='pending' if attempts remain.
         c. Marks status='dead' when max_attempts is exceeded.
    3. Operators can manually trigger a retry via action_retry_now() at any
       point, even on 'dead' records.
    """

    _name = "alba.webhook.retry"
    _description = "Outbound Webhook Retry Queue"
    _inherit = ["mail.thread"]
    _order = "next_retry_at asc, id asc"
    _rec_name = "event_type"

    # =========================================================================
    # Fields
    # =========================================================================

    # ── Event identity ────────────────────────────────────────────────────────

    event_type = fields.Char(
        string="Event Type",
        required=True,
        index=True,
        help='Dot-separated event identifier, e.g. "application.status_changed".',
    )
    delivery_id = fields.Char(
        string="Delivery ID",
        index=True,
        copy=False,
        help="UUID that uniquely identifies this delivery attempt envelope.",
    )

    # ── Payload ───────────────────────────────────────────────────────────────

    payload_json = fields.Text(
        string="Payload (JSON)",
        required=True,
        help="JSON-serialised payload dict to embed in the webhook envelope.",
    )

    # ── Destination ───────────────────────────────────────────────────────────

    api_key_id = fields.Many2one(
        "alba.api.key",
        string="API Key / Destination",
        required=True,
        ondelete="cascade",
        index=True,
        help="The API key record whose Django URL the webhook will be sent to.",
    )
    target_url = fields.Char(
        string="Target URL",
        help="Snapshot of the full webhook URL at the time the record was created.",
    )

    # ── Retry tracking ────────────────────────────────────────────────────────

    status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("delivered", "Delivered"),
            ("dead", "Dead (Max Retries Exceeded)"),
        ],
        string="Status",
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )
    attempt_count = fields.Integer(
        string="Attempts Made",
        default=0,
        help="Number of delivery attempts made so far (including the original).",
    )
    max_attempts = fields.Integer(
        string="Max Attempts",
        default=_DEFAULT_MAX_ATTEMPTS,
        help=(
            "Maximum number of delivery attempts before the record is "
            "moved to 'dead' status."
        ),
    )
    next_retry_at = fields.Datetime(
        string="Next Retry At",
        index=True,
        help="Earliest datetime at which the cron job will retry this delivery.",
    )
    last_attempt_at = fields.Datetime(
        string="Last Attempt At",
        readonly=True,
    )
    delivered_at = fields.Datetime(
        string="Delivered At",
        readonly=True,
    )

    # ── Result of last attempt ─────────────────────────────────────────────────

    last_http_status = fields.Integer(
        string="Last HTTP Status",
        default=0,
        help="HTTP status code returned by the last delivery attempt (0 = no response).",
    )
    last_error = fields.Text(
        string="Last Error",
        help="Error message or non-2xx response body from the last attempt.",
    )

    # ── Original failure context ──────────────────────────────────────────────

    original_error = fields.Text(
        string="Original Failure Reason",
        help="Error detail from the first failed delivery attempt.",
    )

    # ── Company ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    # =========================================================================
    # Class-level factory
    # =========================================================================

    @api.model
    def enqueue(
        self,
        api_key,
        event_type: str,
        payload_dict: dict,
        original_error: str = "",
        http_status: int = 0,
        delivery_id: str = "",
    ):
        """
        Create a retry queue entry for a failed outbound webhook.

        Args:
            api_key (alba.api.key):   The API key record that owns the destination URL.
            event_type (str):         Dot-separated event string.
            payload_dict (dict):      The data payload for the webhook.
            original_error (str):     Error detail from the first failure.
            http_status (int):        HTTP status from the first attempt (0 if no response).
            delivery_id (str):        UUID from the original delivery envelope.

        Returns:
            alba.webhook.retry: The created record.
        """
        record = self.sudo().create(
            {
                "event_type": event_type,
                "delivery_id": delivery_id or "",
                "payload_json": json.dumps(payload_dict, default=str),
                "api_key_id": api_key.id,
                "target_url": api_key.get_full_webhook_url(),
                "status": "pending",
                "attempt_count": 1,  # original attempt already made
                "max_attempts": _DEFAULT_MAX_ATTEMPTS,
                "next_retry_at": _next_retry_at(1),
                "last_attempt_at": fields.Datetime.now(),
                "last_http_status": http_status,
                "last_error": original_error[:2000] if original_error else "",
                "original_error": original_error[:2000] if original_error else "",
                "company_id": api_key.company_id.id
                if api_key.company_id
                else self.env.company.id,
            }
        )
        _logger.info(
            "Webhook retry enqueued: event=%s api_key='%s' delivery_id=%s "
            "next_retry_at=%s",
            event_type,
            api_key.name,
            delivery_id,
            record.next_retry_at,
        )
        return record

    # =========================================================================
    # Manual action
    # =========================================================================

    def action_retry_now(self):
        """
        Manually trigger an immediate retry of this webhook delivery.

        Can be invoked on records in any status, including 'dead'.
        Resets next_retry_at to now so the next cron run picks it up,
        or executes the delivery synchronously in the current request.
        """
        self.ensure_one()

        if self.status == "delivered":
            raise UserError(_("This webhook has already been delivered successfully."))

        _logger.info(
            "Manual retry triggered for webhook retry id=%d event=%s.",
            self.id,
            self.event_type,
        )

        # Attempt delivery synchronously
        success, http_code, error_msg = self._attempt_delivery()

        if success:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Delivered"),
                    "message": _("Webhook '%s' delivered successfully (HTTP %d).")
                    % (self.event_type, http_code),
                    "type": "success",
                    "sticky": False,
                },
            }
        else:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Delivery Failed"),
                    "message": _("HTTP %d — %s") % (http_code, error_msg[:300]),
                    "type": "danger",
                    "sticky": True,
                },
            }

    def action_mark_dead(self):
        """Manually move a pending record to 'dead' without retrying."""
        self.ensure_one()
        self.write(
            {
                "status": "dead",
                "last_error": "Manually marked dead by %s." % self.env.user.name,
            }
        )
        self.message_post(
            body=_("Record manually marked as <b>dead</b> by %s.") % self.env.user.name
        )

    def action_requeue(self):
        """Reset a 'dead' record back to 'pending' for another retry cycle."""
        self.ensure_one()
        if self.status != "dead":
            raise UserError(_("Only 'dead' records can be re-queued."))
        self.write(
            {
                "status": "pending",
                "attempt_count": 0,
                "next_retry_at": _next_retry_at(1),
                "last_error": "",
            }
        )
        self.message_post(body=_("Re-queued for retry by %s.") % self.env.user.name)

    # =========================================================================
    # Scheduled action (cron)
    # =========================================================================

    @api.model
    def cron_process_retry_queue(self):
        """
        Process all pending webhook retry records whose next_retry_at has
        passed.

        Called every 15 minutes by a scheduled action.  Records are processed
        in next_retry_at order (oldest first) so the most overdue deliveries
        are handled first.

        Each delivery is attempted synchronously.  On success the record is
        marked 'delivered'.  On failure the attempt_count is incremented and
        next_retry_at is pushed forward per the back-off schedule.  Records
        that have exceeded max_attempts are moved to 'dead'.
        """
        now = fields.Datetime.now()
        due = self.sudo().search(
            [
                ("status", "=", "pending"),
                ("next_retry_at", "<=", now),
            ],
            order="next_retry_at asc",
            limit=50,  # process at most 50 per cron run to avoid timeouts
        )

        _logger.info("cron_process_retry_queue: found %d due record(s).", len(due))

        delivered = 0
        failed = 0
        dead = 0

        for record in due:
            # Mark as processing to prevent concurrent cron runs picking it up
            record.write({"status": "processing"})

            success, http_code, error_msg = record._attempt_delivery()

            if success:
                delivered += 1
            else:
                new_attempt = (
                    record.attempt_count
                )  # already incremented in _attempt_delivery
                if new_attempt >= record.max_attempts:
                    record.write({"status": "dead"})
                    dead += 1
                    _logger.warning(
                        "Webhook retry dead after %d attempts: event=%s target=%s",
                        new_attempt,
                        record.event_type,
                        record.target_url,
                    )
                else:
                    record.write(
                        {
                            "status": "pending",
                            "next_retry_at": _next_retry_at(new_attempt),
                        }
                    )
                    failed += 1

        _logger.info(
            "cron_process_retry_queue: delivered=%d failed=%d dead=%d.",
            delivered,
            failed,
            dead,
        )

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _attempt_delivery(self):
        """
        Try to send the webhook payload via the linked API key's
        send_webhook() method.

        Updates attempt_count, last_attempt_at, last_http_status, and
        last_error in-place.

        Returns:
            tuple[bool, int, str]: (success, http_status_code, error_message)
        """
        self.ensure_one()

        try:
            payload_dict = json.loads(self.payload_json or "{}")
        except (ValueError, TypeError):
            payload_dict = {}

        api_key = self.api_key_id
        if not api_key or not api_key.is_active:
            self.write(
                {
                    "status": "dead",
                    "last_error": "API key is missing or inactive.",
                    "attempt_count": self.attempt_count + 1,
                    "last_attempt_at": fields.Datetime.now(),
                }
            )
            return (False, 0, "API key is missing or inactive.")

        success, http_code = api_key.send_webhook(self.event_type, payload_dict)

        now = fields.Datetime.now()
        new_count = self.attempt_count + 1

        if success:
            self.write(
                {
                    "status": "delivered",
                    "attempt_count": new_count,
                    "last_attempt_at": now,
                    "delivered_at": now,
                    "last_http_status": http_code,
                    "last_error": "",
                }
            )
            _logger.info(
                "Webhook retry delivered: id=%d event=%s attempt=%d http=%d",
                self.id,
                self.event_type,
                new_count,
                http_code,
            )
            return (True, http_code, "")
        else:
            error_msg = f"HTTP {http_code} — delivery failed on attempt {new_count}."
            self.write(
                {
                    "attempt_count": new_count,
                    "last_attempt_at": now,
                    "last_http_status": http_code,
                    "last_error": error_msg,
                }
            )
            _logger.warning(
                "Webhook retry failed: id=%d event=%s attempt=%d http=%d",
                self.id,
                self.event_type,
                new_count,
                http_code,
            )
            return (False, http_code, error_msg)
