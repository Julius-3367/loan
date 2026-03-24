# -*- coding: utf-8 -*-
"""
alba.sync.log — Synchronisation operation log for Alba Capital.

Every data synchronisation operation between the Django portal and Odoo is
recorded here so that:

  • Operators can audit exactly what was sent, when, by whom, and with what
    result — from both directions (Django → Odoo and Odoo → Django).
  • Failed or partial sync operations can be identified, diagnosed, and
    retried without re-processing successful records.
  • Duplicate detection: each record carries the Django-side object ID and
    model name so that re-submitted payloads can be detected and skipped.

Sync directions
---------------
  inbound   Django portal → Odoo  (API endpoint calls)
  outbound  Odoo → Django portal  (webhook deliveries)

Sync operations
---------------
  create        New record created in the target system.
  update        Existing record updated.
  status_change State / status field changed.
  delete        Record deleted or archived.
  full_sync     Batch / bulk synchronisation pass.
  health_check  Connectivity / liveness probe.

Public surface
--------------
  AlbaSyncLog.log_inbound(operation, model_name, django_id, odoo_id,
                           status, detail, request_data, response_data)  → record
  AlbaSyncLog.log_outbound(operation, event_type, odoo_model,
                            odoo_id, django_id, status, detail,
                            webhook_retry_id)                             → record
  AlbaSyncLog.cron_purge_old_logs()                                       → None
"""

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Selection constants
# ---------------------------------------------------------------------------

SYNC_DIRECTIONS = [
    ("inbound", "Inbound  (Django → Odoo)"),
    ("outbound", "Outbound  (Odoo → Django)"),
]

SYNC_OPERATIONS = [
    ("create", "Create"),
    ("update", "Update"),
    ("status_change", "Status Change"),
    ("delete", "Delete / Archive"),
    ("full_sync", "Full Sync"),
    ("health_check", "Health Check"),
]

SYNC_STATUSES = [
    ("success", "Success"),
    ("partial", "Partial Success"),
    ("failure", "Failure"),
    ("skipped", "Skipped (Duplicate / No-op)"),
    ("pending", "Pending"),
]


