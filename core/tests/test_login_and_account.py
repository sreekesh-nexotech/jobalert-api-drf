"""Login by email/mobile, account deletion, avatar, profile stats."""
from __future__ import annotations

import io

import pytest
from django.urls import reverse
from PIL import Image

from core.models import UserDetails

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Login by mobile / email
# ---------------------------------------------------------------------------


def test_login_by_email_succeeds(api_client, user, password):
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert "access" in res.data and "refresh" in res.data


def test_login_by_mobile_number_succeeds(api_client, make_user, password):
    user = make_user(country_code="+91", mobile_number="9876543210")
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": "9876543210", "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["user"]["mobile_number"] == "9876543210"


def test_login_with_country_code_filter(api_client, make_user, password):
    # Two users share the same digits but different country codes.
    in_user = make_user(country_code="+91", mobile_number="9000000000")
    us_user = make_user(country_code="+1",  mobile_number="9000000000")
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": "9000000000", "country_code": "+1", "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["user"]["uid"] == str(us_user.uid)


def test_login_invalid_password_returns_401(api_client, user):
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": "nope"},
        format="json",
    )
    assert res.status_code == 401


def test_login_unknown_identifier(api_client):
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": "ghost@example.com", "password": "x"},
        format="json",
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Mobile uniqueness on register
# ---------------------------------------------------------------------------


def test_register_rejects_duplicate_mobile(api_client, make_user):
    make_user(country_code="+91", mobile_number="9876543210")
    res = api_client.post(
        reverse("v1:auth-register"),
        {
            "email": "second@example.com",
            "password": "Sup3rSecret!42",
            "password_confirm": "Sup3rSecret!42",
            "country_code": "+91",
            "mobile_number": "9876543210",
        },
        format="json",
    )
    assert res.status_code == 400


def test_register_strips_non_digits_from_mobile(api_client):
    res = api_client.post(
        reverse("v1:auth-register"),
        {
            "email": "fresh@example.com",
            "password": "Sup3rSecret!42",
            "password_confirm": "Sup3rSecret!42",
            "country_code": "+91",
            "mobile_number": "98 7654-3210",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["user"]["mobile_number"] == "9876543210"


# ---------------------------------------------------------------------------
# Account deletion request
# ---------------------------------------------------------------------------


def test_request_account_deletion_flips_status(auth_client, user):
    res = auth_client.post(reverse("v1:user-me-request-deletion"))
    assert res.status_code == 200
    details = UserDetails.objects.get(user=user)
    assert details.account_status == UserDetails.AccountStatus.DELETION_REQUESTED
    assert details.deletion_requested_at is not None


def test_anonymous_cannot_request_deletion(api_client):
    res = api_client.post(reverse("v1:user-me-request-deletion"))
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Avatar upload
# ---------------------------------------------------------------------------


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buf, format="PNG")
    return buf.getvalue()


def test_avatar_upload_stores_url_on_user_details(auth_client, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("me.png", _png_bytes(), content_type="image/png")
    res = auth_client.post(
        reverse("v1:user-me-avatar"),
        {"image": upload},
        format="multipart",
    )
    assert res.status_code == 200
    assert res.data["profile_picture_url"].startswith("http")
    assert res.data["profile_picture_url"].endswith(".png")
    details = UserDetails.objects.get(user=user)
    assert details.profile_picture_url == res.data["profile_picture_url"]


# ---------------------------------------------------------------------------
# Profile stats
# ---------------------------------------------------------------------------


def test_profile_stats_includes_progress_pct(auth_client, user):
    UserDetails.objects.filter(user=user).update(total_points=300)
    res = auth_client.get(reverse("v1:user-me-stats"))
    assert res.status_code == 200
    assert res.data["points"] == 300
    assert res.data["next_level"] == "champion"
    assert res.data["next_level_at"] == 500
    # 300 / 500 = 60%
    assert res.data["progress_pct"] == 60


def test_profile_stats_at_top_level(auth_client, user):
    UserDetails.objects.filter(user=user).update(total_points=1500)
    res = auth_client.get(reverse("v1:user-me-stats"))
    assert res.data["next_level"] is None
    assert res.data["progress_pct"] == 100
