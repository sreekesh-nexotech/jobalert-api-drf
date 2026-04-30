"""Email + OTP helpers.

OTP storage
-----------
We never persist the raw 6-digit code. ``hash_code()`` produces a salted
hash that's stored in :class:`OTPCode.code_hash`. ``check_code()`` does a
constant-time comparison.

Email
-----
``send_otp_email`` wraps Django's mail framework. Configure the SMTP
backend through the standard ``EMAIL_*`` env vars (Workspace SMTP works
out of the box — see ``.env.example``). In dev, leave ``EMAIL_BACKEND``
unset and the console backend prints the email to stdout.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from core.models import OTPCode

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=30)


def _generate_code() -> str:
    """Return a numeric OTP, zero-padded to OTP_LENGTH digits."""
    upper = 10 ** OTP_LENGTH
    return f"{secrets.randbelow(upper):0{OTP_LENGTH}d}"


def hash_code(code: str) -> str:
    """Salted SHA-256 hash. SECRET_KEY is the salt — fine for short-lived OTPs."""
    return sha256(f"{settings.SECRET_KEY}:{code}".encode()).hexdigest()


def check_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)


def issue_otp(*, identifier: str, purpose: str, user=None) -> tuple[OTPCode, str]:
    """Create-or-rotate an OTP for ``(identifier, purpose)`` and return the
    DB row plus the raw code (caller is responsible for delivering it).

    Resending within ``RESEND_COOLDOWN`` of the previous issue raises
    ``ValueError`` so the view can return 429.
    """
    identifier = identifier.lower().strip()

    existing = (
        OTPCode.objects.filter(identifier=identifier, purpose=purpose, is_used=False)
        .order_by("-created_at")
        .first()
    )
    if existing and (timezone.now() - existing.created_at) < RESEND_COOLDOWN:
        raise ValueError("Please wait before requesting another code.")

    # Invalidate any prior unused OTPs for this purpose.
    OTPCode.objects.filter(
        identifier=identifier, purpose=purpose, is_used=False
    ).update(is_used=True, used_at=timezone.now())

    code = _generate_code()
    otp = OTPCode.objects.create(
        identifier=identifier,
        purpose=purpose,
        code_hash=hash_code(code),
        expires_at=timezone.now() + OTP_TTL,
        user=user,
    )
    return otp, code


def consume_otp(*, identifier: str, purpose: str, code: str) -> OTPCode:
    """Validate ``code`` against the most-recent unused OTP for the pair.

    Raises ``ValueError`` with a user-safe message on every failure path
    (no code, expired, too many attempts, mismatch).
    On success the row is marked used and returned (in case the caller
    wants the bound user).
    """
    identifier = identifier.lower().strip()
    otp = (
        OTPCode.objects.filter(
            identifier=identifier, purpose=purpose, is_used=False
        )
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        raise ValueError("No active code. Please request a new one.")
    if otp.expires_at < timezone.now():
        raise ValueError("Code has expired. Please request a new one.")
    if otp.attempts >= otp.max_attempts:
        raise ValueError("Too many failed attempts. Please request a new code.")

    if not check_code(code, otp.code_hash):
        OTPCode.objects.filter(pk=otp.pk).update(attempts=otp.attempts + 1)
        raise ValueError("Incorrect code.")

    otp.is_used = True
    otp.used_at = timezone.now()
    otp.save(update_fields=["is_used", "used_at"])
    return otp


def send_otp_email(*, email: str, code: str, purpose: str) -> None:
    """Best-effort email send. Subject / body templated for the two purposes."""
    if purpose == OTPCode.Purpose.SIGNUP_VERIFY:
        subject = "Verify your Job Alert account"
        body = (
            f"Welcome to Job Alert!\n\n"
            f"Your verification code is: {code}\n\n"
            f"This code expires in 10 minutes. If you didn't sign up, you can "
            f"ignore this email."
        )
    else:
        subject = "Reset your Job Alert password"
        body = (
            f"We received a request to reset your password.\n\n"
            f"Your reset code is: {code}\n\n"
            f"This code expires in 10 minutes. If you didn't request a reset, "
            f"please ignore this email and your password will stay unchanged."
        )
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=[email],
        fail_silently=False,
    )
