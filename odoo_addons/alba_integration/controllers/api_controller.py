# -*- coding: utf-8 -*-
"""
AlbaApiController — REST API endpoints exposed to the Django customer portal.

All routes live under /alba/api/v1/ and are authenticated via the
X-Alba-API-Key HTTP header.  Every handler uses type='http' so that Odoo's
JSON-RPC envelope is bypassed and we retain full control over request parsing
and response serialisation.

Endpoint map
------------
GET  /alba/api/v1/health                          — liveness probe (no auth)
GET  /alba/api/v1/loan-products                   — list active loan products
POST /alba/api/v1/customers                       — create or update customer
POST /alba/api/v1/customers/<customer_id>/kyc     — update KYC status
POST /alba/api/v1/applications                    — create loan application
PATCH /alba/api/v1/applications/<application_id>/status  — update app status
POST /alba/api/v1/payments                        — record a repayment

Authentication
--------------
Every request (except /health) must carry a valid, active API-key value in the
``X-Alba-API-Key`` header.  The helper ``_authenticate()`` raises
``AccessDenied`` on failure; each handler converts that to HTTP 403.

Outbound webhooks
-----------------
Certain state transitions automatically fire HMAC-signed webhook POSTs back to
the Django portal via ``api_key.send_webhook(event_type, payload_dict)``.
"""

import json
import logging
import time
from datetime import date, datetime

from odoo import _, fields, http
from odoo import exceptions as odoo_exceptions
from odoo.http import request
from werkzeug.wrappers import Response as WerkzeugResponse

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_API_VERSION = "1.0"
_SERVICE_NAME = "alba-odoo"

# Mapping from generic status strings (sent by Django) to Odoo state values
# and the corresponding action method names on alba.loan.application.
_STATUS_ACTION_MAP = {
    "submitted": ("submitted", "action_submit"),
    "under_review": ("under_review", "action_review"),
    "credit_analysis": ("credit_analysis", "action_credit_analysis"),
    "pending_approval": ("pending_approval", "action_pending_approval"),
    "approved": ("approved", "action_approve"),
    "employer_verification": ("employer_verification", "action_employer_verification"),
    "guarantor_confirmation": (
        "guarantor_confirmation",
        "action_guarantor_confirmation",
    ),
    "disbursed": ("disbursed", "action_disburse"),
    "rejected": ("rejected", "action_reject"),
    "cancelled": ("cancelled", "action_cancel"),
}

# Normalise Django payment_method strings to Odoo selection values
_PAYMENT_METHOD_MAP = {
    "bank_transfer": "bank_transfer",
    "banktransfer": "bank_transfer",
    "bank": "bank_transfer",
    "mpesa": "mpesa",
    "m_pesa": "mpesa",
    "m-pesa": "mpesa",
    "mobile_money": "mpesa",
    "cash": "cash",
    "cheque": "cheque",
    "check": "cheque",
    "direct_debit": "direct_debit",
    "directdebit": "direct_debit",
    "debit": "direct_debit",
}


