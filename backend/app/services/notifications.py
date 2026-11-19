"""
FamilyConnect AI - Real Notification Service Abstraction (Phase 5B & Phase 6)
Supports real Email (SMTP / Resend HTTP API) and SMS (Twilio REST API) delivery
using actual saved trusted-contact destinations, with provider message IDs,
retries, deduplication, explicit test notification verification, and honest failure reporting.
Never simulates success when credentials are absent or destinations are unverified.
"""

import os
import time
import uuid
import json
import base64
import ssl
import smtplib
import urllib.request
import urllib.parse
import urllib.error
import datetime
import logging
import html
from pathlib import Path
from dotenv import load_dotenv
from email.message import EmailMessage
from email.utils import formatdate
from typing import Dict, Any, Optional, Tuple, List, Union
from sqlalchemy.orm import Session
from ..models import IncidentAlert, EmergencyIncident

logger = logging.getLogger("familyconnect.notifications")

# In-memory capture of dispatched notifications (useful for automated testing and auditing)
_captured_dispatches: List[Dict[str, Any]] = []

def get_captured_dispatches() -> List[Dict[str, Any]]:
    """Return a list of emails/SMS captured during mocked test dispatches."""
    return list(_captured_dispatches)

def clear_captured_dispatches() -> None:
    """Clear recorded dispatches."""
    global _captured_dispatches
    _captured_dispatches = []

# Explicitly load .env from project root or backend folder
def _ensure_env_loaded():
    root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env, override=False)
    elif backend_env.exists():
        load_dotenv(dotenv_path=backend_env, override=False)
    else:
        load_dotenv(override=False)

_ensure_env_loaded()

PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "test.invalid", "placeholder.local"}

# Tracks the most recent user-initiated test notification result
_last_test_notification_result: Optional[Dict[str, Any]] = None


class NotificationResult:
    def __init__(
        self,
        status: str,  # QUEUED, SENT, DELIVERED, FAILED
        provider: str,
        channel: str,
        provider_message_id: Optional[str] = None,
        attempts: int = 1,
        error_message: Optional[str] = None,
        delivered_at: Optional[datetime.datetime] = None
    ):
        self.status = status
        self.provider = provider
        self.channel = channel
        self.provider_message_id = provider_message_id
        self.attempts = attempts
        self.error_message = error_message
        self.delivered_at = delivered_at


def _is_placeholder_email(email: Optional[str]) -> bool:
    if not email or "@" not in email:
        return True
    domain = email.strip().split("@")[-1].lower()
    return domain in PLACEHOLDER_EMAIL_DOMAINS


def _is_placeholder_phone(phone: Optional[str]) -> bool:
    if not phone:
        return True
    cleaned = phone.strip()
    digits = "".join(c for c in cleaned if c.isdigit())
    if len(digits) < 7 or cleaned.endswith("000-0000"):
        return True
    return False


def get_notification_config_status() -> Dict[str, Any]:
    """
    Inspects environment variables (without exposing secrets) to report which
    real notification channels are configured and available, plus the result
    of the most recent explicit test notification.
    """
    _ensure_env_loaded()
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")
    smtp_port = int(os.environ.get("SMTP_PORT", "587") or "587")
    smtp_from = os.environ.get("SMTP_FROM_EMAIL", "").strip().strip('"').strip("'")

    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    resend_from = os.environ.get("RESEND_FROM_EMAIL", "FamilyConnect AI <sos@alerts.canakerala.com>").strip().strip('"').strip("'")
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip().strip('"').strip("'")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip().strip('"').strip("'")
    twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "").strip().strip('"').strip("'")

    email_configured = bool(smtp_host or resend_key)
    sms_configured = bool(twilio_sid and twilio_token and twilio_from)

    active_email_provider = "smtp" if smtp_host else ("resend" if resend_key else "unconfigured")
    active_sms_provider = "twilio" if sms_configured else "unconfigured"

    return {
        "live_delivery_available": email_configured or sms_configured,
        "email_configured": email_configured,
        "email_provider": active_email_provider,
        "email_sender": smtp_from if smtp_host else (resend_from if resend_key else None),
        "smtp_host": smtp_host if smtp_host else None,
        "smtp_port": smtp_port if smtp_host else None,
        "smtp_from_configured": bool(smtp_from),
        "sms_configured": sms_configured,
        "sms_provider": active_sms_provider,
        "last_test_result": _last_test_notification_result,
        "external_911_dispatch": "unavailable (safety policy boundary)"
    }


class NotificationContent:
    """Holds subject, plain-text body, and responsive HTML body for emergency notification."""
    def __init__(self, subject: str, text_body: str, html_body: str):
        self.subject = subject
        self.text_body = text_body
        self.html_body = html_body

    def __iter__(self):
        return iter((self.subject, self.text_body, self.html_body))

    def __getitem__(self, index):
        return (self.subject, self.text_body, self.html_body)[index]

    def __repr__(self):
        return f"<NotificationContent subject='{self.subject}'>"


