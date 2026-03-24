# -*- coding: utf-8 -*-
"""
alba.mpesa.config — Daraja API configuration for Alba Capital.

This model stores every credential and URL needed to talk to Safaricom's
Daraja API.  One *active* record per company/environment is the expected
usage pattern.

Public surface
--------------
  AlbaMpesaConfig.get_active_config(company)     → config record | empty
  record.get_access_token()                       → str  (bearer token)
  record.stk_push(phone, amount, ref, desc)       → dict (Daraja response)
  record.query_stk_status(checkout_request_id)    → dict
  record.register_c2b_urls()                      → dict
  record.b2c_payment(phone, amount, occasion,
                     remarks, command_id)         → dict

Button actions (callable from the form view)
--------------------------------------------
  record.action_test_connection()
  record.action_register_c2b_urls()
"""

import base64
import json
import logging
from datetime import datetime, timedelta

import requests as http_client
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daraja base URLs
# ---------------------------------------------------------------------------
_DARAJA_URLS = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}

# Safaricom result codes that indicate a completed, successful transaction
_SUCCESS_CODES = {"0"}


class AlbaMpesaConfig(models.Model):
    """
    Daraja API configuration record.

    Stores all credentials, callback endpoints, and business codes required
    to interact with Safaricom's M-Pesa Daraja API on behalf of Alba Capital.

    Token caching
    -------------
    Safaricom issues OAuth tokens valid for 3 600 seconds (1 hour).  This
    model caches the current token + its expiry in transient class attributes
    so that every API call in the same Odoo worker process reuses the token
    instead of re-fetching it.  The cache is invalidated 60 seconds before
    the official expiry as a safety margin.

    Security note
    -------------
    Consumer secret and passkey are stored as plain ``Char`` fields.  In a
    hardened deployment you should:
      • Restrict the ``alba_loans.group_loan_manager`` group to the
        M-Pesa configuration menu.
      • Enable Odoo's field-level encryption if available in your edition.
      • Rotate credentials via the Daraja portal after any suspected leak.
    """

    _name = "alba.mpesa.config"
    _description = "Alba Capital M-Pesa Daraja Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "sequence asc, name asc"

    # =========================================================================
    # Fields
    # =========================================================================

    # ── Identity ──────────────────────────────────────────────────────────────

    name = fields.Char(
        string="Configuration Name",
        required=True,
        tracking=True,
        help=(
            'Human-readable label, e.g. "Alba Capital — Production Paybill" '
            'or "Alba Capital — Sandbox Testing".'
        ),
    )
    sequence = fields.Integer(
        string="Priority",
        default=10,
        help="Lower number = higher priority when calling get_active_config().",
    )
    is_active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help=(
            "Only active configurations are returned by get_active_config(). "
            "Deactivate instead of deleting to retain the audit trail."
        ),
    )
    environment = fields.Selection(
        selection=[
            ("sandbox", "Sandbox  (Safaricom testing environment)"),
            ("production", "Production  (Live — real money)"),
        ],
        string="Environment",
        required=True,
        default="sandbox",
        tracking=True,
        help=(
            "Sandbox uses https://sandbox.safaricom.co.ke.  "
            "Production uses https://api.safaricom.co.ke."
        ),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help="Restrict this configuration to a specific company.",
    )

    # ── Daraja OAuth Credentials ──────────────────────────────────────────────

    consumer_key = fields.Char(
        string="Consumer Key",
        required=True,
        help=(
            "Obtained from the Daraja developer portal "
            "(https://developer.safaricom.co.ke).  "
            "Used to generate OAuth bearer tokens."
        ),
    )
    consumer_secret = fields.Char(
        string="Consumer Secret",
        required=True,
        groups="alba_loans.group_loan_manager",
        help=(
            "Keep this value secret.  Combined with the Consumer Key to "
            "generate OAuth bearer tokens via Base64-encoded Basic auth."
        ),
    )

    # ── Business Short Codes ──────────────────────────────────────────────────

    shortcode = fields.Char(
        string="Business Short Code (Paybill)",
        required=True,
        tracking=True,
        help=(
            "Your M-Pesa Paybill number.  "
            "Sandbox default: 174379.  "
            "This is used as PartyB in STK Push and as the ShortCode for C2B."
        ),
    )
    till_number = fields.Char(
        string="Till Number (Buy Goods)",
        tracking=True,
        help=(
            "Optional.  If you accept payments via a Buy Goods Till, enter "
            "the till number here.  It is used as BusinessShortCode for "
            "Buy Goods STK Push requests."
        ),
    )
    account_type = fields.Selection(
        selection=[
            ("paybill", "Paybill"),
            ("till", "Buy Goods (Till)"),
        ],
        string="Default Payment Type",
        default="paybill",
        required=True,
        tracking=True,
        help=(
            "Determines whether STK Push uses the Paybill short code "
            "(CustomerPayBillOnline) or the Till number "
            "(CustomerBuyGoodsOnline) by default."
        ),
    )

    # ── STK Push (Lipa Na M-Pesa Online) ─────────────────────────────────────

    passkey = fields.Char(
        string="Lipa Na M-Pesa Passkey",
        groups="alba_loans.group_loan_manager",
        help=(
            "Passkey for STK Push transactions.  "
            "Provided by Safaricom when you register for Lipa Na M-Pesa.  "
            "Sandbox passkey: bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
        ),
    )
    stk_transaction_type = fields.Selection(
        selection=[
            ("CustomerPayBillOnline", "Paybill — CustomerPayBillOnline"),
            ("CustomerBuyGoodsOnline", "Buy Goods — CustomerBuyGoodsOnline"),
        ],
        string="STK Transaction Type",
        default="CustomerPayBillOnline",
        required=True,
        help=(
            "TransactionType sent with every STK Push request.  "
            "Must match your registered short code type."
        ),
    )

    # ── B2C (Business to Customer) ────────────────────────────────────────────

    initiator_name = fields.Char(
        string="B2C Initiator Username",
        help=(
            "The API operator username configured in the Daraja portal for "
            "B2C transactions.  Required for investor payouts."
        ),
    )
    initiator_security_credential = fields.Char(
        string="B2C Security Credential",
        groups="alba_loans.group_loan_manager",
        help=(
            "Encrypted credential for the B2C initiator.  Generate it by "
            "encrypting the initiator password with the Daraja production "
            "certificate via openssl."
        ),
    )
    b2c_default_command = fields.Selection(
        selection=[
            ("BusinessPayment", "Business Payment"),
            ("SalaryPayment", "Salary Payment"),
            ("PromotionPayment", "Promotion Payment"),
        ],
        string="B2C Default Command",
        default="BusinessPayment",
        help="Default CommandID used for B2C payouts if not overridden per call.",
    )

    # ── Callback / Webhook URLs ───────────────────────────────────────────────

    callback_base_url = fields.Char(
        string="Callback Base URL",
        required=True,
        tracking=True,
        help=(
            "Public HTTPS base URL of this Odoo instance, "
            "e.g. https://odoo.albacapital.co.ke.  "
            "Safaricom will POST callbacks to paths derived from this URL.  "
            "Must be reachable from the internet — localhost will not work "
            "with the production environment."
        ),
    )

    # Computed callback endpoints — displayed read-only on the form so the
    # operator can copy-paste them into the Daraja portal.
    stk_callback_url = fields.Char(
        string="STK Push Callback URL",
        compute="_compute_callback_urls",
        store=False,
    )
    c2b_validation_url = fields.Char(
        string="C2B Validation URL",
        compute="_compute_callback_urls",
        store=False,
    )
    c2b_confirmation_url = fields.Char(
        string="C2B Confirmation URL",
        compute="_compute_callback_urls",
        store=False,
    )
    b2c_result_url = fields.Char(
        string="B2C Result URL",
        compute="_compute_callback_urls",
        store=False,
    )
    b2c_queue_timeout_url = fields.Char(
        string="B2C Queue Timeout URL",
        compute="_compute_callback_urls",
        store=False,
    )

    # ── HTTP & Retry ──────────────────────────────────────────────────────────

    request_timeout = fields.Integer(
        string="HTTP Timeout (seconds)",
        default=30,
        help="Maximum seconds to wait for a Daraja API response.",
    )
    max_stk_retries = fields.Integer(
        string="Max STK Query Retries",
        default=3,
        help=(
            "How many times the system will re-query an STK Push status "
            "before marking the transaction as timed out."
        ),
    )

    # ── Notes ─────────────────────────────────────────────────────────────────

    notes = fields.Text(string="Internal Notes")

    # ── Computed helpers ──────────────────────────────────────────────────────

    transaction_count = fields.Integer(
        string="Transactions",
        compute="_compute_transaction_count",
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================

    _sql_constraints = [
        (
            "name_company_unique",
            "UNIQUE(name, company_id)",
            "A configuration with this name already exists for the same company.",
        ),
    ]

    # =========================================================================
    # Python-level constraints
    # =========================================================================

    @api.constrains("shortcode")
    def _check_shortcode(self):
        for rec in self:
            if rec.shortcode and not rec.shortcode.isdigit():
                raise ValidationError(
                    _("Business Short Code must contain digits only (e.g. 174379).")
                )

    @api.constrains("till_number")
    def _check_till_number(self):
        for rec in self:
            if rec.till_number and not rec.till_number.isdigit():
                raise ValidationError(_("Till Number must contain digits only."))

    @api.constrains("request_timeout")
    def _check_timeout(self):
        for rec in self:
            if rec.request_timeout < 5 or rec.request_timeout > 120:
                raise ValidationError(
                    _("HTTP timeout must be between 5 and 120 seconds.")
                )

    @api.constrains("callback_base_url")
    def _check_callback_base_url(self):
        for rec in self:
            url = (rec.callback_base_url or "").strip()
            if url and not (url.startswith("http://") or url.startswith("https://")):
                raise ValidationError(
                    _("Callback Base URL must start with http:// or https://.")
                )

    # =========================================================================
    # Computed methods
    # =========================================================================

    @api.depends("callback_base_url")
    def _compute_callback_urls(self):
        for rec in self:
            base = (rec.callback_base_url or "").rstrip("/")
            rec.stk_callback_url = f"{base}/alba/mpesa/stk/callback" if base else ""
            rec.c2b_validation_url = f"{base}/alba/mpesa/c2b/validation" if base else ""
            rec.c2b_confirmation_url = (
                f"{base}/alba/mpesa/c2b/confirmation" if base else ""
            )
            rec.b2c_result_url = f"{base}/alba/mpesa/b2c/result" if base else ""
            rec.b2c_queue_timeout_url = f"{base}/alba/mpesa/b2c/timeout" if base else ""

    def _compute_transaction_count(self):
        TxnModel = self.env["alba.mpesa.transaction"]
        for rec in self:
            rec.transaction_count = TxnModel.search_count([("config_id", "=", rec.id)])

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _get_base_url(self):
        """Return the Daraja root URL for the configured environment."""
        self.ensure_one()
        return _DARAJA_URLS.get(self.environment, _DARAJA_URLS["sandbox"])

    def _get_active_shortcode(self):
        """
        Return the short code to use in API calls.

        For Buy Goods transactions the Till number is used as the
        BusinessShortCode; for Paybill transactions the Paybill shortcode
        is used.
        """
        self.ensure_one()
        if self.account_type == "till" and self.till_number:
            return self.till_number
        return self.shortcode

    def _build_stk_password(self, timestamp: str) -> str:
        """
        Compute the Base64-encoded password for STK Push.

        Formula: Base64(shortcode + passkey + timestamp)

        Args:
            timestamp: YYYYMMDDHHmmss string.

        Returns:
            str: Base64-encoded password.

        Raises:
            UserError: When the passkey is not configured.
        """
        self.ensure_one()
        if not self.passkey:
            raise UserError(
                _(
                    "Lipa Na M-Pesa Passkey is not configured on '%s'. "
                    "Please update the M-Pesa configuration."
                )
                % self.name
            )
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    def _get_auth_headers(self) -> dict:
        """
        Return request headers that include a valid Bearer token.

        The token is fetched (or returned from cache) via get_access_token().
        """
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        """
        POST *payload* to *path* (relative to the Daraja base URL) and return
        the parsed JSON response body.

        Args:
            path:    URL path, e.g. "/mpesa/stkpush/v1/processrequest".
            payload: Dictionary to serialise as the request body.

        Returns:
            dict: Parsed Daraja response.

        Raises:
            UserError: On HTTP errors or non-JSON responses.
        """
        self.ensure_one()
        url = self._get_base_url().rstrip("/") + path
        _logger.debug("Daraja POST %s payload=%s", url, json.dumps(payload))
        try:
            resp = http_client.post(
                url,
                json=payload,
                headers=self._get_auth_headers(),
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except http_client.exceptions.HTTPError as exc:
            body = ""
            try:
                body = exc.response.text[:500]
            except Exception:
                pass
            _logger.error(
                "Daraja HTTP error %s %s — %s", exc.response.status_code, url, body
            )
            raise UserError(
                _("Daraja API error (HTTP %s): %s")
                % (exc.response.status_code, body or str(exc))
            ) from exc
        except http_client.exceptions.Timeout as exc:
            raise UserError(
                _("Daraja API timed out after %d seconds.") % self.request_timeout
            ) from exc
        except http_client.exceptions.ConnectionError as exc:
            raise UserError(
                _("Could not connect to Daraja API: %s") % str(exc)
            ) from exc
        except Exception as exc:
            raise UserError(
                _("Unexpected error calling Daraja API: %s") % str(exc)
            ) from exc

    # =========================================================================
    # Token management
    # =========================================================================

    # Class-level token cache keyed by (company_id, environment)
    # Structure: { cache_key: {"token": str, "expiry": datetime} }
    _token_cache: dict = {}

    def get_access_token(self) -> str:
        """
        Obtain a valid Daraja OAuth2 bearer token.

        Tokens issued by Safaricom are valid for 3 600 seconds.  This method
        caches the token (with a 60-second safety margin) in a class-level
        dictionary so that all Odoo worker threads for the same
        company+environment share the token and avoid unnecessary round-trips.

        Returns:
            str: Bearer token string.

        Raises:
            UserError: When credentials are missing or the token request fails.
        """
        self.ensure_one()
        if not self.consumer_key or not self.consumer_secret:
            raise UserError(
                _(
                    "Consumer Key and Consumer Secret must be set on the "
                    "M-Pesa configuration '%s' before making API calls."
                )
                % self.name
            )

        cache_key = (self.id, self.environment)
        now = datetime.utcnow()
        cached = AlbaMpesaConfig._token_cache.get(cache_key)
        if cached and now < cached["expiry"]:
            return cached["token"]

        # ── Fetch a fresh token ─────────────────────────────────────────────
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode("utf-8")
        ).decode("utf-8")
        url = self._get_base_url() + "/oauth/v1/generate?grant_type=client_credentials"
        _logger.info(
            "Fetching Daraja OAuth token for config '%s' (env=%s).",
            self.name,
            self.environment,
        )
        try:
            resp = http_client.get(
                url,
                headers={"Authorization": f"Basic {credentials}"},
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except http_client.exceptions.HTTPError as exc:
            body = ""
            try:
                body = exc.response.text[:400]
            except Exception:
                pass
            raise UserError(
                _("Failed to obtain Daraja token (HTTP %s): %s")
                % (exc.response.status_code, body or str(exc))
            ) from exc
        except Exception as exc:
            raise UserError(
                _("Unexpected error obtaining Daraja token: %s") % str(exc)
            ) from exc

        token = data.get("access_token", "").strip()
        if not token:
            raise UserError(
                _("Daraja OAuth endpoint did not return an access_token. Response: %s")
                % str(data)
            )

        # Cache for 55 minutes (token valid 60 min; 5-min safety margin)
        AlbaMpesaConfig._token_cache[cache_key] = {
            "token": token,
            "expiry": now + timedelta(minutes=55),
        }
        return token

    def action_clear_token_cache(self):
        """
        Manually clear the in-process token cache for this configuration.

        Useful after rotating credentials to force an immediate token refresh.
        """
        self.ensure_one()
        cache_key = (self.id, self.environment)
        AlbaMpesaConfig._token_cache.pop(cache_key, None)
        self.message_post(body=_("OAuth token cache cleared."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Cache Cleared"),
                "message": _("The next API call will fetch a fresh Daraja token."),
                "type": "info",
                "sticky": False,
            },
        }

    # =========================================================================
    # STK Push — Lipa Na M-Pesa Online
    # =========================================================================

    def stk_push(
        self,
        phone_number: str,
        amount: float,
        account_reference: str,
        transaction_desc: str,
    ) -> dict:
        """
        Initiate an STK Push (Lipa Na M-Pesa Online) payment prompt.

        Safaricom will send an on-screen payment prompt to the customer's
        phone.  The customer confirms with their M-Pesa PIN and Safaricom
        fires a callback to ``stk_callback_url`` with the result.

        Args:
            phone_number:      Customer's Safaricom number in 254XXXXXXXXX format.
                               Leading ``+`` and ``0`` prefixes are normalised
                               automatically.
            amount:            Exact amount in KES (must be a positive integer;
                               fractional parts are rounded up to the nearest
                               whole shilling as required by Daraja).
            account_reference: Shown to the customer on their phone.  Max 12
                               characters.  Typically the loan number.
            transaction_desc:  Short description shown in the prompt.  Max 13
                               characters.

        Returns:
            dict: Raw Daraja response body, e.g.::

                {
                    "MerchantRequestID": "...",
                    "CheckoutRequestID": "ws_CO_...",
                    "ResponseCode": "0",
                    "ResponseDescription": "Success. Request accepted for processing",
                    "CustomerMessage": "Success. Request accepted for processing"
                }

        Raises:
            UserError: On validation errors or Daraja API failures.
        """
        self.ensure_one()

        # ── Normalise phone ─────────────────────────────────────────────────
        phone = _normalise_phone(phone_number)

        # ── Validate amount ─────────────────────────────────────────────────
        int_amount = _to_whole_shillings(amount)

        # ── Build password ──────────────────────────────────────────────────
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        password = self._build_stk_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": self.stk_transaction_type,
            "Amount": int_amount,
            "PartyA": phone,
            "PartyB": self._get_active_shortcode(),
            "PhoneNumber": phone,
            "CallBackURL": self.stk_callback_url,
            "AccountReference": (account_reference or "")[:12].strip(),
            "TransactionDesc": (transaction_desc or "Loan Repayment")[:13].strip(),
        }

        _logger.info(
            "STK Push initiated: phone=%s amount=%d ref=%s",
            phone,
            int_amount,
            account_reference,
        )
        return self._post("/mpesa/stkpush/v1/processrequest", payload)

    def query_stk_status(self, checkout_request_id: str) -> dict:
        """
        Query the processing status of a previously initiated STK Push.

        Args:
            checkout_request_id: The ``CheckoutRequestID`` string returned by
                                 :meth:`stk_push`.

        Returns:
            dict: Daraja query response.  ``ResultCode == "0"`` indicates
                  the payment completed successfully.

        Raises:
            UserError: On validation errors or Daraja API failures.
        """
        self.ensure_one()
        if not checkout_request_id:
            raise UserError(_("checkout_request_id must not be empty."))
        if not self.passkey:
            raise UserError(_("Passkey is not configured on '%s'.") % self.name)

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        password = self._build_stk_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        return self._post("/mpesa/stkpushquery/v1/query", payload)

    # =========================================================================
    # C2B — Customer to Business (Paybill / Till)
    # =========================================================================

    def register_c2b_urls(self) -> dict:
        """
        Register the C2B validation and confirmation callback URLs with
        Safaricom.  This must be called once (or whenever the Odoo URL
        changes) before C2B payments are processed.

        Returns:
            dict: Daraja registration response.

        Raises:
            UserError: When callback_base_url is not set or the API call fails.
        """
        self.ensure_one()
        if not self.callback_base_url:
            raise UserError(
                _(
                    "Callback Base URL is not set on configuration '%s'. "
                    "Please enter the public HTTPS URL of this Odoo instance."
                )
                % self.name
            )

        payload = {
            "ShortCode": self.shortcode,
            "ResponseType": "Completed",
            "ConfirmationURL": self.c2b_confirmation_url,
            "ValidationURL": self.c2b_validation_url,
        }
        result = self._post("/mpesa/c2b/v1/registerurl", payload)
        self.message_post(
            body=_(
                "C2B URLs registered with Safaricom.<br/>"
                "Confirmation URL: <code>%s</code><br/>"
                "Validation URL: <code>%s</code><br/>"
                "Daraja response: <code>%s</code>"
            )
            % (
                self.c2b_confirmation_url,
                self.c2b_validation_url,
                json.dumps(result),
            )
        )
        _logger.info(
            "C2B URLs registered for config '%s': %s",
            self.name,
            result,
        )
        return result

    # =========================================================================
    # B2C — Business to Customer (investor / customer payouts)
    # =========================================================================

    def b2c_payment(
        self,
        phone_number: str,
        amount: float,
        occasion: str,
        remarks: str,
        command_id: str = None,
    ) -> dict:
        """
        Initiate a B2C (Business to Customer) payment.

        Used primarily for investor interest payouts and loan refunds.

        Args:
            phone_number: Recipient's phone in 254XXXXXXXXX format.
            amount:       Amount in KES.
            occasion:     Short label shown in the Daraja portal (max 100 chars).
            remarks:      Short remarks for the transaction (max 100 chars).
            command_id:   One of ``BusinessPayment``, ``SalaryPayment``,
                          ``PromotionPayment``.  Defaults to the value
                          configured on the record.

        Returns:
            dict: Daraja B2C initiation response.  A successful submission
                  returns ``ResponseCode == "0"``; the *actual* result is
                  delivered asynchronously via the B2C result URL callback.

        Raises:
            UserError: When B2C credentials are missing or the API call fails.
        """
        self.ensure_one()
        if not self.initiator_name or not self.initiator_security_credential:
            raise UserError(
                _(
                    "B2C Initiator Username and Security Credential must be "
                    "configured on '%s' before initiating payouts."
                )
                % self.name
            )

        phone = _normalise_phone(phone_number)
        int_amount = _to_whole_shillings(amount)
        cmd = command_id or self.b2c_default_command

        payload = {
            "InitiatorName": self.initiator_name,
            "SecurityCredential": self.initiator_security_credential,
            "CommandID": cmd,
            "Amount": int_amount,
            "PartyA": self.shortcode,
            "PartyB": phone,
            "Remarks": (remarks or "")[:100].strip(),
            "QueueTimeOutURL": self.b2c_queue_timeout_url,
            "ResultURL": self.b2c_result_url,
            "Occasion": (occasion or "")[:100].strip(),
        }

        _logger.info(
            "B2C payment initiated: phone=%s amount=%d cmd=%s occasion=%s",
            phone,
            int_amount,
            cmd,
            occasion,
        )
        return self._post("/mpesa/b2c/v1/paymentrequest", payload)

    # =========================================================================
    # Class-level helpers
    # =========================================================================

    @api.model
    def get_active_config(self, company=None):
        """
        Return the highest-priority active M-Pesa configuration for *company*.

        Args:
            company (res.company | None): Defaults to the current company.

        Returns:
            alba.mpesa.config: Matched record, or empty recordset when none
                               is configured.

        Example::

            config = self.env["alba.mpesa.config"].get_active_config()
            if config:
                result = config.stk_push(phone, amount, ref, desc)
        """
        company = company or self.env.company
        return self.sudo().search(
            [("is_active", "=", True), ("company_id", "=", company.id)],
            order="sequence asc, id asc",
            limit=1,
        )

    # =========================================================================
    # ORM overrides
    # =========================================================================

    def write(self, vals):
        """Clear token cache when credentials change."""
        cred_fields = {"consumer_key", "consumer_secret", "environment"}
        if cred_fields & set(vals.keys()):
            for rec in self:
                AlbaMpesaConfig._token_cache.pop((rec.id, rec.environment), None)
        return super().write(vals)

    # =========================================================================
    # Button / action methods
    # =========================================================================

    def action_test_connection(self):
        """
        Verify Daraja connectivity by fetching an OAuth token.

        Displays a success or failure notification so the operator can
        immediately know whether the credentials are correct.
        """
        self.ensure_one()
        # Force cache miss so we always hit the network
        AlbaMpesaConfig._token_cache.pop((self.id, self.environment), None)
        try:
            token = self.get_access_token()
            msg = (
                _("Connection successful!  Daraja token received (first 8 chars: %s…).")
                % token[:8]
            )
            notif_type = "success"
            title = _("Daraja Connection OK")
            self.message_post(
                body=_(
                    "Connection test passed — Daraja token obtained for "
                    "environment <b>%s</b>."
                )
                % self.environment
            )
        except UserError as exc:
            msg = str(exc)
            notif_type = "danger"
            title = _("Daraja Connection Failed")
            self.message_post(body=_("Connection test <b>failed</b>: %s") % msg)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": msg,
                "type": notif_type,
                "sticky": notif_type == "danger",
            },
        }

    def action_register_c2b_urls(self):
        """
        Button action: register C2B validation and confirmation URLs with
        Safaricom and display the result as a notification.
        """
        self.ensure_one()
        try:
            result = self.register_c2b_urls()
            msg = _("C2B URLs registered.  Daraja response: %s") % json.dumps(result)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("C2B URLs Registered"),
                    "message": msg,
                    "type": "success",
                    "sticky": False,
                },
            }
        except UserError as exc:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("C2B Registration Failed"),
                    "message": str(exc),
                    "type": "danger",
                    "sticky": True,
                },
            }

    def action_view_transactions(self):
        """Open the M-Pesa transaction log filtered to this configuration."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("M-Pesa Transactions — %s") % self.name,
            "res_model": "alba.mpesa.transaction",
            "view_mode": "list,form",
            "domain": [("config_id", "=", self.id)],
            "context": {"default_config_id": self.id},
        }


# =============================================================================
# Module-level utility functions
# =============================================================================


def _normalise_phone(raw: str) -> str:
    """
    Normalise a Kenyan phone number to the 254XXXXXXXXX format required by
    the Daraja API.

    Accepted input formats:
      • ``0712345678``   → ``254712345678``
      • ``+254712345678`` → ``254712345678``
      • ``254712345678`` → ``254712345678`` (no-op)
      • ``712345678``    → ``254712345678``

    Args:
        raw: Phone number string (spaces and hyphens are stripped).

    Returns:
        str: Normalised phone number.

    Raises:
        UserError: When the result does not look like a valid Kenyan number.
    """
    if not raw:
        raise UserError(_("Phone number must not be empty."))

    phone = raw.strip().replace(" ", "").replace("-", "")

    if phone.startswith("+"):
        phone = phone[1:]

    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
    elif len(phone) == 9 and not phone.startswith("254"):
        phone = "254" + phone

    # Basic sanity: must be 12 digits starting with 2547 or 2541
    if not phone.isdigit() or len(phone) != 12 or not phone.startswith("254"):
        raise UserError(
            _(
                "Invalid phone number '%s'. "
                "Please use the format 0712345678 or 254712345678."
            )
            % raw
        )
    return phone


def _to_whole_shillings(amount: float) -> int:
    """
    Convert *amount* to a whole-number integer as required by Daraja.

    Daraja rejects fractional amounts, so we round up to the nearest shilling.

    Args:
        amount: Monetary amount (float or Decimal).

    Returns:
        int: Amount rounded up to the nearest whole shilling.

    Raises:
        UserError: When amount is zero or negative.
    """
    import math

    value = math.ceil(float(amount))
    if value <= 0:
        raise UserError(_("Payment amount must be greater than zero. Got: %s") % amount)
    return value