class AlbaApiController(http.Controller):
    """
    HTTP controller exposing the Alba Capital REST integration API.

    All route handlers follow a uniform pattern:
      1. Authenticate via ``_authenticate()``.
      2. Parse the JSON request body via ``_parse_json_body()``.
      3. Validate required fields.
      4. Execute business logic using ``sudo()`` (public auth user).
      5. Fire outbound webhooks where applicable.
      6. Return a structured JSON response.

    Private helpers (_authenticate, _json_response, _error_response, etc.) are
    intentionally not prefixed with ``@http.route`` so Odoo does not register
    them as routable endpoints.
    """

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _authenticate(self):
        """
        Extract and validate the API key from the ``X-Alba-API-Key`` request
        header.

        On success, the ``alba.api.key`` record is returned and its
        ``last_used`` timestamp is updated.

        Raises:
            odoo.exceptions.AccessDenied: When the header is missing, the key
                does not match an active record, or the caller's IP address is
                not in the key's allowlist.

        Returns:
            alba.api.key: The matched, active API key record (with sudo).
        """
        raw_key = request.httprequest.headers.get("X-Alba-API-Key", "").strip()
        if not raw_key:
            raise odoo_exceptions.AccessDenied(_("Missing X-Alba-API-Key header."))

        api_key = request.env["alba.api.key"].sudo().verify_key(raw_key)
        if not api_key:
            raise odoo_exceptions.AccessDenied(_("Invalid or inactive API key."))

        # Optional IP allowlist enforcement
        if api_key.allowed_ips:
            remote_ip = (
                request.httprequest.environ.get("HTTP_X_FORWARDED_FOR", "")
                .split(",")[0]
                .strip()
                or request.httprequest.remote_addr
                or ""
            )
            allowed_set = {
                ip.strip() for ip in api_key.allowed_ips.split(",") if ip.strip()
            }
            if allowed_set and remote_ip not in allowed_set:
                _logger.warning(
                    "API key '%s': rejected request from IP %s (allowlist: %s)",
                    api_key.name,
                    remote_ip,
                    api_key.allowed_ips,
                )
                raise odoo_exceptions.AccessDenied(
                    _("Access denied: your IP address is not in the allowed list.")
                )

        return api_key

    @staticmethod
    def _parse_json_body():
        """
        Safely parse the HTTP request body as JSON.

        Tries ``request.get_json_data()`` first (available in Odoo 16.3+),
        then falls back to manually decoding ``request.httprequest.data``.

        Returns:
            dict: Parsed body, or empty dict when the body is absent / invalid.
        """
        # Odoo 16.3+ convenience method
        if hasattr(request, "get_json_data"):
            try:
                data = request.get_json_data()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass  # Fall through to manual parsing

        raw = request.httprequest.data
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
            _logger.debug("_parse_json_body: failed to parse request body — %s", exc)
            return {}

    @staticmethod
    def _json_response(data, status=200):
        """
        Construct a JSON HTTP response with the correct Content-Type header.

        ``datetime``, ``date``, and any other non-serialisable values are
        coerced to strings via ``default=str``.

        Args:
            data (dict | list): JSON-serialisable payload.
            status (int): HTTP status code.

        Returns:
            werkzeug.wrappers.Response
        """
        body = json.dumps(data, default=str, ensure_ascii=False)
        return WerkzeugResponse(
            response=body,
            status=status,
            mimetype="application/json",
            headers=[
                ("Content-Type", "application/json; charset=utf-8"),
                ("X-Alba-Service", _SERVICE_NAME),
                ("X-Alba-Version", _API_VERSION),
            ],
        )

    @staticmethod
    def _error_response(message, status=400, details=None):
        """
        Construct a structured JSON error response.

        Args:
            message (str): Human-readable error description.
            status (int): HTTP status code (4xx / 5xx).
            details (dict | None): Optional additional diagnostic data.

        Returns:
            werkzeug.wrappers.Response
        """
        payload = {
            "error": message,
            "status": status,
        }
        if details:
            payload["details"] = details
        body = json.dumps(payload, default=str, ensure_ascii=False)
        return WerkzeugResponse(
            response=body,
            status=status,
            mimetype="application/json",
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @staticmethod
    def _get_or_create_partner(customer_data):
        """
        Find an existing ``res.partner`` by email, or create one from the
        supplied *customer_data* dict.  When a match is found the partner's
        name, phone, and email are synchronised.

        Args:
            customer_data (dict): Django customer payload with at minimum
                ``email``, ``first_name``, and ``last_name``.

        Returns:
            res.partner: Matched or newly created partner record.
        """
        Partner = request.env["res.partner"].sudo()

        email = (customer_data.get("email") or "").strip().lower()
        first_name = (customer_data.get("first_name") or "").strip()
        last_name = (customer_data.get("last_name") or "").strip()
        full_name = f"{first_name} {last_name}".strip() or email or "Unknown Customer"
        phone = (customer_data.get("phone") or "").strip()

        partner_vals = {
            "name": full_name,
            "email": email,
            "phone": phone,
            "is_company": False,
            "customer_rank": 1,
            "lang": "en_US",
        }

        partner = None
        if email:
            partner = Partner.search([("email", "=ilike", email)], limit=1)

        if partner:
            partner.write(partner_vals)
        else:
            partner = Partner.create(partner_vals)

        return partner

    @staticmethod
    def _safe_float(value, default=0.0):
        """Convert *value* to float, returning *default* on failure."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value, default=0):
        """Convert *value* to int, returning *default* on failure."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _validate_required(data, required_fields):
        """
        Check that every field name in *required_fields* is present and
        non-empty in *data*.

        Returns:
            list[str]: Names of fields that are missing or blank.
        """
        return [f for f in required_fields if not data.get(f) and data.get(f) != 0]

    # =========================================================================
    # Route handlers
    # =========================================================================

    # -------------------------------------------------------------------------
    # 1. Health check — no authentication required
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/health",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def health_check(self, **kwargs):
        """
        Liveness / readiness probe for the integration layer.

        No API key is required.  Returns a minimal JSON body that the Django
        portal (or a load-balancer health check) can use to confirm that the
        Odoo instance is running and the integration module is installed.

        Response 200
        ------------
        .. code-block:: json

            {
                "status": "ok",
                "version": "1.0",
                "service": "alba-odoo",
                "timestamp": "2024-01-15T12:00:00+00:00"
            }
        """
        from datetime import timezone

        return self._json_response(
            {
                "status": "ok",
                "version": _API_VERSION,
                "service": _SERVICE_NAME,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    # -------------------------------------------------------------------------
    # 2. List active loan products
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/loan-products",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def list_loan_products(self, **kwargs):
        """
        Return all active loan products as a JSON array.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        Response 200
        ------------
        .. code-block:: json

            {
                "products": [
                    {
                        "id": 1,
                        "name": "Business Loan",
                        "code": "BL-001",
                        "category": "business_loan",
                        "min_amount": 10000.0,
                        "max_amount": 500000.0,
                        "interest_rate": 3.5,
                        "interest_method": "reducing_balance",
                        "min_tenure_months": 3,
                        "max_tenure_months": 24,
                        "repayment_frequency": "monthly"
                    }
                ],
                "count": 1
            }
        """
        try:
            self._authenticate()

            products = (
                request.env["alba.loan.product"]
                .sudo()
                .search([("is_active", "=", True)], order="name asc")
            )

            result = []
            for p in products:
                result.append(
                    {
                        "id": p.id,
                        "name": p.name or "",
                        "code": p.code or "",
                        "category": p.category or "",
                        "min_amount": self._safe_float(p.min_amount),
                        "max_amount": self._safe_float(p.max_amount),
                        "interest_rate": self._safe_float(p.interest_rate),
                        "interest_method": p.interest_method or "",
                        "min_tenure_months": self._safe_int(p.min_tenure_months, 1),
                        "max_tenure_months": self._safe_int(p.max_tenure_months, 12),
                        "repayment_frequency": p.repayment_frequency or "monthly",
                    }
                )

            return self._json_response({"products": result, "count": len(result)})

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except Exception as exc:
            _logger.exception("list_loan_products: unexpected error — %s", exc)
            return self._error_response("Internal server error.", 500)

    # -------------------------------------------------------------------------
    # 3. Create or update customer
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/customers",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def create_or_update_customer(self, **kwargs):
        """
        Create or update an Odoo customer record from a Django portal customer.

        The caller must supply ``django_customer_id`` so Odoo can detect
        subsequent update calls and avoid creating duplicates.  Lookup order:
          1. Match ``alba.customer.django_customer_id`` exactly.
          2. If not found, search ``res.partner`` by email; if a matching
             partner already has an ``alba.customer`` record, use it.
          3. If still not found, create a new ``res.partner`` +
             ``alba.customer`` pair.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        Request body (JSON)
        -------------------
        Required: ``django_customer_id``, ``email``, ``first_name``,
        ``last_name``, ``phone``

        Optional: ``id_number``, ``id_type``, ``date_of_birth``, ``gender``,
        ``employment_status``, ``monthly_income``

        Response 200 / 201
        ------------------
        .. code-block:: json

            {
                "odoo_customer_id": 42,
                "odoo_partner_id": 100,
                "status": "created"
            }
        """
        try:
            api_key = self._authenticate()
            data = self._parse_json_body()

            missing = self._validate_required(
                data, ["django_customer_id", "email", "first_name", "last_name"]
            )
            if missing:
                return self._error_response(
                    f"Missing required fields: {', '.join(missing)}", 400
                )

            django_customer_id = str(data["django_customer_id"]).strip()
            Customer = request.env["alba.customer"].sudo()

            # --- Locate existing record --------------------------------------
            customer = Customer.search(
                [("django_customer_id", "=", django_customer_id)], limit=1
            )

            # Fallback: search by partner email
            if not customer and data.get("email"):
                email_norm = data["email"].strip().lower()
                partner_match = (
                    request.env["res.partner"]
                    .sudo()
                    .search([("email", "=ilike", email_norm)], limit=1)
                )
                if partner_match:
                    customer = Customer.search(
                        [("partner_id", "=", partner_match.id)], limit=1
                    )

            # --- Sync res.partner -------------------------------------------
            partner = self._get_or_create_partner(data)

            # --- Build customer field dict ----------------------------------
            customer_vals = {
                "django_customer_id": django_customer_id,
                "partner_id": partner.id,
            }

            # Optional KYC / personal fields — only write when supplied
            optional_map = {
                "id_number": "id_number",
                "id_type": "id_type",
                "date_of_birth": "date_of_birth",
                "gender": "gender",
                "employment_status": "employment_status",
                "monthly_income": "monthly_income",
                "employer_name": "employer_name",
                "bank_name": "bank_name",
                "bank_account": "bank_account",
                "county": "county",
                "city": "city",
            }
            for django_field, odoo_field in optional_map.items():
                val = data.get(django_field)
                if val is not None and val != "":
                    customer_vals[odoo_field] = val

            # --- Persist -----------------------------------------------------
            if customer:
                customer.write(customer_vals)
                status = "updated"
                http_status = 200
            else:
                customer = Customer.create(customer_vals)
                status = "created"
                http_status = 201

            _logger.info(
                "create_or_update_customer: django_id=%s odoo_id=%d status=%s",
                django_customer_id,
                customer.id,
                status,
            )

            return self._json_response(
                {
                    "odoo_customer_id": customer.id,
                    "odoo_partner_id": partner.id,
                    "status": status,
                },
                status=http_status,
            )

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except odoo_exceptions.UserError as exc:
            return self._error_response(str(exc), 400)
        except Exception as exc:
            _logger.exception("create_or_update_customer: unexpected error — %s", exc)
            return self._error_response("Internal server error.", 500)

    # -------------------------------------------------------------------------
    # 4. Update KYC status
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/customers/<int:customer_id>/kyc",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def update_kyc_status(self, customer_id, **kwargs):
        """
        Update the KYC (Know Your Customer) status of an Odoo customer record.

        When *kyc_status* is set to ``"verified"`` an outbound webhook
        ``customer.kyc_verified`` is fired to the Django portal.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        URL parameter
        -------------
        ``customer_id`` — Odoo database ID of the ``alba.customer`` record.

        Request body (JSON)
        -------------------
        Required: ``kyc_status``  (one of: pending / submitted / verified / rejected)

        Optional: ``verified_by``, ``verification_notes``, ``document_ids``

        Response 200
        ------------
        .. code-block:: json

            {
                "status": "updated",
                "kyc_status": "verified",
                "odoo_customer_id": 42
            }
        """
        try:
            api_key = self._authenticate()
            data = self._parse_json_body()

            kyc_status = (data.get("kyc_status") or "").strip()
            if not kyc_status:
                return self._error_response("Missing required field: kyc_status", 400)

            valid_statuses = {"pending", "submitted", "verified", "rejected"}
            if kyc_status not in valid_statuses:
                return self._error_response(
                    f"Invalid kyc_status '{kyc_status}'. "
                    f"Allowed values: {', '.join(sorted(valid_statuses))}.",
                    400,
                )

            customer = request.env["alba.customer"].sudo().browse(customer_id)
            if not customer.exists():
                return self._error_response(
                    f"Customer with id={customer_id} not found.", 404
                )

            update_vals = {"kyc_status": kyc_status}

            # Record verification timestamp when marking as verified
            if kyc_status == "verified":
                from datetime import timezone

                update_vals["kyc_verified_at"] = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            # Persist optional notes
            if data.get("verification_notes"):
                update_vals["kyc_notes"] = data["verification_notes"]

            customer.write(update_vals)

            _logger.info(
                "update_kyc_status: customer_id=%d kyc_status=%s",
                customer_id,
                kyc_status,
            )

            # Fire outbound webhook on verification
            if kyc_status == "verified":
                from datetime import timezone

                partner = customer.partner_id
                api_key.send_webhook(
                    "customer.kyc_verified",
                    {
                        "odoo_customer_id": customer.id,
                        "django_customer_id": customer.django_customer_id or "",
                        "customer_name": partner.name if partner else "",
                        "customer_email": partner.email if partner else "",
                        "kyc_status": kyc_status,
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            return self._json_response(
                {
                    "status": "updated",
                    "kyc_status": kyc_status,
                    "odoo_customer_id": customer.id,
                }
            )

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except odoo_exceptions.UserError as exc:
            return self._error_response(str(exc), 400)
        except Exception as exc:
            _logger.exception("update_kyc_status: unexpected error — %s", exc)
            return self._error_response("Internal server error.", 500)

    # -------------------------------------------------------------------------
    # 5. Create loan application
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/applications",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def create_application(self, **kwargs):
        """
        Create a new loan application in Odoo from a Django portal submission.

        The call is fully idempotent: if an ``alba.loan.application`` with the
        given ``django_application_id`` already exists the existing record is
        returned with ``status: "exists"`` rather than creating a duplicate.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        Request body (JSON)
        -------------------
        Required: ``django_application_id``, ``django_customer_id``,
        ``loan_product_code``, ``requested_amount``, ``tenure_months``

        Optional: ``repayment_frequency``, ``purpose``

        Response 201
        ------------
        .. code-block:: json

            {
                "odoo_application_id": 7,
                "application_number": "APP-20240115-0001",
                "status": "created"
            }
        """
        try:
            self._authenticate()
            data = self._parse_json_body()

            missing = self._validate_required(
                data,
                [
                    "django_application_id",
                    "django_customer_id",
                    "loan_product_code",
                    "requested_amount",
                    "tenure_months",
                ],
            )
            if missing:
                return self._error_response(
                    f"Missing required fields: {', '.join(missing)}", 400
                )

            django_app_id = str(data["django_application_id"]).strip()
            django_cust_id = str(data["django_customer_id"]).strip()

            Application = request.env["alba.loan.application"].sudo()

            # --- Idempotency: check for existing application -----------------
            existing = Application.search(
                [("django_application_id", "=", django_app_id)], limit=1
            )
            if existing:
                _logger.info(
                    "create_application: duplicate detected django_app_id=%s "
                    "odoo_id=%d — returning existing.",
                    django_app_id,
                    existing.id,
                )
                return self._json_response(
                    {
                        "odoo_application_id": existing.id,
                        "application_number": existing.application_number or "",
                        "status": "exists",
                    }
                )

            # --- Resolve customer -------------------------------------------
            customer = (
                request.env["alba.customer"]
                .sudo()
                .search([("django_customer_id", "=", django_cust_id)], limit=1)
            )
            if not customer:
                return self._error_response(
                    f"Customer with django_customer_id='{django_cust_id}' not found. "
                    "Create the customer record first via POST /alba/api/v1/customers.",
                    404,
                )

            # --- Resolve loan product ----------------------------------------
            product = (
                request.env["alba.loan.product"]
                .sudo()
                .search(
                    [
                        ("code", "=", data["loan_product_code"]),
                        ("is_active", "=", True),
                    ],
                    limit=1,
                )
            )
            if not product:
                return self._error_response(
                    f"Active loan product with code='{data['loan_product_code']}' "
                    "not found.",
                    404,
                )

            # Determine repayment frequency — fallback to product default
            repayment_freq = (
                data.get("repayment_frequency") or ""
            ).strip().lower() or (product.repayment_frequency or "monthly")

            app_vals = {
                "django_application_id": django_app_id,
                "customer_id": customer.id,
                "product_id": product.id,
                "requested_amount": self._safe_float(data["requested_amount"]),
                "tenure_months": self._safe_int(data["tenure_months"], 1),
                "repayment_frequency": repayment_freq,
                "purpose": (data.get("purpose") or "").strip(),
                "state": "draft",
            }

            application = Application.create(app_vals)

            _logger.info(
                "create_application: created odoo_id=%d number=%s django_app_id=%s",
                application.id,
                application.application_number,
                django_app_id,
            )

            return self._json_response(
                {
                    "odoo_application_id": application.id,
                    "application_number": application.application_number or "",
                    "status": "created",
                },
                status=201,
            )

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except odoo_exceptions.UserError as exc:
            return self._error_response(str(exc), 400)
        except Exception as exc:
            _logger.exception("create_application: unexpected error — %s", exc)
            return self._error_response("Internal server error.", 500)

    # -------------------------------------------------------------------------
    # 6. Update application status
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/applications/<int:application_id>/status",
        type="http",
        auth="public",
        methods=["PATCH", "POST"],
        csrf=False,
    )
    def update_application_status(self, application_id, **kwargs):
        """
        Advance or change the workflow state of a loan application.

        The handler maps the *new_status* string to a named action method on
        ``alba.loan.application`` (e.g. ``action_approve``).  If the model
        does not expose that action (older alba_loans version), it falls back
        to a direct ``write({'state': new_status})`` — with a warning log.

        After a successful transition an ``application.status_changed`` webhook
        is fired to the Django portal.  When the new status is ``"disbursed"``
        an additional ``loan.disbursed`` webhook is also fired.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        URL parameter
        -------------
        ``application_id`` — Odoo database ID of the ``alba.loan.application``.

        Request body (JSON)
        -------------------
        Required: ``new_status``
        Optional: ``notes``

        Response 200
        ------------
        .. code-block:: json

            {
                "status": "updated",
                "previous_state": "pending_approval",
                "new_state": "approved",
                "application_number": "APP-20240115-0001"
            }
        """
        try:
            api_key = self._authenticate()
            data = self._parse_json_body()

            new_status = (data.get("new_status") or "").strip().lower()
            if not new_status:
                return self._error_response("Missing required field: new_status", 400)

            if new_status not in _STATUS_ACTION_MAP:
                return self._error_response(
                    f"Unknown status '{new_status}'. "
                    f"Allowed values: {', '.join(sorted(_STATUS_ACTION_MAP))}.",
                    400,
                )

            application = (
                request.env["alba.loan.application"].sudo().browse(application_id)
            )
            if not application.exists():
                return self._error_response(
                    f"Application with id={application_id} not found.", 404
                )

            previous_state = application.state
            odoo_state_value, action_method_name = _STATUS_ACTION_MAP[new_status]
            notes = (data.get("notes") or "").strip()

            # Append notes to internal_notes if provided
            if notes:
                existing_notes = application.internal_notes or ""
                separator = "\n\n" if existing_notes else ""
                from datetime import timezone

                note_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                application.write(
                    {
                        "internal_notes": (
                            f"{existing_notes}{separator}"
                            f"[{note_ts}] Django status update → {new_status}:\n{notes}"
                        )
                    }
                )

            # Attempt named action method first, fall back to direct write
            if hasattr(application, action_method_name):
                try:
                    getattr(application, action_method_name)()
                except (
                    odoo_exceptions.UserError,
                    odoo_exceptions.ValidationError,
                ) as exc:
                    return self._error_response(
                        f"Cannot transition to '{new_status}': {exc}", 400
                    )
            else:
                _logger.warning(
                    "update_application_status: action '%s' not found on "
                    "alba.loan.application — falling back to direct state write.",
                    action_method_name,
                )
                try:
                    application.write({"state": odoo_state_value})
                except Exception as exc:
                    return self._error_response(
                        f"Cannot set state to '{new_status}': {exc}", 400
                    )

            # Refresh the record so we read the post-transition state
            application.invalidate_recordset()
            new_state = application.state

            _logger.info(
                "update_application_status: id=%d %s → %s",
                application_id,
                previous_state,
                new_state,
            )

            # --- Fire application.status_changed webhook --------------------
            webhook_payload = {
                "odoo_application_id": application.id,
                "application_number": application.application_number or "",
                "django_application_id": application.django_application_id or "",
                "previous_state": previous_state,
                "new_state": new_state,
                "notes": notes,
            }
            api_key.send_webhook("application.status_changed", webhook_payload)

            # Also fire loan.disbursed when the application reaches disbursed state
            if new_state == "disbursed":
                loan = getattr(application, "loan_id", None)
                api_key.send_webhook(
                    "loan.disbursed",
                    {
                        "odoo_application_id": application.id,
                        "application_number": application.application_number or "",
                        "django_application_id": application.django_application_id
                        or "",
                        "loan_number": loan.loan_number if loan else "",
                        "odoo_loan_id": loan.id if loan else 0,
                        "disbursed_amount": self._safe_float(
                            getattr(application, "approved_amount", None)
                            or getattr(application, "requested_amount", 0)
                        ),
                    },
                )

            return self._json_response(
                {
                    "status": "updated",
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "application_number": application.application_number or "",
                }
            )

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except odoo_exceptions.UserError as exc:
            return self._error_response(str(exc), 400)
        except Exception as exc:
            _logger.exception(
                "update_application_status: unexpected error for id=%d — %s",
                application_id,
                exc,
            )
            return self._error_response("Internal server error.", 500)

    # -------------------------------------------------------------------------
    # 7. Record payment / repayment
    # -------------------------------------------------------------------------

    @http.route(
        "/alba/api/v1/payments",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def record_payment(self, **kwargs):
        """
        Record a loan repayment that originated in the Django portal or via
        M-Pesa / bank integration.

        The endpoint is fully idempotent: if a repayment with the same
        ``django_payment_id`` already exists the existing record is returned
        without creating a duplicate entry or posting a second accounting entry.

        After the repayment is posted a ``payment.matched`` webhook is fired to
        the Django portal with the principal and interest allocation breakdown.

        Authentication
        --------------
        Requires ``X-Alba-API-Key`` header.

        Request body (JSON)
        -------------------
        Required: ``django_payment_id``, ``loan_number``, ``amount_paid``,
        ``payment_date``, ``payment_method``

        Optional: ``django_customer_id``, ``mpesa_transaction_id``,
        ``payment_reference``

        Response 201
        ------------
        .. code-block:: json

            {
                "odoo_repayment_id": 15,
                "status": "posted",
                "principal_applied": 8450.00,
                "interest_applied": 1550.00
            }
        """
        try:
            api_key = self._authenticate()
            data = self._parse_json_body()

            missing = self._validate_required(
                data,
                [
                    "django_payment_id",
                    "loan_number",
                    "amount_paid",
                    "payment_date",
                    "payment_method",
                ],
            )
            if missing:
                return self._error_response(
                    f"Missing required fields: {', '.join(missing)}", 400
                )

            django_payment_id = str(data["django_payment_id"]).strip()
            Repayment = request.env["alba.loan.repayment"].sudo()

            # --- Idempotency: check for existing repayment ------------------
            existing = Repayment.search(
                [("django_payment_id", "=", django_payment_id)], limit=1
            )
            if existing:
                _logger.info(
                    "record_payment: duplicate detected django_payment_id=%s "
                    "odoo_id=%d — returning existing.",
                    django_payment_id,
                    existing.id,
                )
                return self._json_response(
                    {
                        "odoo_repayment_id": existing.id,
                        "status": "already_exists",
                        "principal_applied": self._safe_float(
                            getattr(existing, "principal_applied", 0)
                        ),
                        "interest_applied": self._safe_float(
                            getattr(existing, "interest_applied", 0)
                        ),
                    }
                )

            # --- Resolve loan ------------------------------------------------
            loan = (
                request.env["alba.loan"]
                .sudo()
                .search([("loan_number", "=", data["loan_number"])], limit=1)
            )
            if not loan:
                return self._error_response(
                    f"Loan with loan_number='{data['loan_number']}' not found.", 404
                )

            # --- Normalise payment method ------------------------------------
            raw_method = (
                str(data.get("payment_method") or "")
                .strip()
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
            )
            odoo_payment_method = _PAYMENT_METHOD_MAP.get(raw_method, "bank_transfer")

            # --- Build repayment record --------------------------------------
            amount_paid = self._safe_float(data["amount_paid"])
            if amount_paid <= 0:
                return self._error_response(
                    f"amount_paid must be greater than zero (got {amount_paid}).", 400
                )

            repayment_vals = {
                "loan_id": loan.id,
                "django_payment_id": django_payment_id,
                "payment_date": data["payment_date"],
                "amount_paid": amount_paid,
                "payment_method": odoo_payment_method,
                "mpesa_transaction_id": (
                    data.get("mpesa_transaction_id") or ""
                ).strip(),
                "payment_reference": (data.get("payment_reference") or "").strip(),
                "state": "draft",
            }

            repayment = Repayment.create(repayment_vals)

            # --- Post the repayment (triggers accounting entries) -----------
            try:
                repayment.action_post()
            except (odoo_exceptions.UserError, odoo_exceptions.ValidationError) as exc:
                # Roll back the draft repayment to avoid orphan records
                repayment.unlink()
                return self._error_response(f"Cannot post repayment: {exc}", 400)

            # Refresh so computed allocation fields are visible
            repayment.invalidate_recordset()

            principal_applied = self._safe_float(
                getattr(repayment, "principal_applied", 0)
            )
            interest_applied = self._safe_float(
                getattr(repayment, "interest_applied", 0)
            )

            _logger.info(
                "record_payment: created and posted odoo_id=%d "
                "django_payment_id=%s loan=%s amount=%.2f",
                repayment.id,
                django_payment_id,
                loan.loan_number,
                amount_paid,
            )

            # --- Fire payment.matched webhook --------------------------------
            api_key.send_webhook(
                "payment.matched",
                {
                    "odoo_repayment_id": repayment.id,
                    "django_payment_id": django_payment_id,
                    "loan_number": loan.loan_number,
                    "odoo_loan_id": loan.id,
                    "amount_paid": amount_paid,
                    "payment_date": str(data["payment_date"]),
                    "payment_method": odoo_payment_method,
                    "mpesa_transaction_id": repayment.mpesa_transaction_id or "",
                    "payment_reference": repayment.payment_reference or "",
                    "principal_applied": principal_applied,
                    "interest_applied": interest_applied,
                    "receipt_number": getattr(repayment, "receipt_number", "") or "",
                },
            )

            return self._json_response(
                {
                    "odoo_repayment_id": repayment.id,
                    "status": "posted",
                    "principal_applied": principal_applied,
                    "interest_applied": interest_applied,
                },
                status=201,
            )

        except odoo_exceptions.AccessDenied as exc:
            return self._error_response(str(exc), 403)
        except odoo_exceptions.UserError as exc:
            return self._error_response(str(exc), 400)
        except Exception as exc:
            _logger.exception("record_payment: unexpected error — %s", exc)
            return self._error_response("Internal server error.", 500)
