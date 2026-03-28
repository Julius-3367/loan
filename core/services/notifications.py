# -*- coding: utf-8 -*-
"""
core.services.notifications
============================
Centralised notification service for the Alba Capital portal.

Handles:
  - Django in-portal Notification records
  - Transactional email (Django send_mail → SMTP or console)
  - SMS via Onfon Media HTTP API (optional, non-blocking)

Usage
-----
  from core.services.notifications import NotificationService
  NotificationService.application_submitted(application)
  NotificationService.application_approved(application)
  NotificationService.loan_disbursed(loan)
  NotificationService.payment_due_reminder(loan, days_until_due)
  NotificationService.payment_received(loan, repayment)

Configuration (.env / Django settings)
---------------------------------------
  ONFON_API_KEY      Onfon Media API key (leave blank to disable SMS)
  ONFON_SENDER_ID    Sender ID registered with Onfon (e.g. ALBACAP)
  EMAIL_HOST_USER    From address for transactional email

All email sending is wrapped in try/except so a broken SMTP config never
crashes the main request.  SMS failures are also silently logged.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────────────────────────────────────


def _send_email(to_email: str, subject: str, template: str, context: dict) -> bool:
    """Render *template* and send a plain-text + HTML email. Returns True on success."""
    try:
        html_body = render_to_string(template, context)
        # Strip tags for plain-text fallback
        import re
        plain_body = re.sub(r"<[^>]+>", "", html_body)

        send_mail(
            subject=subject,
            message=plain_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                               settings.EMAIL_HOST_USER or "noreply@albacapital.co.ke"),
            recipient_list=[to_email],
            html_message=html_body,
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.warning("Email to %s failed: %s", to_email, exc)
        return False


def _send_sms(phone: str, message: str) -> bool:
    """
    Send SMS via Onfon Media API.
    Returns True on success, False if disabled or on error.
    """
    api_key = getattr(settings, "ONFON_API_KEY", "")
    sender_id = getattr(settings, "ONFON_SENDER_ID", "ALBACAP")

    if not api_key:
        return False  # SMS not configured

    # Normalise Kenyan phone number to 254XXXXXXXXX
    phone = phone.strip().lstrip("+")
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        return False

    try:
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode({
            "key": api_key,
            "senderId": sender_id,
            "message": message,
            "mobile": phone,
        })
        url = f"https://api.onfonmedia.co.ke/v1/sms/SendBulkSMS?{params}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True
            logger.warning("Onfon SMS returned HTTP %s for %s", resp.status, phone)
    except Exception as exc:
        logger.warning("SMS to %s failed: %s", phone, exc)
    return False


def _create_notification(user, notification_type: str, title: str, message: str,
                         priority: str = "MEDIUM", loan_application=None, loan=None):
    """Create an in-portal Notification record (silently ignores errors)."""
    try:
        from loans.models import Notification  # avoid circular import
        Notification.create_for_user(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            loan_application=loan_application,
            loan=loan,
        )
    except Exception as exc:
        logger.warning("Could not create in-portal notification for %s: %s", user, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Public notification service
# ─────────────────────────────────────────────────────────────────────────────


class NotificationService:
    """
    Facade for all customer-facing notifications.
    Each method fires: in-portal Notification + email + SMS (if configured).
    """

    # ── Account lifecycle ────────────────────────────────────────────────────

    @staticmethod
    def account_approved(user):
        """Notify customer that their registration was approved."""
        _create_notification(
            user=user,
            notification_type="ACCOUNT_APPROVED",
            title="Account Approved",
            message="Your Alba Capital account has been approved. You can now apply for loans.",
            priority="HIGH",
        )
        _send_email(
            to_email=user.email,
            subject="Alba Capital — Account Approved",
            template="core/email/account_approved.html",
            context={
                "user": user,
                "login_url": settings.SITE_URL + "/login/" if hasattr(settings, "SITE_URL") else "/login/",
            },
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, your Alba Capital account is approved. "
                      "Log in at albacapital.co.ke to apply for a loan.")

    # ── Loan application lifecycle ───────────────────────────────────────────

    @staticmethod
    def application_submitted(application):
        """Notify customer that their application was received."""
        user = application.customer.user
        _create_notification(
            user=user,
            notification_type="APPLICATION_SUBMITTED",
            title=f"Application {application.application_number} Received",
            message=(
                f"Thank you! Your loan application {application.application_number} "
                f"for KES {application.requested_amount:,.0f} has been received and "
                "is being reviewed."
            ),
            loan_application=application,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Application {application.application_number} Received",
            template="core/email/application_submitted.html",
            context={"user": user, "application": application},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, your loan application "
                      f"{application.application_number} has been received. "
                      "We'll notify you of the outcome.")

    @staticmethod
    def application_approved(application):
        """Notify customer that their application was approved."""
        user = application.customer.user
        _create_notification(
            user=user,
            notification_type="APPLICATION_APPROVED",
            title=f"Application {application.application_number} Approved",
            message=(
                f"Congratulations! Your loan application {application.application_number} "
                f"for KES {application.requested_amount:,.0f} has been approved. "
                "Funds will be disbursed shortly."
            ),
            priority="HIGH",
            loan_application=application,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Application {application.application_number} Approved ✓",
            template="core/email/application_approved.html",
            context={"user": user, "application": application},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, your loan application "
                      f"{application.application_number} has been APPROVED! "
                      "Funds will be disbursed to your account soon.")

    @staticmethod
    def application_rejected(application):
        """Notify customer that their application was rejected."""
        user = application.customer.user
        _create_notification(
            user=user,
            notification_type="APPLICATION_REJECTED",
            title=f"Application {application.application_number} Not Approved",
            message=(
                f"Unfortunately, your loan application {application.application_number} "
                "was not approved at this time. "
                + (f"Reason: {application.rejection_reason}" if application.rejection_reason else "")
                + " Please contact us for more details."
            ),
            priority="HIGH",
            loan_application=application,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Application {application.application_number} Update",
            template="core/email/application_rejected.html",
            context={"user": user, "application": application},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, your loan application "
                      f"{application.application_number} was not approved. "
                      "Please visit our portal for details.")

    # ── Loan lifecycle ───────────────────────────────────────────────────────

    @staticmethod
    def loan_disbursed(loan):
        """Notify customer that their loan has been disbursed."""
        user = loan.customer.user
        _create_notification(
            user=user,
            notification_type="LOAN_DISBURSED",
            title=f"Loan {loan.loan_number} Disbursed",
            message=(
                f"KES {loan.principal_amount:,.0f} has been disbursed for loan "
                f"{loan.loan_number}. Your first payment of KES "
                f"{loan.installment_amount:,.0f} is due on {loan.first_payment_date}."
            ),
            priority="HIGH",
            loan=loan,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Loan {loan.loan_number} Disbursed",
            template="core/email/loan_disbursed.html",
            context={"user": user, "loan": loan},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, KES {loan.principal_amount:,.0f} disbursed "
                      f"for loan {loan.loan_number}. First payment: "
                      f"KES {loan.installment_amount:,.0f} due {loan.first_payment_date}.")

    @staticmethod
    def payment_due_reminder(loan, days_until_due: int):
        """Send payment due reminder N days before the due date."""
        user = loan.customer.user
        _create_notification(
            user=user,
            notification_type="PAYMENT_DUE",
            title=f"Payment Due in {days_until_due} Day(s) — {loan.loan_number}",
            message=(
                f"Your instalment of KES {loan.installment_amount:,.0f} for loan "
                f"{loan.loan_number} is due in {days_until_due} day(s) "
                f"({loan.next_payment_date}). Please ensure your account is funded."
            ),
            priority="HIGH" if days_until_due <= 1 else "MEDIUM",
            loan=loan,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Payment Reminder: {loan.loan_number}",
            template="core/email/payment_due.html",
            context={"user": user, "loan": loan, "days_until_due": days_until_due},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, reminder: KES {loan.installment_amount:,.0f} "
                      f"due in {days_until_due} day(s) for loan {loan.loan_number}. "
                      "Pay via M-Pesa or visit albacapital.co.ke.")

    @staticmethod
    def payment_received(loan, repayment):
        """Confirm payment receipt to customer."""
        user = loan.customer.user
        _create_notification(
            user=user,
            notification_type="PAYMENT_RECEIVED",
            title=f"Payment Received — {loan.loan_number}",
            message=(
                f"We have received your payment of KES {repayment.amount_paid:,.0f} "
                f"for loan {loan.loan_number}. Outstanding balance: "
                f"KES {loan.outstanding_balance:,.0f}."
            ),
            loan=loan,
        )
        _send_email(
            to_email=user.email,
            subject=f"Alba Capital — Payment Confirmed: {loan.loan_number}",
            template="core/email/payment_received.html",
            context={"user": user, "loan": loan, "repayment": repayment},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"Hi {user.first_name}, payment of KES {repayment.amount_paid:,.0f} "
                      f"confirmed for {loan.loan_number}. Balance: "
                      f"KES {loan.outstanding_balance:,.0f}. Thank you!")

    @staticmethod
    def payment_overdue(loan):
        """Alert customer that their loan is overdue."""
        user = loan.customer.user
        _create_notification(
            user=user,
            notification_type="PAYMENT_OVERDUE",
            title=f"OVERDUE — {loan.loan_number}",
            message=(
                f"Your loan {loan.loan_number} is {loan.days_overdue} day(s) overdue. "
                f"Outstanding balance: KES {loan.outstanding_balance:,.0f}. "
                "Please make payment immediately to avoid penalties."
            ),
            priority="CRITICAL",
            loan=loan,
        )
        _send_email(
            to_email=user.email,
            subject=f"URGENT — Overdue Payment: {loan.loan_number}",
            template="core/email/payment_overdue.html",
            context={"user": user, "loan": loan},
        )
        if user.phone:
            _send_sms(user.phone,
                      f"ALERT: Loan {loan.loan_number} is {loan.days_overdue} day(s) "
                      "overdue. Pay now to avoid penalties. Contact us: 0800 XXX XXX.")

    # ── KYC ─────────────────────────────────────────────────────────────────

    @staticmethod
    def kyc_verified(user):
        _create_notification(
            user=user,
            notification_type="KYC_VERIFIED",
            title="KYC Verification Complete",
            message="Your identity has been verified. You can now apply for loans.",
            priority="HIGH",
        )
        _send_email(
            to_email=user.email,
            subject="Alba Capital — KYC Verification Complete",
            template="core/email/kyc_verified.html",
            context={"user": user},
        )

    @staticmethod
    def kyc_rejected(user, reason: str = ""):
        _create_notification(
            user=user,
            notification_type="KYC_REJECTED",
            title="KYC Verification Failed",
            message=(
                "Your KYC verification could not be completed. "
                + (f"Reason: {reason} " if reason else "")
                + "Please update your documents and try again."
            ),
            priority="HIGH",
        )
        _send_email(
            to_email=user.email,
            subject="Alba Capital — KYC Verification Update Required",
            template="core/email/kyc_rejected.html",
            context={"user": user, "reason": reason},
        )
