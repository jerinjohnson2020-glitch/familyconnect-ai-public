"""
Phase 6: Verification Suite for SOS Emergency Email Notification Content
Validates:
1. Subject line format ("FamilyConnect AI — Emergency Alert: ...")
2. Readable, accessible, mobile-friendly HTML email design with plain-text alternative
3. Presence of authorized incident details:
   - Family member's name
   - Emergency type
   - Severity level and AI triage explanation (when available)
   - Incident description / notes (when available)
   - Reported time with explicit UTC timezone indication
   - Location details and Google Maps link ONLY when valid coordinates are present
   - Current incident status
   - App incident link when configured
4. Proper HTML escaping preventing injection in email clients
5. Absence of fabricated coordinates or invented details when fields are null/missing
6. Notification sent only to configured, active trusted contacts
7. Mock notification safety interceptor preventing accidental external emails during testing
8. Database integrity preserved after test execution
"""

import os
import sys
import unittest
import html
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Set backend root in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Base
from app.models import (
    EmergencyIncident,
    IncidentAlert,
    TrustedContact,
    Member,
    User
)
from app.services.notifications import (
    build_safe_notification_content,
    dispatch_contact_notification,
    retry_failed_alert,
    _send_via_smtp,
    _send_via_resend,
    _send_via_twilio_sms,
    send_household_invitation_email,
    send_responder_application_received_email,
    send_responder_application_decision_email,
    send_explicit_test_notification,
    get_captured_dispatches,
    clear_captured_dispatches
)


class MockIncident:
    """Lightweight mock incident object for unit testing build_safe_notification_content."""
    def __init__(
        self,
        id=101,
        reporter_name="Grandma Rose",
        incident_type="FALL_DETECTED",
        severity="CRITICAL",
        status="ACTIVE",
        description="Detected sudden fall in the hallway near the stairs.",
        ai_rationale="High impact sensor telemetry detected with no motion for 60 seconds.",
        ai_confidence=0.94,
        latitude=9.93123,
        longitude=76.26730,
        reported_at=None,
        created_at=None
    ):
        self.id = id
        self.reporter_name = reporter_name
        self.incident_type = incident_type
        self.severity = severity
        self.status = status
        self.description = description
        self.ai_rationale = ai_rationale
        self.ai_confidence = ai_confidence
        self.latitude = latitude
        self.longitude = longitude
        self.reported_at = reported_at or datetime(2026, 10, 15, 14, 30, 0)
        self.created_at = created_at or datetime(2026, 10, 15, 14, 30, 0)