def build_safe_notification_content(
    incident: EmergencyIncident,
    contact_name: str,
    tier_label: str = "Primary"
) -> NotificationContent:
    """
    Constructs professional, accessible, mobile-friendly email content for real SOS alerts:
    - Clear subject: "FamilyConnect AI — Emergency Alert: ..."
    - Family member's name
    - Emergency category / incident type
    - Severity and AI triage explanation (if available)
    - Incident description / reporter notes (if available)
    - Reported time in readable format with explicit UTC timezone
    - Location and Google Maps link (only if valid coordinates are available)
    - Current incident status
    - Application link (if valid base URL is configured)
    - Generates both high-contrast responsive HTML and a clean plain-text alternative.
    Does NOT invent missing incident details, fabricate coordinates, or expose unnecessary personal information.
    """
    safe_contact_name = html.escape(contact_name.strip() if contact_name else "Trusted Contact")
    safe_reporter_name = html.escape(incident.reporter_name.strip() if incident.reporter_name else "Family Member")
    safe_incident_type = html.escape(incident.incident_type.strip() if incident.incident_type else "General SOS")
    safe_status = html.escape((incident.status or "ACTIVE").strip().upper())
    safe_tier = html.escape(tier_label.strip() if tier_label else "Primary")

    severity_str = (getattr(incident, "severity_level", None) or getattr(incident, "severity", None) or "ALERT").strip().upper()
    if severity_str not in ("PENDING", "UNKNOWN", "ALERT"):
        subject = f"FamilyConnect AI — Emergency Alert: [{severity_str}] {incident.reporter_name} ({incident.incident_type})"
    else:
        subject = f"FamilyConnect AI — Emergency Alert: {incident.reporter_name} ({incident.incident_type})"

    # Reported Time with clear timezone
    created_dt = incident.created_at or datetime.datetime.utcnow()
    readable_time = created_dt.strftime("%A, %B %d, %Y at %I:%M:%S %p UTC")

    # Severity styling
    if severity_str == "CRITICAL":
        sev_color = "#dc2626"
        sev_badge = "#b91c1c"
    elif severity_str == "HIGH":
        sev_color = "#ea580c"
        sev_badge = "#c2410c"
    elif severity_str == "MEDIUM":
        sev_color = "#d97706"
        sev_badge = "#b45309"
    else:
        sev_color = "#2563eb"
        sev_badge = "#1d4ed8"

    # AI Triage & Explanation
    ai_rationale = (getattr(incident, "ai_rationale", None) or "").strip()
    safe_ai_rationale = html.escape(ai_rationale) if ai_rationale else None
    score = getattr(incident, "severity_score", None) if getattr(incident, "severity_score", None) is not None else getattr(incident, "ai_confidence", None)
    confidence_display = f" (Confidence: {round(score * 100)}%)" if score else ""

    # Incident Description
    desc_clean = (incident.description or "").strip()
    safe_description = html.escape(desc_clean) if desc_clean else None

    # Location & Map Link Validation
    has_valid_coords = False
    lat_val = None
    lon_val = None
    try:
        lat_in = getattr(incident, "latitude", None)
        lon_in = getattr(incident, "longitude", None)
        if lat_in is not None and lon_in is not None:
            lat_val = float(lat_in)
            lon_val = float(lon_in)
            if not (lat_val == 0.0 and lon_val == 0.0) and (-90.0 <= lat_val <= 90.0) and (-180.0 <= lon_val <= 180.0):
                has_valid_coords = True
    except (TypeError, ValueError):
        has_valid_coords = False

    raw_label = (getattr(incident, "location_label", None) or "").strip()
    safe_location_label = html.escape(raw_label) if raw_label else None
    loc_accuracy = getattr(incident, "location_accuracy_m", None)

    if has_valid_coords:
        coord_text = f"{lat_val:.5f}, {lon_val:.5f}"
        map_url = f"https://maps.google.com/?q={lat_val},{lon_val}"
        acc_text = f" (accuracy &plusmn;{round(loc_accuracy, 1)}m)" if loc_accuracy else ""
        plain_acc_text = f" (accuracy ±{round(loc_accuracy, 1)}m)" if loc_accuracy else ""
        location_summary = f"{raw_label or 'Reported GPS Location'} [approx. {coord_text}{plain_acc_text}]"
    else:
        coord_text = None
        map_url = None
        acc_text = ""
        location_summary = raw_label or "Coordinates not available / not reported"

    # App link verification (prioritize FRONTEND_PUBLIC_URL)
    base_url = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or os.environ.get("FAMILYCONNECT_PUBLIC_URL") or "").strip().rstrip("/")
    if base_url and (base_url.startswith("http://") or base_url.startswith("https://")):
        app_incident_url = f"{base_url}/?incident_id={incident.id}"
    else:
        app_incident_url = None

    # -------------------------------------------------------------
    # 1. Plain-Text Alternative Body
    # -------------------------------------------------------------
    text_lines = [
        "=======================================================================",
        "FAMILYCONNECT AI — EMERGENCY ALERT",
        "=======================================================================",
        "",
        f"Hello {contact_name} ({tier_label} Trusted Contact),",
        "",
        f"An emergency SOS has been reported for your family member {incident.reporter_name}.",
        "",
        "INCIDENT DETAILS:",
        f"• Family Member:    {incident.reporter_name}",
        f"• Emergency Type:   {incident.incident_type}",
        f"• Incident ID:      #{incident.id}",
        f"• Current Status:   {safe_status}",
        f"• Reported Time:    {readable_time}",
        f"• Severity Level:   {severity_str}{confidence_display}",
    ]

    if ai_rationale:
        text_lines.extend([
            "",
            "AI TRIAGE ASSESSMENT:",
            f"Explanation: {ai_rationale}",
            "(Decision-support indicator based on reported symptoms and profile context.)"
        ])

    if desc_clean:
        text_lines.extend([
            "",
            "INCIDENT DESCRIPTION:",
            f"{desc_clean}"
        ])
    else:
        text_lines.extend([
            "",
            "INCIDENT DESCRIPTION:",
            "No additional description provided by reporter."
        ])

    text_lines.extend([
        "",
        "LOCATION INFORMATION:",
        f"Location: {location_summary}"
    ])
    if has_valid_coords and map_url:
        text_lines.append(f"Google Maps Link: {map_url}")

    if app_incident_url:
        text_lines.extend([
            "",
            "INCIDENT ACCESS:",
            f"View & Acknowledge Incident: {app_incident_url}",
            "(Requires authentication to protect family privacy)"
        ])

    text_lines.extend([
        "",
        "=======================================================================",
        "IMPORTANT SAFETY NOTICE:",
        "This notification was sent to authorized trusted contacts configured in",
        "FamilyConnect AI. AI assessment is for decision support only and is NOT",
        "a certified medical diagnosis. If this is a life-threatening emergency,",
        "please call 112 (National Emergency) or 108 (Ambulance) immediately. Official emergency dispatch is not automatically",
        "contacted by this application.",
        "======================================================================="
    ])
    text_body = "\n".join(text_lines)

    # -------------------------------------------------------------
    # 2. Rich, Accessible, Mobile-Friendly HTML Body
    # -------------------------------------------------------------
    ai_box_html = ""
    if safe_ai_rationale:
        ai_box_html = f"""
        <div style="background-color: #f1f5f9; border-left: 4px solid {sev_badge}; padding: 14px 16px; border-radius: 6px; margin-bottom: 20px;">
          <h3 style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #475569;">
            AI Triage Assessment {f'<span style="font-weight: 500; font-size: 12px; color: #64748b;">{confidence_display}</span>' if confidence_display else ''}
          </h3>
          <p style="margin: 0; font-size: 14px; line-height: 1.5; color: #1e293b;">
            {safe_ai_rationale}
          </p>
          <p style="margin: 6px 0 0 0; font-size: 11px; color: #64748b; font-style: italic;">
            Experimental decision-support indicator, not a certified medical diagnosis.
          </p>
        </div>
        """

    desc_box_html = ""
    if safe_description:
        desc_box_html = f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 14px 16px; border-radius: 6px; margin-bottom: 20px;">
          <h3 style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b;">
            Incident Notes
          </h3>
          <p style="margin: 0; font-size: 14px; line-height: 1.5; color: #1e293b; white-space: pre-wrap;">{safe_description}</p>
        </div>
        """

    if has_valid_coords and map_url:
        location_box_html = f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
          <h3 style="margin: 0 0 8px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b;">
            Location Details
          </h3>
          <p style="margin: 0 0 6px 0; font-size: 14px; font-weight: 600; color: #0f172a;">
            {safe_location_label or "Reported GPS Coordinates"}
          </p>
          <p style="margin: 0 0 12px 0; font-size: 13px; color: #475569;">
            Coordinates: <code style="background-color: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px;">{coord_text}</code>{acc_text}
          </p>
          <a href="{map_url}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 18px; border-radius: 6px; font-size: 13px; font-weight: 700; min-height: 38px; line-height: 20px;">
            Open in Google Maps &rarr;
          </a>
        </div>
        """
    else:
        location_box_html = f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 14px 16px; border-radius: 6px; margin-bottom: 20px;">
          <h3 style="margin: 0 0 6px 0; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b;">
            Location Details
          </h3>
          <p style="margin: 0; font-size: 14px; color: #475569;">
            {safe_location_label or "Coordinates not available / not reported for this incident."}
          </p>
        </div>
        """

    app_btn_html = ""
    if app_incident_url:
        app_btn_html = f"""
        <div style="text-align: center; margin: 24px 0 16px 0;">
          <a href="{app_incident_url}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #0f172a; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-size: 15px; font-weight: 700; min-height: 44px; line-height: 22px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            View &amp; Acknowledge Incident &rarr;
          </a>
          <p style="margin: 8px 0 0 0; font-size: 12px; color: #64748b;">
            Authentication required to protect family privacy
          </p>
        </div>
        """

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f1f5f9; padding: 24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container (max-width: 600px for mobile/desktop email clients) -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0;">
          
          <!-- Urgent Header Banner -->
          <tr>
            <td style="background-color: {sev_badge}; padding: 20px 24px; text-align: left;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: rgba(255, 255, 255, 0.85); display: block; margin-bottom: 4px;">FamilyConnect AI &bull; Emergency Alert</span>
                    <h1 style="margin: 0; font-size: 20px; font-weight: 800; color: #ffffff; line-height: 1.25;">
                      {safe_reporter_name} &mdash; {safe_incident_type}
                    </h1>
                  </td>
                  <td align="right" style="vertical-align: middle; white-space: nowrap; padding-left: 12px;">
                    <span style="display: inline-block; padding: 6px 12px; background-color: rgba(255, 255, 255, 0.2); border: 1px solid rgba(255, 255, 255, 0.4); border-radius: 9999px; font-size: 12px; font-weight: 800; color: #ffffff; text-transform: uppercase; letter-spacing: 0.5px;">
                      {severity_str}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Content Body -->
          <tr>
            <td style="padding: 24px;">
              <!-- Greeting & Context -->
              <p style="margin-top: 0; margin-bottom: 14px; font-size: 15px; line-height: 1.5; color: #334155;">
                Hello <strong>{safe_contact_name}</strong>,
              </p>
              <p style="margin-top: 0; margin-bottom: 20px; font-size: 15px; line-height: 1.5; color: #334155;">
                An emergency SOS has been reported for <strong>{safe_reporter_name}</strong>. You are receiving this alert as a designated <strong>{safe_tier} Trusted Contact</strong>.
              </p>

              <!-- Incident Details Card -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px; font-size: 14px;">
                <tr>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #64748b; width: 36%;">Family Member</td>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: #0f172a;">{safe_reporter_name}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #64748b;">Emergency Type</td>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: #0f172a;">{safe_incident_type}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #64748b;">Severity Level</td>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: {sev_color};">
                    {severity_str} {html.escape(confidence_display)}
                  </td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #64748b;">Current Status</td>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 700; color: #0f172a;">{safe_status}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #64748b;">Reported Time</td>
                  <td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #0f172a; font-weight: 500;">{readable_time}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; font-weight: 600; color: #64748b;">Incident Ref</td>
                  <td style="padding: 10px 14px; color: #0f172a; font-weight: 500;">#{incident.id}</td>
                </tr>
              </table>

              <!-- AI Triage Box (if available) -->
              {ai_box_html}

              <!-- Description / Notes (if available) -->
              {desc_box_html}

              <!-- Location & Map -->
              {location_box_html}

              <!-- App CTA Link (if configured) -->
              {app_btn_html}

            </td>
          </tr>

          <!-- Safety Policy Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 24px; text-align: left; font-size: 12px; line-height: 1.5; color: #64748b;">
              <strong style="color: #475569; display: block; margin-bottom: 4px;">Important Safety Notice:</strong>
              AI severity assessment is an experimental decision-support indicator, not a certified medical diagnosis. 
              Official 112 / emergency services dispatch is not automatically contacted by this application.
              If there is immediate danger to life or safety, please call emergency services immediately.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    return NotificationContent(subject=subject, text_body=text_body, html_body=html_body)


def _send_via_smtp(
    recipient_email: str,
    subject: str,
    body: str,
    incident_id: int,
    html_body: Optional[str] = None,
    max_retries: int = 2
) -> NotificationResult:
    if not recipient_email or "@" not in recipient_email:
        return NotificationResult(
            status="FAILED",
            provider="smtp",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message="Trusted contact has no valid email address configured."
        )

    if _is_placeholder_email(recipient_email):
        return NotificationResult(
            status="FAILED",
            provider="smtp",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message=f"Refused to send to placeholder email destination '{recipient_email}'."
        )

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        msg_id = f"mock-smtp-{uuid.uuid4().hex[:12]}"
        logger.info(
            f"[Notification] Simulated EMAIL alert to '{recipient_email}' via smtp_mock "
            f"(mock mode active; real SMTP connection suppressed; ref: {msg_id})"
        )
        _captured_dispatches.append({
            "channel": "EMAIL",
            "provider": "smtp_mock",
            "recipient": recipient_email,
            "subject": subject,
            "body": body,
            "html": html_body,
            "msg_id": msg_id,
        })
        return NotificationResult(
            status="SIMULATED",
            provider="smtp_mock",
            channel="EMAIL",
            provider_message_id=msg_id,
            attempts=1,
            error_message=None,
            delivered_at=None
        )

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "587") or "587")
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("SMTP_FROM_EMAIL", smtp_user or "alerts@familyconnect.local").strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "false").lower() in ("true", "1", "yes")
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    timeout_sec = float(os.environ.get("SMTP_TIMEOUT_SEC", "5.0"))

    if not smtp_host:
        return NotificationResult(
            status="FAILED",
            provider="unconfigured",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message="Live email delivery unavailable: SMTP_HOST is not configured."
        )

    domain_part = smtp_from.split("@")[-1] if "@" in smtp_from else "familyconnect.local"
    msg_id = f"<fc-inc-{incident_id}-{uuid.uuid4().hex[:12]}@{domain_part}>"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = recipient_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = msg_id
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    last_error = None
    total_attempts = 0

    for attempt in range(1, max_retries + 2):
        total_attempts = attempt
        try:
            if use_ssl:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout_sec) as server:
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    refused = server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_sec) as server:
                    server.ehlo()
                    if use_tls:
                        server.starttls()
                        server.ehlo()
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    refused = server.send_message(msg)

            if refused:
                last_error = f"SMTP recipient refused: {list(refused.keys())}"
                continue

            now = datetime.datetime.utcnow()
            return NotificationResult(
                status="DELIVERED",
                provider="smtp",
                channel="EMAIL",
                provider_message_id=msg_id,
                attempts=total_attempts,
                error_message=None,
                delivered_at=now
            )
        except Exception as exc:
            last_error = f"SMTP delivery error (attempt {attempt}/{max_retries + 1}): {type(exc).__name__}: {str(exc)}"
            logger.warning(f"[Notification] {last_error}")
            if attempt <= max_retries:
                time.sleep(0.15 * attempt)

    return NotificationResult(
        status="FAILED",
        provider="smtp",
        channel="EMAIL",
        provider_message_id=None,
        attempts=total_attempts,
        error_message=last_error
    )


def _send_via_resend(
    recipient_email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    max_retries: int = 2
) -> NotificationResult:
    if not recipient_email or "@" not in recipient_email:
        return NotificationResult(
            status="FAILED",
            provider="resend",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message="Trusted contact has no valid email address configured."
        )

    if _is_placeholder_email(recipient_email):
        return NotificationResult(
            status="FAILED",
            provider="resend",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message=f"Refused to send to placeholder email destination '{recipient_email}'."
        )

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        msg_id = f"mock-resend-{uuid.uuid4().hex[:12]}"
        logger.info(
            f"[Notification] Simulated EMAIL alert to '{recipient_email}' via resend_mock "
            f"(mock mode active; real HTTP API call suppressed; ref: {msg_id})"
        )
        _captured_dispatches.append({
            "channel": "EMAIL",
            "provider": "resend_mock",
            "recipient": recipient_email,
            "subject": subject,
            "body": body,
            "html": html_body,
            "msg_id": msg_id,
        })
        return NotificationResult(
            status="SIMULATED",
            provider="resend_mock",
            channel="EMAIL",
            provider_message_id=msg_id,
            attempts=1,
            error_message=None,
            delivered_at=None
        )

    _ensure_env_loaded()
    api_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "FamilyConnect AI <sos@alerts.canakerala.com>").strip().strip('"').strip("'")

    if not api_key:
        return NotificationResult(
            status="FAILED",
            provider="unconfigured",
            channel="EMAIL",
            provider_message_id=None,
            attempts=1,
            error_message="Live email delivery unavailable: RESEND_API_KEY is not configured."
        )

    payload_dict: Dict[str, Any] = {
        "from": from_email,
        "to": [recipient_email],
        "subject": subject,
        "text": body
    }
    if html_body:
        payload_dict["html"] = html_body

    payload = json.dumps(payload_dict).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "FamilyConnectAI/1.0"
    }

    last_error = None
    total_attempts = 0

    for attempt in range(1, max_retries + 2):
        total_attempts = attempt
        try:
            req = urllib.request.Request("https://api.resend.com/emails", data=payload, headers=headers, method="POST")
            ssl_ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10.0, context=ssl_ctx) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_id = resp_data.get("id")
                return NotificationResult(
                    status="SENT",
                    provider="resend",
                    channel="EMAIL",
                    provider_message_id=msg_id,
                    attempts=total_attempts,
                    error_message=None,
                    delivered_at=datetime.datetime.utcnow()
                )
        except urllib.error.HTTPError as http_err:
            try:
                err_body = http_err.read().decode("utf-8")
                err_json = json.loads(err_body)
                err_detail = err_json.get("message") or err_json.get("error") or err_body
            except Exception:
                err_detail = str(http_err)
            last_error = f"Resend API error (attempt {attempt}): HTTP {http_err.code}: {err_detail}"
            logger.warning(f"[Notification] {last_error}")
            if http_err.code in (400, 401, 402, 403, 422):
                break
            if attempt <= max_retries:
                time.sleep(0.2 * attempt)
        except Exception as exc:
            last_error = f"Resend API error (attempt {attempt}): {type(exc).__name__}: {str(exc)}"
            logger.warning(f"[Notification] {last_error}")
            if attempt <= max_retries:
                time.sleep(0.2 * attempt)

    return NotificationResult(
        status="FAILED",
        provider="resend",
        channel="EMAIL",
        provider_message_id=None,
        attempts=total_attempts,
        error_message=last_error
    )


def _send_via_twilio_sms(
    recipient_phone: str,
    body: str,
    max_retries: int = 2
) -> NotificationResult:
    if not recipient_phone or len(recipient_phone.strip()) < 7:
        return NotificationResult(
            status="FAILED",
            provider="twilio",
            channel="SMS",
            provider_message_id=None,
            attempts=1,
            error_message="Invalid phone number for trusted contact."
        )

    if _is_placeholder_phone(recipient_phone):
        return NotificationResult(
            status="FAILED",
            provider="twilio",
            channel="SMS",
            provider_message_id=None,
            attempts=1,
            error_message=f"Refused to send SMS to invalid or placeholder phone number '{recipient_phone}'."
        )

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        msg_id = f"mock-twilio-{uuid.uuid4().hex[:12]}"
        logger.info(
            f"[Notification] Simulated SMS alert to '{recipient_phone}' via twilio_mock "
            f"(mock mode active; real REST API call suppressed; ref: {msg_id})"
        )
        _captured_dispatches.append({
            "channel": "SMS",
            "provider": "twilio_mock",
            "recipient": recipient_phone,
            "subject": "",
            "body": body,
            "html": None,
            "msg_id": msg_id,
        })
        return NotificationResult(
            status="SIMULATED",
            provider="twilio_mock",
            channel="SMS",
            provider_message_id=msg_id,
            attempts=1,
            error_message=None,
            delivered_at=None
        )

    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

    if not (sid and token and from_num):
        return NotificationResult(
            status="FAILED",
            provider="unconfigured",
            channel="SMS",
            provider_message_id=None,
            attempts=1,
            error_message="Live SMS delivery unavailable: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER are not configured."
        )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({
        "To": recipient_phone,
        "From": from_num,
        "Body": body
    }).encode("utf-8")

    auth_b64 = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    last_error = None
    total_attempts = 0
    for attempt in range(1, max_retries + 2):
        total_attempts = attempt
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_sid = resp_data.get("sid")
                tw_status = (resp_data.get("status") or "sent").upper()
                mapped_status = "DELIVERED" if tw_status == "DELIVERED" else "SENT"
                return NotificationResult(
                    status=mapped_status,
                    provider="twilio",
                    channel="SMS",
                    provider_message_id=msg_sid,
                    attempts=total_attempts,
                    error_message=None,
                    delivered_at=datetime.datetime.utcnow() if mapped_status == "DELIVERED" else None
                )
        except Exception as exc:
            last_error = f"Twilio SMS error (attempt {attempt}): {type(exc).__name__}: {str(exc)}"
            if attempt <= max_retries:
                time.sleep(0.2 * attempt)

    return NotificationResult(
        status="FAILED",
        provider="twilio",
        channel="SMS",
        provider_message_id=None,
        attempts=total_attempts,
        error_message=last_error
    )


def dispatch_contact_notification(
    db: Session,
    incident: EmergencyIncident,
    contact_name: str,
    contact_phone: str,
    contact_email: Optional[str] = None,
    contact_id: Optional[int] = None,
    preferred_channel: str = "EMAIL",
    tier_label: str = "Primary",
    max_retries: int = 2
) -> IncidentAlert:
    """
    Dispatches an alert to an active trusted contact using their actual saved destination,
    with deduplication, provider selection, retries, and persistent status tracking.
    Never sends to invented fallback destinations.
    """
    now = datetime.datetime.utcnow()
    pref_upper = (preferred_channel or "EMAIL").upper()

    _ensure_env_loaded()
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip().strip('"').strip("'")

    if "EMAIL" in pref_upper or (contact_email and (smtp_host or resend_key) and "SMS" not in pref_upper):
        effective_channel = "EMAIL"
    elif "SMS" in pref_upper and twilio_sid:
        effective_channel = "SMS"
    elif contact_email:
        effective_channel = "EMAIL"
    else:
        effective_channel = "SMS" if "SMS" in pref_upper else "EMAIL"

    contact_key = str(contact_id) if contact_id else f"{contact_name}:{contact_phone}"
    dedup_key = f"inc:{incident.id}:contact:{contact_key}:ch:{effective_channel}"

    existing_alert = db.query(IncidentAlert).filter(
        IncidentAlert.incident_id == incident.id,
        IncidentAlert.dedup_key == dedup_key
    ).first()

    if existing_alert and existing_alert.status in ("SENT", "DELIVERED", "ACKNOWLEDGED", "SIMULATED"):
        logger.info(f"[Notification] Deduplicated alert for {dedup_key} (already {existing_alert.status})")
        return existing_alert

    subject, body, html_body = build_safe_notification_content(incident, contact_name, tier_label)

    if existing_alert:
        alert = existing_alert
        alert.status = "QUEUED"
    else:
        alert = IncidentAlert(
            incident_id=incident.id,
            contact_id=contact_id,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            channel=effective_channel,
            status="QUEUED",
            provider="pending",
            delivery_attempts=0,
            dedup_key=dedup_key,
            sent_at=now
        )
        db.add(alert)
        db.flush()

    if effective_channel == "EMAIL":
        target_email = (contact_email or "").strip()
        if not target_email:
            result = NotificationResult(
                status="FAILED",
                provider="smtp" if smtp_host else ("resend" if resend_key else "unconfigured"),
                channel="EMAIL",
                provider_message_id=None,
                attempts=1,
                error_message=f"Trusted contact '{contact_name}' has no email address configured."
            )
        elif smtp_host:
            result = _send_via_smtp(target_email, subject, body, incident.id, html_body=html_body, max_retries=max_retries)
        elif resend_key:
            result = _send_via_resend(target_email, subject, body, html_body=html_body, max_retries=max_retries)
        elif os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
            result = _send_via_resend(target_email, subject, body, html_body=html_body, max_retries=max_retries)
        else:
            result = NotificationResult(
                status="FAILED",
                provider="unconfigured",
                channel="EMAIL",
                provider_message_id=None,
                attempts=1,
                error_message="Live delivery unavailable: Neither SMTP_HOST nor RESEND_API_KEY is configured in environment."
            )
    else:
        result = _send_via_twilio_sms(contact_phone, body, max_retries=max_retries)

    alert.status = result.status
    alert.provider = result.provider
    alert.channel = result.channel
    alert.provider_message_id = result.provider_message_id
    alert.delivery_attempts = (alert.delivery_attempts or 0) + result.attempts
    alert.last_attempt_at = datetime.datetime.utcnow()
    alert.delivered_at = result.delivered_at
    alert.error_message = result.error_message
    db.flush()

    return alert


def retry_failed_alert(
    db: Session,
    alert: IncidentAlert,
    incident: EmergencyIncident,
    max_retries: int = 2
) -> IncidentAlert:
    """
    Retries a previously FAILED or QUEUED IncidentAlert using its saved destination.
    """
    if alert.status in ("SENT", "DELIVERED", "ACKNOWLEDGED"):
        return alert

    subject, body, html_body = build_safe_notification_content(incident, alert.contact_name, "Retry")
    _ensure_env_loaded()
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")

    target_email = (alert.contact_email or "").strip()
    if alert.channel == "EMAIL" or target_email:
        if not target_email:
            result = NotificationResult(
                status="FAILED",
                provider="smtp" if smtp_host else ("resend" if resend_key else "unconfigured"),
                channel="EMAIL",
                provider_message_id=None,
                attempts=1,
                error_message=f"Trusted contact '{alert.contact_name}' has no email address configured."
            )
        elif smtp_host:
            result = _send_via_smtp(target_email, subject, body, incident.id, html_body=html_body, max_retries=max_retries)
        elif resend_key:
            result = _send_via_resend(target_email, subject, body, html_body=html_body, max_retries=max_retries)
        elif os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
            result = _send_via_resend(target_email, subject, body, html_body=html_body, max_retries=max_retries)
        else:
            result = NotificationResult(
                status="FAILED",
                provider="unconfigured",
                channel="EMAIL",
                provider_message_id=None,
                attempts=1,
                error_message="Live delivery unavailable: Neither SMTP_HOST nor RESEND_API_KEY is configured."
            )
    else:
        result = _send_via_twilio_sms(alert.contact_phone, body, max_retries=max_retries)

    alert.status = result.status
    alert.provider = result.provider
    alert.channel = result.channel
    alert.provider_message_id = result.provider_message_id
    alert.delivery_attempts = (alert.delivery_attempts or 0) + result.attempts
    alert.last_attempt_at = datetime.datetime.utcnow()
    alert.delivered_at = result.delivered_at
    alert.error_message = result.error_message
    db.flush()

    return alert


def send_explicit_test_notification(
    channel: str,
    recipient: str,
    confirm_send: bool,
    requested_by: str
) -> Dict[str, Any]:
    """
    Phase 6 Section 6: Sends a user-initiated test notification ONLY when confirm_send=True.
    Records and returns the honest provider result.
    """
    global _last_test_notification_result

    if not confirm_send:
        raise ValueError("Explicit user confirmation (confirm_send=True) is required before sending a test notification.")

    ch = (channel or "EMAIL").strip().upper()
    dest = (recipient or "").strip()
    if ch == "EMAIL" and _is_placeholder_email(dest):
        raise ValueError(f"Refused to send test notification to placeholder email destination '{dest}'.")
    if ch == "SMS" and _is_placeholder_phone(dest):
        raise ValueError(f"Refused to send test notification to placeholder phone destination '{dest}'.")
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    subject = "[FamilyConnect AI] Explicit Provider Verification Test"
    body = (
        f"This is an explicit user-initiated test notification from FamilyConnect AI.\n"
        f"Requested by: {requested_by}\n"
        f"Timestamp: {now_iso}\n"
        f"Channel: {ch}\n"
    )

    _ensure_env_loaded()
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")

    if ch == "EMAIL":
        if smtp_host:
            res = _send_via_smtp(dest, subject, body, incident_id=0, max_retries=1)
        elif resend_key:
            res = _send_via_resend(dest, subject, body, max_retries=1)
        elif os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
            res = _send_via_resend(dest, subject, body, max_retries=1)
        else:
            res = NotificationResult(
                status="FAILED",
                provider="unconfigured",
                channel="EMAIL",
                provider_message_id=None,
                attempts=1,
                error_message="Live email delivery unavailable: Neither SMTP_HOST nor RESEND_API_KEY is configured."
            )
    elif ch == "SMS":
        res = _send_via_twilio_sms(dest, body, max_retries=1)
    else:
        raise ValueError("Unsupported channel. Choose EMAIL or SMS.")

    summary = {
        "channel": res.channel,
        "recipient": dest,
        "status": res.status,
        "provider": res.provider,
        "provider_message_id": res.provider_message_id,
        "attempts": res.attempts,
        "error_message": res.error_message,
        "tested_at": now_iso,
        "requested_by": requested_by,
        "succeeded": res.status in ("DELIVERED", "SENT", "SIMULATED")
    }
    _last_test_notification_result = summary
    return summary


def send_household_invitation_email(
    recipient_email: str,
    inviter_name: str,
    household_name: str,
    invitation_link: str,
    role: str = "member",
    expires_hours: int = 72
) -> NotificationResult:
    """Dispatches a branded invitation email via the configured email provider (Resend/SMTP)."""
    subject = f"FamilyConnect AI — Invitation to join {household_name}'s Household"
    clean_inviter = html.escape(inviter_name)
    clean_household = html.escape(household_name)
    clean_role = html.escape(role)
    clean_link = html.escape(invitation_link)

    text_body = (
        f"Hello,\n\n"
        f"{inviter_name} has invited you to join their household ({household_name}) on FamilyConnect AI as a {role}.\n\n"
        f"FamilyConnect AI provides real-time emergency monitoring, SOS alerting, and trusted community support.\n\n"
        f"To accept this invitation, open the following link:\n"
        f"{invitation_link}\n\n"
        f"This link is valid for {expires_hours} hours. Single use only.\n"
        f"If you did not expect this invitation, you may safely ignore this message.\n\n"
        f"— FamilyConnect AI Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);border:1px solid #e2e8f0;">
          <tr>
            <td style="background-color:#0284c7;padding:24px;text-align:left;">
              <span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:rgba(255,255,255,0.85);display:block;margin-bottom:4px;">FamilyConnect AI</span>
              <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff;line-height:1.25;">
                Household Invitation
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;">
              <p style="margin-top:0;margin-bottom:16px;font-size:15px;line-height:1.6;color:#334155;">
                Hello,
              </p>
              <p style="margin-top:0;margin-bottom:16px;font-size:15px;line-height:1.6;color:#334155;">
                <strong>{clean_inviter}</strong> has invited you to join the <strong>{clean_household}</strong> circle on FamilyConnect AI as a <strong>{clean_role}</strong>.
              </p>
              <div style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:20px 0;">
                <p style="margin:0;font-size:14px;color:#475569;line-height:1.5;">
                  FamilyConnect AI keeps your family safe with instant SOS alerts, live geolocation sharing, and trusted emergency contacts.
                </p>
              </div>
              <div style="text-align:center;margin:28px 0 20px 0;">
                <a href="{clean_link}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background-color:#0284c7;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:8px;font-size:15px;font-weight:700;min-height:44px;line-height:22px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
                  Accept Invitation &rarr;
                </a>
                <p style="margin:10px 0 0 0;font-size:12px;color:#64748b;">
                  Link expires in {expires_hours} hours. Single-use only.
                </p>
              </div>
              <p style="margin-top:24px;margin-bottom:0;font-size:12px;color:#94a3b8;line-height:1.5;border-top:1px solid #f1f5f9;padding-top:16px;">
                If you did not expect this invitation, you can safely disregard this email.<br>
                Direct link: <a href="{clean_link}" style="color:#0284c7;word-break:break-all;">{clean_link}</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _ensure_env_loaded()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif resend_key:
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif smtp_host:
        return _send_via_smtp(recipient_email, subject, text_body, html_body=html_body, incident_id=0)
    else:
        return NotificationResult(
            status="FAILED",
            provider="unconfigured",
            channel="EMAIL",
            error_message="Email delivery unavailable: Neither RESEND_API_KEY nor SMTP_HOST is configured."
        )


def send_responder_application_received_email(
    recipient_email: str,
    applicant_name: str,
    organization: str
) -> NotificationResult:
    """Dispatches application confirmation email to first-responder applicant."""
    subject = "FamilyConnect AI — First Responder Application Received"
    clean_name = html.escape(applicant_name)
    clean_org = html.escape(organization)

    text_body = (
        f"Hello {applicant_name},\n\n"
        f"Thank you for applying to be a verified community First Responder with {organization} on FamilyConnect AI.\n\n"
        f"Your application has been received and is currently under review by our platform administration team.\n"
        f"For community safety, emergency responders require administrative verification before incident access is granted.\n\n"
        f"You will receive an email notification once your application has been evaluated.\n\n"
        f"— FamilyConnect AI Operations Team"
    )

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);border:1px solid #e2e8f0;">
          <tr>
            <td style="background-color:#0f172a;padding:24px;text-align:left;">
              <span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:rgba(255,255,255,0.85);display:block;margin-bottom:4px;">FamilyConnect AI &bull; Responder Network</span>
              <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff;line-height:1.25;">
                Application Received
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;">
              <p style="margin-top:0;margin-bottom:16px;font-size:15px;line-height:1.6;color:#334155;">
                Hello <strong>{clean_name}</strong>,
              </p>
              <p style="margin-top:0;margin-bottom:16px;font-size:15px;line-height:1.6;color:#334155;">
                Thank you for applying to join the verified First Responder network representing <strong>{clean_org}</strong>.
              </p>
              <div style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:20px 0;">
                <p style="margin:0;font-size:14px;color:#475569;line-height:1.5;">
                  <strong>Status: Pending Verification</strong><br>
                  To protect community members, all first responder registrations require administrative vetting of credentials before account activation.
                </p>
              </div>
              <p style="margin-top:16px;margin-bottom:0;font-size:14px;color:#475569;line-height:1.5;">
                You will receive another email once your credentials have been verified by a platform administrator.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _ensure_env_loaded()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif resend_key:
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif smtp_host:
        return _send_via_smtp(recipient_email, subject, text_body, html_body=html_body, incident_id=0)
    else:
        return NotificationResult(status="FAILED", provider="unconfigured", channel="EMAIL", error_message="Email unconfigured")


def send_responder_application_decision_email(
    recipient_email: str,
    applicant_name: str,
    approved: bool,
    review_notes: Optional[str] = None
) -> NotificationResult:
    """Dispatches application approval or rejection email to first-responder applicant."""
    clean_name = html.escape(applicant_name)
    clean_notes = html.escape(review_notes) if review_notes else None

    if approved:
        subject = "FamilyConnect AI — First Responder Application Approved"
        text_body = (
            f"Hello {applicant_name},\n\n"
            f"Great news! Your First Responder application for FamilyConnect AI has been APPROVED.\n\n"
            f"Your account is now active. You may log in to the dashboard to receive emergency incident assignments, "
            f"view incident locations, and coordinate real-time emergency responses.\n\n"
            f"{f'Reviewer Notes: {review_notes}' if review_notes else ''}\n\n"
            f"— FamilyConnect AI Operations Team"
        )
        badge_color = "#15803d"
        status_text = "Approved & Activated"
        message_detail = "Your responder account has been approved and activated. You can now log in using your registered credentials."
    else:
        subject = "FamilyConnect AI — First Responder Application Status Update"
        text_body = (
            f"Hello {applicant_name},\n\n"
            f"Thank you for your interest in joining the FamilyConnect AI First Responder network.\n"
            f"After review, your application could not be approved at this time.\n\n"
            f"{f'Reason / Notes: {review_notes}' if review_notes else ''}\n\n"
            f"If you have questions or wish to update your credentials, please contact support.\n\n"
            f"— FamilyConnect AI Operations Team"
        )
        badge_color = "#b91c1c"
        status_text = "Not Approved"
        message_detail = "After administrative review, your application could not be approved at this time."

    notes_html = f"<p style='margin:12px 0 0 0;font-size:14px;color:#334155;'><strong>Notes:</strong> {clean_notes}</p>" if clean_notes else ""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);border:1px solid #e2e8f0;">
          <tr>
            <td style="background-color:{badge_color};padding:24px;text-align:left;">
              <span style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:rgba(255,255,255,0.85);display:block;margin-bottom:4px;">FamilyConnect AI &bull; Responder Network</span>
              <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff;line-height:1.25;">
                Application {status_text}
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:24px;">
              <p style="margin-top:0;margin-bottom:16px;font-size:15px;line-height:1.6;color:#334155;">
                Hello <strong>{clean_name}</strong>,
              </p>
              <div style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:20px 0;">
                <p style="margin:0;font-size:14px;color:#475569;line-height:1.5;">
                  {message_detail}
                </p>
                {notes_html}
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    _ensure_env_loaded()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    smtp_host = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")

    if os.environ.get("MOCK_NOTIFICATIONS", "false").lower() in ("true", "1", "yes"):
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif resend_key:
        return _send_via_resend(recipient_email, subject, text_body, html_body)
    elif smtp_host:
        return _send_via_smtp(recipient_email, subject, text_body, html_body=html_body, incident_id=0)
    else:
        return NotificationResult(status="FAILED", provider="unconfigured", channel="EMAIL", error_message="Email unconfigured")