class AlbaSyncLog(models.Model):
    """
    Immutable audit log for every Django ↔ Odoo synchronisation operation.

    Records are created by the API controller (inbound) and by webhook
    send methods (outbound).  They are never modified after creation — any
    correction creates a new record.

    Retention
    ---------
    A configurable cron job purges records older than
    ``alba.integration.sync_log_retention_days`` (default: 90 days) to
    prevent unbounded table growth.
    """

    _name = "alba.sync.log"
    _description = "Django ↔ Odoo Synchronisation Log"
    _order = "create_date desc, id desc"
    _rec_name = "display_name"

    # =========================================================================
    # Fields
    # =========================================================================

    # ── Display ───────────────────────────────────────────────────────────────

    display_name = fields.Char(
        string="Summary",
        compute="_compute_display_name",
        store=True,
        help="Human-readable one-line summary of this sync operation.",
    )

    # ── Direction & operation ─────────────────────────────────────────────────

    direction = fields.Selection(
        selection=SYNC_DIRECTIONS,
        string="Direction",
        required=True,
        index=True,
        help=(
            "Inbound = Django called an Odoo REST endpoint.  "
            "Outbound = Odoo fired a webhook to Django."
        ),
    )
    operation = fields.Selection(
        selection=SYNC_OPERATIONS,
        string="Operation",
        required=True,
        index=True,
    )

    # ── Model / object identification ─────────────────────────────────────────

    odoo_model = fields.Char(
        string="Odoo Model",
        index=True,
        help='Technical model name, e.g. "alba.loan.application".',
    )
    odoo_record_id = fields.Integer(
        string="Odoo Record ID",
        index=True,
        help="database id of the Odoo record created or updated.",
    )
    django_model = fields.Char(
        string="Django Model",
        help='Django model / resource name, e.g. "LoanApplication".',
    )
    django_record_id = fields.Integer(
        string="Django Record ID",
        index=True,
        help="Primary key of the corresponding Django record.",
    )

    # ── Outbound-specific ─────────────────────────────────────────────────────

    event_type = fields.Char(
        string="Webhook Event Type",
        index=True,
        help='Dot-separated event identifier, e.g. "application.status_changed".',
    )
    webhook_retry_id = fields.Many2one(
        "alba.webhook.retry",
        string="Retry Queue Entry",
        ondelete="set null",
        help="Linked retry record when the initial delivery failed.",
    )

    # ── API key ───────────────────────────────────────────────────────────────

    api_key_id = fields.Many2one(
        "alba.api.key",
        string="API Key",
        ondelete="set null",
        index=True,
        help="The API key used to authenticate this inbound or outbound request.",
    )

    # ── Outcome ───────────────────────────────────────────────────────────────

    status = fields.Selection(
        selection=SYNC_STATUSES,
        string="Status",
        required=True,
        index=True,
    )
    http_status_code = fields.Integer(
        string="HTTP Status Code",
        default=0,
        help="HTTP response code returned (0 when no HTTP response was received).",
    )
    detail = fields.Text(
        string="Detail / Error Message",
        help=(
            "Human-readable outcome detail.  For failures this should "
            "contain enough context to diagnose the root cause."
        ),
    )
    duration_ms = fields.Integer(
        string="Duration (ms)",
        default=0,
        help="Wall-clock time in milliseconds for the sync operation.",
    )

    # ── Payload snapshots ─────────────────────────────────────────────────────

    request_data = fields.Text(
        string="Request / Outbound Payload",
        help=(
            "JSON snapshot of the inbound request body (for inbound ops) "
            "or the outbound webhook payload (for outbound ops).  "
            "Truncated to 20 000 characters."
        ),
    )
    response_data = fields.Text(
        string="Response / Callback Body",
        help=(
            "JSON snapshot of the response sent back to Django (for inbound) "
            "or the response received from Django (for outbound).  "
            "Truncated to 20 000 characters."
        ),
    )

    # ── Request metadata ──────────────────────────────────────────────────────

    remote_ip = fields.Char(
        string="Remote IP",
        help="Client IP address of the inbound request.",
    )
    user_agent = fields.Char(
        string="User-Agent",
        help="HTTP User-Agent header of the inbound request.",
    )

    # ── Company ───────────────────────────────────────────────────────────────

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    # =========================================================================
    # Computed fields
    # =========================================================================

    @api.depends("direction", "operation", "odoo_model", "odoo_record_id", "status")
    def _compute_display_name(self):
        for rec in self:
            direction_label = dict(SYNC_DIRECTIONS).get(rec.direction, rec.direction)
            operation_label = dict(SYNC_OPERATIONS).get(rec.operation, rec.operation)
            status_label = dict(SYNC_STATUSES).get(rec.status, rec.status)
            model = rec.odoo_model or rec.django_model or "—"
            rec_id = rec.odoo_record_id or rec.django_record_id or 0
            rec.display_name = (
                f"[{direction_label}] {operation_label} — {model}"
                f"#{rec_id} — {status_label}"
            )

    # =========================================================================
    # Factory class methods
    # =========================================================================

    @api.model
    def log_inbound(
        self,
        operation: str,
        odoo_model: str = "",
        django_record_id: int = 0,
        odoo_record_id: int = 0,
        status: str = "success",
        detail: str = "",
        request_data: dict | str = None,
        response_data: dict | str = None,
        http_status_code: int = 200,
        api_key=None,
        remote_ip: str = "",
        user_agent: str = "",
        duration_ms: int = 0,
        django_model: str = "",
        event_type: str = "",
    ):
        """
        Record an inbound sync operation (Django → Odoo API call).

        Args:
            operation:        One of the SYNC_OPERATIONS keys.
            odoo_model:       Technical Odoo model name.
            django_record_id: Primary key of the Django source record.
            odoo_record_id:   ID of the Odoo record created / updated.
            status:           One of the SYNC_STATUSES keys.
            detail:           Human-readable outcome detail or error.
            request_data:     Inbound request body (dict or JSON string).
            response_data:    Response body sent back to Django.
            http_status_code: HTTP status returned to Django.
            api_key:          alba.api.key record (or None).
            remote_ip:        Client IP.
            user_agent:       HTTP User-Agent.
            duration_ms:      Processing time in milliseconds.
            django_model:     Django model / resource name.
            event_type:       Event type string (optional for inbound).

        Returns:
            alba.sync.log: Created record.
        """
        return self._create_log(
            direction="inbound",
            operation=operation,
            odoo_model=odoo_model,
            django_model=django_model,
            odoo_record_id=odoo_record_id,
            django_record_id=django_record_id,
            status=status,
            detail=detail,
            request_data=request_data,
            response_data=response_data,
            http_status_code=http_status_code,
            api_key_id=api_key.id if api_key else False,
            remote_ip=remote_ip,
            user_agent=user_agent,
            duration_ms=duration_ms,
            event_type=event_type,
        )

    @api.model
    def log_outbound(
        self,
        operation: str,
        event_type: str = "",
        odoo_model: str = "",
        odoo_record_id: int = 0,
        django_record_id: int = 0,
        status: str = "success",
        detail: str = "",
        request_data: dict | str = None,
        response_data: dict | str = None,
        http_status_code: int = 0,
        api_key=None,
        duration_ms: int = 0,
        webhook_retry_id: int = 0,
        django_model: str = "",
    ):
        """
        Record an outbound sync operation (Odoo webhook → Django).

        Args:
            operation:         One of the SYNC_OPERATIONS keys.
            event_type:        Dot-separated event string.
            odoo_model:        Technical Odoo model name of the source record.
            odoo_record_id:    ID of the Odoo source record.
            django_record_id:  ID of the corresponding Django record (if known).
            status:            One of the SYNC_STATUSES keys.
            detail:            Human-readable outcome detail.
            request_data:      Outbound webhook payload.
            response_data:     Response received from Django.
            http_status_code:  HTTP response code from Django.
            api_key:           alba.api.key record.
            duration_ms:       Round-trip time in milliseconds.
            webhook_retry_id:  ID of a linked alba.webhook.retry record.
            django_model:      Django model name (if known).

        Returns:
            alba.sync.log: Created record.
        """
        return self._create_log(
            direction="outbound",
            operation=operation,
            event_type=event_type,
            odoo_model=odoo_model,
            django_model=django_model,
            odoo_record_id=odoo_record_id,
            django_record_id=django_record_id,
            status=status,
            detail=detail,
            request_data=request_data,
            response_data=response_data,
            http_status_code=http_status_code,
            api_key_id=api_key.id if api_key else False,
            duration_ms=duration_ms,
            webhook_retry_id=webhook_retry_id or False,
        )

    # =========================================================================
    # Private helpers
    # =========================================================================

    @api.model
    def _create_log(self, **vals):
        """
        Normalise and create a sync log record.

        Truncates large payload blobs to 20 000 characters to prevent
        single log entries from bloating the database.
        """
        # Serialise payload fields if they are dicts
        for field_name in ("request_data", "response_data"):
            value = vals.get(field_name)
            if isinstance(value, dict):
                vals[field_name] = json.dumps(value, default=str)[:20_000]
            elif isinstance(value, str):
                vals[field_name] = value[:20_000]
            else:
                vals[field_name] = ""

        # Truncate string fields with reasonable limits
        if vals.get("detail"):
            vals["detail"] = str(vals["detail"])[:5_000]
        if vals.get("remote_ip"):
            vals["remote_ip"] = str(vals["remote_ip"])[:64]
        if vals.get("user_agent"):
            vals["user_agent"] = str(vals["user_agent"])[:256]
        if vals.get("event_type"):
            vals["event_type"] = str(vals["event_type"])[:128]
        if vals.get("odoo_model"):
            vals["odoo_model"] = str(vals["odoo_model"])[:128]
        if vals.get("django_model"):
            vals["django_model"] = str(vals["django_model"])[:128]

        # Strip falsy non-required relation IDs
        for rel_field in ("api_key_id", "webhook_retry_id"):
            if not vals.get(rel_field):
                vals[rel_field] = False

        try:
            record = self.sudo().create(vals)
            return record
        except Exception as exc:
            # Never let logging errors crash the main request
            _logger.error("AlbaSyncLog._create_log failed: %s | vals=%s", exc, vals)
            return self.browse()

    # =========================================================================
    # Scheduled action (cron) — log retention
    # =========================================================================

    @api.model
    def cron_purge_old_logs(self):
        """
        Purge sync log records older than the configured retention period.

        The retention period is controlled by the system parameter
        ``alba.integration.sync_log_retention_days`` (default: 90 days).

        Called weekly by a scheduled action.  Purges in batches of 1000 to
        avoid locking the table for extended periods.
        """
        from datetime import timedelta

        retention_days = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("alba.integration.sync_log_retention_days", "90")
        )
        cutoff = fields.Datetime.now() - timedelta(days=retention_days)

        _logger.info(
            "cron_purge_old_logs: purging sync logs older than %s (%d-day retention).",
            cutoff.date(),
            retention_days,
        )

        old_records = self.sudo().search(
            [("create_date", "<", cutoff)],
            order="id asc",
            limit=1000,
        )
        count = len(old_records)
        old_records.unlink()

        _logger.info("cron_purge_old_logs: deleted %d sync log record(s).", count)

    # =========================================================================
    # Reporting helpers
    # =========================================================================

    @api.model
    def get_sync_health_summary(self, hours: int = 24) -> dict:
        """
        Return a summary of sync activity in the last *hours* hours.

        Useful for dashboard widgets and health-check webhooks.

        Args:
            hours: Look-back window in hours (default 24).

        Returns:
            dict: Counts broken down by direction and status::

                {
                    "window_hours": 24,
                    "inbound": {"success": N, "failure": N, "total": N},
                    "outbound": {"success": N, "failure": N, "total": N},
                    "total": N,
                }
        """
        from datetime import timedelta

        since = fields.Datetime.now() - timedelta(hours=hours)
        records = self.sudo().search([("create_date", ">=", since)])

        summary: dict = {
            "window_hours": hours,
            "inbound": {"success": 0, "failure": 0, "skipped": 0, "total": 0},
            "outbound": {"success": 0, "failure": 0, "skipped": 0, "total": 0},
            "total": len(records),
        }

        for rec in records:
            direction = rec.direction or "inbound"
            bucket = summary.get(direction, summary["inbound"])
            bucket["total"] += 1
            if rec.status == "success":
                bucket["success"] += 1
            elif rec.status in ("failure", "partial"):
                bucket["failure"] += 1
            elif rec.status == "skipped":
                bucket["skipped"] += 1

        return summary
