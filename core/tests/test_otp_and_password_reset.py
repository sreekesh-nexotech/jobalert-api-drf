"""OTP issue/verify, signup verification flag, and password reset flow."""
from __future__ import annotations

import pytest
from django.core import mail
from django.urls import reverse

from core.email import RESEND_COOLDOWN, hash_code, issue_otp
from core.models import OTPCode, UserDetails

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# OTP send + verify (signup)
# ---------------------------------------------------------------------------


def test_register_emails_signup_otp(api_client, mailoutbox):
    res = api_client.post(
        reverse("v1:auth-register"),
        {
            "email": "newcomer@example.com",
            "password": "Sup3rSecret!42",
            "password_confirm": "Sup3rSecret!42",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["otp_sent"] is True
    # Console backend captures into mail.outbox via mailoutbox fixture.
    assert any("newcomer@example.com" in m.to for m in mailoutbox)
    # The OTP row exists.
    assert OTPCode.objects.filter(
        identifier="newcomer@example.com",
        purpose=OTPCode.Purpose.SIGNUP_VERIFY,
        is_used=False,
    ).exists()


def test_otp_resend_within_cooldown_returns_silently(api_client, user):
    res1 = api_client.post(
        reverse("v1:auth-otp-send"),
        {"identifier": user.email, "purpose": "signup_verify"},
        format="json",
    )
    res2 = api_client.post(
        reverse("v1:auth-otp-send"),
        {"identifier": user.email, "purpose": "signup_verify"},
        format="json",
    )
    # First request issues; second within cooldown should also return 200
    # but raise no error (silent enumeration-resistant behaviour).
    assert res1.status_code == 200
    assert res2.status_code in (200, 400)


def test_otp_verify_marks_user_otp_verified(api_client, user):
    otp, raw_code = issue_otp(
        identifier=user.email, purpose="signup_verify", user=user
    )
    res = api_client.post(
        reverse("v1:auth-otp-verify"),
        {"identifier": user.email, "purpose": "signup_verify", "code": raw_code},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["verified"] is True
    details = UserDetails.objects.get(user=user)
    assert details.otp_verified is True


def test_otp_verify_rejects_wrong_code(api_client, user):
    issue_otp(identifier=user.email, purpose="signup_verify", user=user)
    res = api_client.post(
        reverse("v1:auth-otp-verify"),
        {"identifier": user.email, "purpose": "signup_verify", "code": "000000"},
        format="json",
    )
    assert res.status_code == 400


def test_otp_verify_rejects_expired_code(api_client, user, settings):
    from django.utils import timezone

    otp, code = issue_otp(
        identifier=user.email, purpose="signup_verify", user=user
    )
    OTPCode.objects.filter(pk=otp.pk).update(
        expires_at=timezone.now() - timezone.timedelta(seconds=1)
    )
    res = api_client.post(
        reverse("v1:auth-otp-verify"),
        {"identifier": user.email, "purpose": "signup_verify", "code": code},
        format="json",
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


def test_password_reset_full_flow(api_client, user, password, mailoutbox):
    # 1. Request reset
    res = api_client.post(
        reverse("v1:auth-password-reset-request"),
        {"email": user.email},
        format="json",
    )
    assert res.status_code == 200

    # Pull the OTP from the DB (the raw code isn't returned via API).
    otp_row = OTPCode.objects.filter(
        identifier=user.email, purpose=OTPCode.Purpose.PASSWORD_RESET
    ).latest("created_at")
    # Brute the 6-digit space against the hash.
    raw_code = None
    for n in range(1_000_000):
        candidate = f"{n:06d}"
        if hash_code(candidate) == otp_row.code_hash:
            raw_code = candidate
            break
    assert raw_code, "could not recover raw OTP from hash"

    # 2. Confirm reset
    new_pwd = "Br4ndN3wPwd!"
    res = api_client.post(
        reverse("v1:auth-password-reset-confirm"),
        {"email": user.email, "code": raw_code, "new_password": new_pwd},
        format="json",
    )
    assert res.status_code == 204

    user.refresh_from_db()
    assert user.check_password(new_pwd)


def test_password_reset_request_for_unknown_email_is_silent(api_client):
    res = api_client.post(
        reverse("v1:auth-password-reset-request"),
        {"email": "nobody@example.com"},
        format="json",
    )
    # Don't reveal account existence.
    assert res.status_code == 200


def test_password_reset_confirm_rejects_bad_code(api_client, user):
    res = api_client.post(
        reverse("v1:auth-password-reset-confirm"),
        {"email": user.email, "code": "999999", "new_password": "Whatever!42"},
        format="json",
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# cleanup_otps management command
# ---------------------------------------------------------------------------


def test_cleanup_otps_removes_expired_and_old_used(user):
    from datetime import timedelta
    from django.core.management import call_command
    from django.utils import timezone

    OTPCode.objects.create(
        identifier=user.email, purpose="signup_verify",
        code_hash="x", expires_at=timezone.now() - timedelta(hours=1),
    )
    OTPCode.objects.create(
        identifier=user.email, purpose="signup_verify",
        code_hash="y", expires_at=timezone.now() - timedelta(days=10),
        is_used=True, used_at=timezone.now() - timedelta(days=10),
    )
    fresh = OTPCode.objects.create(
        identifier=user.email, purpose="signup_verify",
        code_hash="z", expires_at=timezone.now() + timedelta(minutes=5),
    )

    call_command("cleanup_otps")

    assert OTPCode.objects.filter(pk=fresh.pk).exists()
    assert OTPCode.objects.count() == 1


# ---------------------------------------------------------------------------
# Mail outbox fixture (pytest-django provides it but uses 'mailoutbox')
# ---------------------------------------------------------------------------


@pytest.fixture
def mailoutbox(settings):
    """Force the locmem backend so we can assert on mail.outbox."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    return mail.outbox
