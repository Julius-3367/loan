# -*- coding: utf-8 -*-
"""
alba.api.key — API Key management for the Alba Capital Django Integration Bridge.

Each record represents a trusted integration client (e.g. the Django portal).
It stores:
  • The inbound API key that Django must send in every request (X-Alba-API-Key).
  • The shared HMAC-SHA256 secret used to sign outbound webhook payloads.
  • The target Django base URL and webhook path where Odoo fires events.

Public surface
--------------
  AlbaApiKey._generate_key()            → new UUID4 string
  AlbaApiKey._generate_secret()         → 64-char hex string
  AlbaApiKey.verify_key(key_string)     → api.key record or empty recordset
  record.send_webhook(event, payload)   → (success: bool, http_code: int)
  record.action_regenerate_key()        → client notification action
  record.action_rotate_secret()         → client notification action
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import requests as req_lib
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AlbaApiKey(models.Model):
    """
    Represents a trusted API client (the Django portal) that is allowed to
    call Odoo REST endpoints and receive HMAC-signed webhook payloads.
    """

    _name = "alba.api.key"
    _description = "Alba Integration API Key"
    _inherit = ["mail.thread"]
    _rec_name = "name"
    _order = "name"

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    name = fields.Char(
        string="Label",
        required=True,
        tracking=True,
        help='Human-readable label, e.g. "Django Portal – Production".',
    )

    key = fields.Char(
        string="API Key",
        readonly=True,
        copy=False,
        index=True,
        help=(
            "Auto-generated UUID4 key. The Django portal must send this value "
            "in the X-Alba-API-Key request header."
        ),
    )

    webhook_secret = fields.Char(
        string="Webhook Secret",
        readonly=True,
        copy=False,
        help=(
            "Auto-generated 64-char hex secret used for HMAC-SHA256 signing of "
            "outbound webhook payloads. The X-Alba-Signature header will contain "
            "sha256=<hex_digest>."
        ),
    )

    django_base_url = fields.Char(
        string="Django Portal URL",
        required=True,
        help=(
            "Base URL of the Django customer portal, "
            "e.g. https://portal.albacapital.co.ke"
        ),
    )

    webhook_path = fields.Char(
        string="Webhook Path",
        default="/api/v1/webhooks/odoo/",
        help=(
            "URL path on the Django server that receives Odoo webhook POST "
            "requests. Will be appended to Django Portal URL."
        ),
    )

    full_webhook_url = fields.Char(
        string="Full Webhook URL",
        compute="_compute_full_webhook_url",
        store=False,
        help="Computed concatenation of Django Portal URL and Webhook Path.",
    )

    is_active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Inactive keys are rejected on all inbound requests.",
    )

    last_used = fields.Datetime(
        string="Last Used",
        readonly=True,
        copy=False,
        help="Timestamp of the most recent successful authentication.",
    )

    allowed_ips = fields.Text(
        string="Allowed IP Addresses",
        help=(
            "Comma-separated list of IP addresses permitted to use this key. "
            "Leave empty to allow requests from any IP address."
        ),
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        help="Restrict this integration key to a specific company.",
    )

    log_ids = fields.One2many(
        "alba.webhook.log",
        "api_key_id",
        string="Webhook Logs",
        readonly=True,
    )

    log_count = fields.Integer(
        string="Log Count",
        compute="_compute_log_count",
    )

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends("log_ids")
    def _compute_log_count(self):
        for record in self:
            record.log_count = len(record.log_ids)

    @api.depends("django_base_url", "webhook_path")
    def _compute_full_webhook_url(self):
        for record in self:
            record.full_webhook_url = record.get_full_webhook_url()

    # -------------------------------------------------------------------------
    # Static / class-level helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _generate_key():
        """Return a new UUID4 string to use as an API key."""
        return str(uuid.uuid4())

    @staticmethod
    def _generate_secret():
        """Return a new 64-character hex string to use as a webhook secret."""
        return os.urandom(32).hex()

    @api.model
    def verify_key(self, key_string):
        """
        Look up and return the active ``alba.api.key`` record whose ``key``
        field matches *key_string*.

        On a successful match the ``last_used`` field is updated atomically.
        Returns an empty recordset when no match is found (i.e. the caller
        should treat the absence of a record as authentication failure).

        Args:
            key_string (str): The raw value taken from the X-Alba-API-Key header.

        Returns:
            alba.api.key: Matched record, or empty recordset.
        """
        if not key_string or not isinstance(key_string, str):
            return self.browse()

        record = self.sudo().search(
            [("key", "=", key_string.strip()), ("is_active", "=", True)],
            limit=1,
        )
        if record:
            # Touch last_used — intentionally not going through business logic
            record.sudo().write({"last_used": fields.Datetime.now()})
        return record

    # -------------------------------------------------------------------------
    # ORM overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate key and webhook_secret when not provided."""
        for vals in vals_list:
            if not vals.get("key"):
                vals["key"] = self._generate_key()
            if not vals.get("webhook_secret"):
                vals["webhook_secret"] = self._generate_secret()
        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # Business actions — callable from form view buttons
    # -------------------------------------------------------------------------

    def action_regenerate_key(self):
        """
        Replace the current API key with a freshly generated UUID4 value.

        The old key is immediately invalidated; any Django portal instance
        using the old key will receive 403 responses until reconfigured.
        """
        self.ensure_one()
        new_key = self._generate_key()
        self.write({"key": new_key})
        self.message_post(
            body=_(
                "API key regenerated. The previous key is now invalid. "
                "Update the Django portal's ODOO_API_KEY setting."
            )
        )
        _logger.info("API key regenerated for integration key '%s'.", self.name)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("API Key Regenerated"),
                "message": _(
                    "The API key for «%s» has been regenerated. "
                    "Update the Django portal configuration before the next request."
                )
                % self.name,
                "type": "warning",
                "sticky": True,
            },
        }

    def action_rotate_secret(self):
        """
        Replace the current webhook secret with a freshly generated 64-char
        hex value.

        All in-flight webhooks signed with the old secret will fail validation
        on the Django side until the new secret is propagated.
        """
        self.ensure_one()
        new_secret = self._generate_secret()
        self.write({"webhook_secret": new_secret})
        self.message_post(
            body=_(
                "Webhook secret rotated. Update the Django portal's "
                "ODOO_WEBHOOK_SECRET setting to resume signature verification."
            )
        )
        _logger.info("Webhook secret rotated for integration key '%s'.", self.name)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook Secret Rotated"),
                "message": _(
                    "The webhook secret for «%s» has been rotated. "
                    "Update the Django portal configuration."
                )
                % self.name,
                "type": "warning",
                "sticky": True,
            },
        }

    def action_view_logs(self):
        """Open the list of webhook logs associated with this API key."""
        self.ensure_one()
        return {
            "name": _("Webhook Logs — %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "alba.webhook.log",
            "view_mode": "tree,form",
            "domain": [("api_key_id", "=", self.id)],
            "context": {
                "default_api_key_id": self.id,
                "search_default_filter_all": 1,
            },
        }

    # -------------------------------------------------------------------------
    # Webhook infrastructure
    # -------------------------------------------------------------------------

    def get_full_webhook_url(self):
        """
        Return the fully qualified URL that Odoo will POST webhook payloads to.

        Rules:
          • Trailing slashes on the base URL are stripped.
          • The webhook path is normalised to always start with '/'.
          • Returns empty string when ``django_base_url`` is not set.
        """
        self.ensure_one()
        base = (self.django_base_url or "").rstrip("/")
        path = self.webhook_path or "/api/v1/webhooks/odoo/"
        if path and not path.startswith("/"):
            path = "/" + path
        return (base + path) if base else ""

    def send_webhook(self, event_type, payload_dict):
        """
        Build, sign, and POST a webhook payload to the Django portal.

        Payload format
        --------------
        {
            "event":     "<event_type>",
            "timestamp": "<ISO-8601 UTC datetime>",
            "data":      { ... }   ← caller-supplied payload_dict
        }

        Signing
        -------
        The raw UTF-8-encoded JSON body is signed with HMAC-SHA256 using
        ``self.webhook_secret``.  The signature is sent as the value of the
        ``X-Alba-Signature`` header in the form ``sha256=<hex_digest>``.

        Logging
        -------
        Every attempt — successful or not — is recorded as an
        ``alba.webhook.log`` record so operators can audit and diagnose
        delivery failures from the Odoo back-office.

        Args:
            event_type (str):   Dot-separated event identifier,
                                e.g. ``"application.status_changed"``.
            payload_dict (dict): Arbitrary JSON-serialisable data to embed
                                 in the ``data`` key of the webhook body.

        Returns:
            tuple[bool, int]: ``(success, http_status_code)``
                              ``success`` is ``True`` when the remote server
                              responded with a 2xx status.  ``http_status_code``
                              is 0 when the request was never sent.
        """
        self.ensure_one()

        # --- Pre-flight checks -----------------------------------------------
        if not self.is_active:
            _logger.warning("Webhook skipped: API key '%s' is inactive.", self.name)
            return (False, 0)

        if not self.django_base_url:
            _logger.warning(
                "Webhook skipped: no Django base URL on API key '%s'.", self.name
            )
            return (False, 0)

        if not self.webhook_secret:
            _logger.warning(
                "Webhook skipped: no webhook secret on API key '%s'.", self.name
            )
            return (False, 0)

        url = self.get_full_webhook_url()
        if not url:
            _logger.warning(
                "Webhook skipped: computed URL is empty for API key '%s'.", self.name
            )
            return (False, 0)

        # --- Build payload ---------------------------------------------------
        timestamp = datetime.now(timezone.utc).isoformat()
        delivery_id = str(uuid.uuid4())

        envelope = {
            "event": event_type,
            "timestamp": timestamp,
            "delivery_id": delivery_id,
            "data": payload_dict,
        }
        body_str = json.dumps(envelope, default=str, ensure_ascii=False)
        body_bytes = body_str.encode("utf-8")

        # --- HMAC-SHA256 signature -------------------------------------------
        raw_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        signature_header = f"sha256={raw_signature}"

        request_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Alba-Signature": signature_header,
            "X-Alba-Event": event_type,
            "X-Alba-Delivery": delivery_id,
            "User-Agent": "AlbaOdooIntegration/1.0",
        }

        # --- HTTP dispatch ---------------------------------------------------
        start_ts = time.monotonic()
        success = False
        response_code = 0
        response_body = ""
        error_message = ""

        try:
            resp = req_lib.post(
                url,
                data=body_bytes,
                headers=request_headers,
                timeout=30,
            )
            response_code = resp.status_code
            # Truncate stored response body to avoid bloating the database
            response_body = resp.text[:10_000]
            success = 200 <= response_code < 300

            if success:
                _logger.info(
                    "Webhook '%s' → %s  delivery=%s  status=%d",
                    event_type,
                    url,
                    delivery_id,
                    response_code,
                )
            else:
                _logger.warning(
                    "Webhook '%s' → %s  delivery=%s  non-2xx status=%d  body=%s",
                    event_type,
                    url,
                    delivery_id,
                    response_code,
                    response_body[:200],
                )

        except req_lib.exceptions.Timeout:
            error_message = "Request timed out after 30 seconds."
            _logger.warning(
                "Webhook '%s' timed out for API key '%s'.", event_type, self.name
            )

        except req_lib.exceptions.ConnectionError as exc:
            error_message = f"Connection error: {str(exc)[:500]}"
            _logger.warning(
                "Webhook '%s' connection error for API key '%s': %s",
                event_type,
                self.name,
                exc,
            )

        except req_lib.exceptions.RequestException as exc:
            error_message = f"HTTP request error: {str(exc)[:500]}"
            _logger.error(
                "Webhook '%s' request exception for API key '%s': %s",
                event_type,
                self.name,
                exc,
            )

        except Exception as exc:  # pragma: no cover — safety net
            error_message = f"Unexpected error: {str(exc)[:500]}"
            _logger.exception(
                "Unexpected webhook error for API key '%s', event '%s': %s",
                self.name,
                event_type,
                exc,
            )

        duration_ms = int((time.monotonic() - start_ts) * 1000)

        # --- Persist log record ----------------------------------------------
        # Use a savepoint so the log is written even if the outer transaction
        # is later rolled back by the caller.
        try:
            with self.env.cr.savepoint():
                self.env["alba.webhook.log"].sudo().create(
                    {
                        "api_key_id": self.id,
                        "direction": "outbound",
                        "event_type": event_type,
                        "payload": body_str,
                        "response_body": response_body,
                        "response_code": response_code,
                        "status": "success" if success else "failed",
                        "error_message": error_message,
                        "duration_ms": duration_ms,
                    }
                )
        except Exception as log_exc:
            _logger.error(
                "Failed to persist webhook log for event '%s': %s",
                event_type,
                log_exc,
            )

        return (success, response_code)