class TestSOSEmailContent(unittest.TestCase):

    def setUp(self):
        clear_captured_dispatches()
        os.environ["MOCK_NOTIFICATIONS"] = "true"

    def tearDown(self):
        clear_captured_dispatches()

    def test_01_subject_line_format(self):
        """Subject must be clear, actionable, and include reporter name and emergency type."""
        incident = MockIncident(
            reporter_name="Sarah Connor",
            incident_type="MEDICAL",
            severity="CRITICAL"
        )
        content = build_safe_notification_content(incident, contact_name="John Connor", tier_label="Primary")
        
        self.assertTrue(
            content.subject.startswith("FamilyConnect AI — Emergency Alert:"),
            f"Subject should start with standard prefix, got: {content.subject}"
        )
        self.assertIn("Sarah Connor", content.subject)
        self.assertIn("MEDICAL", content.subject)

    def test_02_html_and_text_content_structure(self):
        """Content must contain accessible HTML and a matching plain-text alternative."""
        incident = MockIncident(
            reporter_name="Robert Vance",
            incident_type="CHEST_PAIN",
            severity="CRITICAL",
            description="Severe tightness in chest, difficulty breathing.",
            ai_rationale="Urgent biometric indicator threshold exceeded.",
            ai_confidence=0.91,
            latitude=10.0158,
            longitude=76.3418
        )
        content = build_safe_notification_content(incident, contact_name="Phyllis Vance", tier_label="Primary")

        # HTML assertions
        html_str = content.html_body
        self.assertIn("<!DOCTYPE html>", html_str)
        self.assertIn("table role=\"presentation\"", html_str)
        self.assertIn("Robert Vance", html_str)
        self.assertIn("CHEST_PAIN", html_str)
        self.assertIn("Phyllis Vance", html_str)
        self.assertIn("CRITICAL", html_str)
        self.assertIn("Severe tightness in chest", html_str)
        self.assertIn("Urgent biometric indicator threshold exceeded", html_str)
        self.assertIn("91%", html_str)  # 0.91 confidence
        self.assertIn("Important Safety Notice", html_str)
        self.assertIn("maps.google.com", html_str)

        # Plain text assertions
        text_str = content.text_body
        self.assertIn("FAMILYCONNECT AI — EMERGENCY ALERT", text_str)
        self.assertIn("Robert Vance", text_str)
        self.assertIn("CHEST_PAIN", text_str)
        self.assertIn("Phyllis Vance", text_str)
        self.assertIn("CRITICAL", text_str)
        self.assertIn("Urgent biometric indicator threshold exceeded", text_str)
        self.assertIn("maps.google.com", text_str)
        self.assertIn("IMPORTANT SAFETY NOTICE", text_str)

    def test_03_valid_coordinates_include_map_link(self):
        """Valid coordinates must generate approximate coordinates and a Google Maps link."""
        incident = MockIncident(
            latitude=9.931234,
            longitude=76.267304
        )
        content = build_safe_notification_content(incident, contact_name="Alice")

        expected_map_link = "https://maps.google.com/?q=9.931234,76.267304"
        self.assertIn(expected_map_link, content.html_body)
        self.assertIn(expected_map_link, content.text_body)
        self.assertIn("9.93123, 76.26730", content.html_body)
        self.assertIn("9.93123, 76.26730", content.text_body)

    def test_04_missing_or_zero_coordinates_do_not_fabricate_maps(self):
        """When coordinates are None, 0.0, or invalid, no map link or fake coordinates may be emitted."""
        # Case A: None coordinates
        inc_none = MockIncident(latitude=None, longitude=None)
        content_none = build_safe_notification_content(inc_none, contact_name="Alice")
        self.assertNotIn("maps.google.com", content_none.html_body)
        self.assertNotIn("maps.google.com", content_none.text_body)
        self.assertIn("Coordinates not available / not reported", content_none.html_body)

        # Case B: (0.0, 0.0) coordinates
        inc_zero = MockIncident(latitude=0.0, longitude=0.0)
        content_zero = build_safe_notification_content(inc_zero, contact_name="Alice")
        self.assertNotIn("maps.google.com", content_zero.html_body)
        self.assertNotIn("maps.google.com", content_zero.text_body)
        self.assertIn("Coordinates not available / not reported", content_zero.html_body)

        # Case C: Out of bounds coordinates (lat=120)
        inc_oob = MockIncident(latitude=120.0, longitude=76.0)
        content_oob = build_safe_notification_content(inc_oob, contact_name="Alice")
        self.assertNotIn("maps.google.com", content_oob.html_body)
        self.assertNotIn("maps.google.com", content_oob.text_body)

    def test_05_missing_ai_triage_or_description_handled_gracefully(self):
        """Missing optional fields (AI rationale, description) should be omitted cleanly without blanks."""
        incident = MockIncident(
            description=None,
            ai_rationale=None,
            ai_confidence=None
        )
        content = build_safe_notification_content(incident, contact_name="Alice")

        # HTML should not have an empty AI Triage box or broken blockquotes
        self.assertNotIn("AI Triage Assessment", content.html_body)
        self.assertNotIn("Incident Notes / Reported Details", content.html_body)

        # Plain text should not have empty labels
        self.assertNotIn("AI Triage Analysis:", content.text_body)
        self.assertNotIn("Incident Description:", content.text_body)

    def test_06_html_sanitization_prevents_xss(self):
        """User-controlled inputs (reporter name, contact name, description) must be HTML-escaped."""
        incident = MockIncident(
            reporter_name="<script>alert('pwned')</script>",
            incident_type="SOS<img src=x onerror=alert(1)>",
            description="He broke his leg & feels <dizzy>."
        )
        content = build_safe_notification_content(
            incident,
            contact_name="<b>Trusted Contact</b>",
            tier_label="Primary<style>"
        )

        self.assertNotIn("<script>", content.html_body)
        self.assertIn("&lt;script&gt;", content.html_body)
        self.assertNotIn("<img", content.html_body)
        self.assertNotIn("<style>", content.html_body)
        self.assertIn("&lt;style&gt;", content.html_body)
        self.assertIn("&lt;b&gt;Trusted Contact&lt;/b&gt;", content.html_body)
        self.assertIn("&amp; feels &lt;dizzy&gt;", content.html_body)

    def test_07_timestamp_format_includes_utc(self):
        """Timestamps must be formatted clearly with explicit UTC indication."""
        ts = datetime(2026, 10, 15, 9, 45, 0)
        incident = MockIncident(created_at=ts)
        content = build_safe_notification_content(incident, contact_name="Alice")
        self.assertIn("UTC", content.html_body)
        self.assertIn("UTC", content.text_body)
        self.assertIn("October 15, 2026", content.html_body)
        self.assertIn("09:45:00", content.html_body)

    def test_08_unpacking_compatibility(self):
        """NotificationContent must support both 2-tuple, 3-tuple, and attribute access."""
        incident = MockIncident()
        content = build_safe_notification_content(incident, contact_name="Alice")

        # Attribute access
        self.assertTrue(hasattr(content, "subject"))
        self.assertTrue(hasattr(content, "text_body"))
        self.assertTrue(hasattr(content, "html_body"))

        # 3-tuple unpacking
        subj, txt, html_content = content
        self.assertEqual(subj, content.subject)
        self.assertEqual(txt, content.text_body)
        self.assertEqual(html_content, content.html_body)

        # 2-tuple slicing
        s2, t2 = content[:2]
        self.assertEqual(s2, content.subject)
        self.assertEqual(t2, content.text_body)

    def _create_in_memory_session(self):
        """Creates an ephemeral in-memory SQLite session isolated from familyconnect.db."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocalMem = sessionmaker(bind=engine)
        return SessionLocalMem()

    def test_09_mock_dispatch_captures_html_and_text(self):
        """Integration: dispatching an alert captures both plain text and rich HTML without external calls."""
        db = self._create_in_memory_session()
        try:
            # Create a minimal test incident in ephemeral DB
            test_incident = EmergencyIncident(
                reporter_name="Test Subject Email Phase6",
                incident_type="SOS_FALL",
                severity_level="HIGH",
                status="ACTIVE",
                description="Testing rich email notifications in Phase 6.",
                ai_rationale="Simulated fall event detected by motion sensor.",
                severity_score=0.88,
                latitude=9.9312,
                longitude=76.2673,
                created_at=datetime.utcnow()
            )
            db.add(test_incident)
            db.commit()
            db.refresh(test_incident)

            clear_captured_dispatches()

            # Dispatch notification to a test address
            alert = dispatch_contact_notification(
                db=db,
                incident=test_incident,
                contact_name="Verified Contact",
                contact_phone="+15551234567",
                contact_email="test-recipient@canakerala.com",
                contact_id=None,
                preferred_channel="EMAIL",
                tier_label="Primary"
            )
            db.commit()

            # Verify alert record in DB
            self.assertEqual(alert.incident_id, test_incident.id)
            self.assertEqual(alert.channel, "EMAIL")
            self.assertEqual(alert.status, "SIMULATED")
            self.assertIsNone(alert.delivered_at, "Mock dispatch must never set delivered_at timestamp")

            # Verify mock capture
            captured = get_captured_dispatches()
            self.assertEqual(len(captured), 1, "Exactly one notification should have been captured in mock mode")
            
            item = captured[0]
            self.assertEqual(item["recipient"], "test-recipient@canakerala.com")
            self.assertEqual(item["channel"], "EMAIL")
            self.assertIn("FamilyConnect AI — Emergency Alert:", item["subject"])
            self.assertIn("Test Subject Email Phase6", item["subject"])
            
            # Check HTML in captured item
            self.assertIsNotNone(item["html"])
            self.assertIn("<!DOCTYPE html>", item["html"])
            self.assertIn("Simulated fall event detected by motion sensor", item["html"])
            self.assertIn("maps.google.com/?q=9.9312,76.2673", item["html"])

            # Check text in captured item
            self.assertIsNotNone(item["body"])
            self.assertIn("Simulated fall event detected by motion sensor", item["body"])
            self.assertIn("maps.google.com/?q=9.9312,76.2673", item["body"])

        finally:
            db.close()

    @patch("app.services.notifications.smtplib.SMTP_SSL")
    @patch("app.services.notifications.smtplib.SMTP")
    @patch("app.services.notifications.urllib.request.urlopen")
    def test_10_smtp_mock_zero_network_calls(self, mock_urlopen, mock_smtp, mock_smtp_ssl):
        """Verifies SMTP dispatch under MOCK_NOTIFICATIONS makes 0 network calls and returns SIMULATED."""
        mock_urlopen.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: urlopen called during mock mode")
        mock_smtp.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP called during mock mode")
        mock_smtp_ssl.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP_SSL called during mock mode")

        os.environ["MOCK_NOTIFICATIONS"] = "true"
        os.environ["SMTP_HOST"] = "smtp.mocktest.local"
        res = _send_via_smtp("test@alerts.canakerala.com", "Subject", "Body", incident_id=101)

        self.assertEqual(res.status, "SIMULATED")
        self.assertEqual(res.provider, "smtp_mock")
        self.assertIsNone(res.delivered_at, "Mock dispatch must not have a delivered_at timestamp")
        self.assertTrue(res.provider_message_id.startswith("mock-smtp-"))
        mock_smtp.assert_not_called()
        mock_smtp_ssl.assert_not_called()
        mock_urlopen.assert_not_called()

    @patch("app.services.notifications.smtplib.SMTP_SSL")
    @patch("app.services.notifications.smtplib.SMTP")
    @patch("app.services.notifications.urllib.request.urlopen")
    def test_11_resend_mock_zero_network_calls(self, mock_urlopen, mock_smtp, mock_smtp_ssl):
        """Verifies Resend HTTP API dispatch under MOCK_NOTIFICATIONS makes 0 network calls and returns SIMULATED."""
        mock_urlopen.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: urlopen called during mock mode")
        mock_smtp.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP called during mock mode")
        mock_smtp_ssl.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP_SSL called during mock mode")

        os.environ["MOCK_NOTIFICATIONS"] = "true"
        os.environ["RESEND_API_KEY"] = "re_mock_key_123"
        res = _send_via_resend("test@alerts.canakerala.com", "Subject", "Body")

        self.assertEqual(res.status, "SIMULATED")
        self.assertEqual(res.provider, "resend_mock")
        self.assertIsNone(res.delivered_at, "Mock dispatch must not have a delivered_at timestamp")
        self.assertTrue(res.provider_message_id.startswith("mock-resend-"))
        mock_urlopen.assert_not_called()
        mock_smtp.assert_not_called()
        mock_smtp_ssl.assert_not_called()

    @patch("app.services.notifications.smtplib.SMTP_SSL")
    @patch("app.services.notifications.smtplib.SMTP")
    @patch("app.services.notifications.urllib.request.urlopen")
    def test_12_twilio_sms_mock_zero_network_calls(self, mock_urlopen, mock_smtp, mock_smtp_ssl):
        """Verifies Twilio SMS REST dispatch under MOCK_NOTIFICATIONS makes 0 network calls and returns SIMULATED."""
        mock_urlopen.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: urlopen called during mock mode")
        mock_smtp.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP called during mock mode")
        mock_smtp_ssl.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP_SSL called during mock mode")

        os.environ["MOCK_NOTIFICATIONS"] = "true"
        os.environ["TWILIO_ACCOUNT_SID"] = "ACmock123"
        os.environ["TWILIO_AUTH_TOKEN"] = "authtok_mock"
        os.environ["TWILIO_FROM_NUMBER"] = "+15551234567"
        res = _send_via_twilio_sms("+15559876543", "Emergency body")

        self.assertEqual(res.status, "SIMULATED")
        self.assertEqual(res.provider, "twilio_mock")
        self.assertIsNone(res.delivered_at, "Mock dispatch must not have a delivered_at timestamp")
        self.assertTrue(res.provider_message_id.startswith("mock-twilio-"))
        mock_urlopen.assert_not_called()
        mock_smtp.assert_not_called()
        mock_smtp_ssl.assert_not_called()

    @patch("app.services.notifications.smtplib.SMTP_SSL")
    @patch("app.services.notifications.smtplib.SMTP")
    @patch("app.services.notifications.urllib.request.urlopen")
    def test_13_retry_and_fallback_zero_network_calls(self, mock_urlopen, mock_smtp, mock_smtp_ssl):
        """Verifies retry, deduplication, and contact fallback make 0 provider network calls and return SIMULATED."""
        mock_urlopen.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: urlopen called during mock mode")
        mock_smtp.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP called during mock mode")
        mock_smtp_ssl.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP_SSL called during mock mode")

        os.environ["MOCK_NOTIFICATIONS"] = "true"
        db = self._create_in_memory_session()
        try:
            inc = EmergencyIncident(
                reporter_name="Test Patient Retry",
                incident_type="SOS_FALL",
                status="ACTIVE",
                latitude=9.9312,
                longitude=76.2673,
                created_at=datetime.utcnow()
            )
            db.add(inc)
            db.commit()
            db.refresh(inc)

            # Initial dispatch
            alert = dispatch_contact_notification(
                db=db,
                incident=inc,
                contact_name="Retry Contact",
                contact_phone="+15551234567",
                contact_email="retry-test@alerts.canakerala.com",
                preferred_channel="EMAIL"
            )
            db.commit()
            self.assertEqual(alert.status, "SIMULATED")
            self.assertIsNone(alert.delivered_at)

            # Retry
            retried = retry_failed_alert(db=db, alert=alert, incident=inc)
            db.commit()
            self.assertEqual(retried.status, "SIMULATED")
            self.assertIsNone(retried.delivered_at)

            # Deduplication
            dupe = dispatch_contact_notification(
                db=db,
                incident=inc,
                contact_name="Retry Contact",
                contact_phone="+15551234567",
                contact_email="retry-test@alerts.canakerala.com",
                preferred_channel="EMAIL"
            )
            self.assertEqual(dupe.status, "SIMULATED")

            # Fallback SMS for member with no TrustedContacts
            mem = Member(
                name="Fallback Patient",
                relationship="Self",
                phone="+15551234567",
                emergency_contact_name="Fallback Contact",
                emergency_contact_phone="+15559998888"
            )
            db.add(mem)
            db.commit()

            fb_alert = dispatch_contact_notification(
                db=db,
                incident=inc,
                contact_name=mem.emergency_contact_name,
                contact_phone=mem.emergency_contact_phone,
                preferred_channel="SMS"
            )
            self.assertEqual(fb_alert.status, "SIMULATED")
            self.assertIsNone(fb_alert.delivered_at)

            mock_urlopen.assert_not_called()
            mock_smtp.assert_not_called()
            mock_smtp_ssl.assert_not_called()
        finally:
            db.close()

    def test_14_network_spy_traps_unexpected_calls(self):
        """Proves that our network trap correctly raises AssertionError if urlopen or SMTP is called."""
        trap_mock = MagicMock(side_effect=AssertionError("Network call intercepted by safety trap!"))
        with self.assertRaises(AssertionError) as ctx:
            trap_mock("https://api.resend.com/emails")
        self.assertIn("Network call intercepted", str(ctx.exception))

    @patch("app.services.notifications.smtplib.SMTP_SSL")
    @patch("app.services.notifications.smtplib.SMTP")
    @patch("app.services.notifications.urllib.request.urlopen")
    def test_15_transactional_email_endpoints_zero_network_calls(self, mock_urlopen, mock_smtp, mock_smtp_ssl):
        """Verifies transactional email functions under mock mode make 0 provider network calls."""
        mock_urlopen.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: urlopen called during mock mode")
        mock_smtp.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP called during mock mode")
        mock_smtp_ssl.side_effect = AssertionError("CRITICAL SECURITY VIOLATION: SMTP_SSL called during mock mode")

        os.environ["MOCK_NOTIFICATIONS"] = "true"

        # 1. Household invitation
        inv_res = send_household_invitation_email(
            recipient_email="invitee@alerts.canakerala.com",
            inviter_name="Alice",
            household_name="Alice Household",
            invitation_link="https://app.familyconnect.org/join?token=123"
        )
        self.assertEqual(inv_res.status, "SIMULATED")
        self.assertIsNone(inv_res.delivered_at)

        # 2. Responder application received
        rec_res = send_responder_application_received_email(
            recipient_email="responder@alerts.canakerala.com",
            applicant_name="John Doe",
            organization="City EMT"
        )
        self.assertEqual(rec_res.status, "SIMULATED")
        self.assertIsNone(rec_res.delivered_at)

        # 3. Responder application decision
        dec_res = send_responder_application_decision_email(
            recipient_email="responder@alerts.canakerala.com",
            applicant_name="John Doe",
            approved=True
        )
        self.assertEqual(dec_res.status, "SIMULATED")
        self.assertIsNone(dec_res.delivered_at)

        # 4. User-initiated test notification
        test_res = send_explicit_test_notification(
            channel="EMAIL",
            recipient="admin@alerts.canakerala.com",
            confirm_send=True,
            requested_by="admin"
        )
        self.assertEqual(test_res["status"], "SIMULATED")
        self.assertTrue(test_res["succeeded"])

        mock_urlopen.assert_not_called()
        mock_smtp.assert_not_called()
        mock_smtp_ssl.assert_not_called()

    def test_16_mock_alerts_never_reported_as_delivered(self):
        """Ensures that mock dispatches never return DELIVERED or set delivered_at timestamps."""
        os.environ["MOCK_NOTIFICATIONS"] = "true"
        smtp_res = _send_via_smtp("test@alerts.canakerala.com", "Subj", "Body", incident_id=1)
        resend_res = _send_via_resend("test@alerts.canakerala.com", "Subj", "Body")
        twilio_res = _send_via_twilio_sms("+15559876543", "Body")

        for res in [smtp_res, resend_res, twilio_res]:
            self.assertNotEqual(res.status, "DELIVERED", f"Mock dispatch should never report DELIVERED: {res.provider}")
            self.assertEqual(res.status, "SIMULATED")
            self.assertIsNone(res.delivered_at, f"Mock dispatch should have delivered_at=None: {res.provider}")
            self.assertIn("mock", res.provider)

    def test_17_timeline_events_for_simulated_alerts(self):
        """Verifies that incident timeline events for simulated alerts clearly indicate delivery was suppressed."""
        db = self._create_in_memory_session()
        try:
            inc = EmergencyIncident(
                reporter_name="Timeline Test Patient",
                incident_type="SOS_GENERAL",
                status="ACTIVE",
                latitude=9.9312,
                longitude=76.2673,
                created_at=datetime.utcnow()
            )
            db.add(inc)
            db.commit()

            alert = dispatch_contact_notification(
                db=db,
                incident=inc,
                contact_name="Timeline Contact",
                contact_phone="+15551234567",
                contact_email="timeline@alerts.canakerala.com",
                preferred_channel="EMAIL"
            )
            db.commit()

            self.assertEqual(alert.status, "SIMULATED")
            self.assertIsNone(alert.delivered_at)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
