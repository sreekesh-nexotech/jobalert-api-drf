"""Auth: register, login, refresh, logout, change password, /users/me/."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import UserDetails

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


def test_register_creates_user_and_details_and_returns_tokens(api_client):
    payload = {
        "email": "new@example.com",
        "username": "newbie",
        "password": "Sup3rSecret!42",
        "password_confirm": "Sup3rSecret!42",
    }
    res = api_client.post(reverse("v1:auth-register"), payload, format="json")
    assert res.status_code == 201, res.content
    assert "access" in res.data and "refresh" in res.data
    assert res.data["user"]["email"] == "new@example.com"

    user = User.objects.get(email="new@example.com")
    assert UserDetails.objects.filter(user=user).exists()


def test_register_rejects_duplicate_email(api_client, user):
    payload = {
        "email": user.email,
        "password": "Sup3rSecret!42",
        "password_confirm": "Sup3rSecret!42",
    }
    res = api_client.post(reverse("v1:auth-register"), payload, format="json")
    assert res.status_code == 400


def test_register_rejects_password_mismatch(api_client):
    payload = {
        "email": "x@example.com",
        "password": "Sup3rSecret!42",
        "password_confirm": "different!",
    }
    res = api_client.post(reverse("v1:auth-register"), payload, format="json")
    assert res.status_code == 400


def test_register_is_unauthenticated(api_client):
    """Anonymous users must be able to register."""
    res = api_client.post(
        reverse("v1:auth-register"),
        {
            "email": "anon@example.com",
            "password": "Sup3rSecret!42",
            "password_confirm": "Sup3rSecret!42",
        },
        format="json",
    )
    assert res.status_code == 201


# ---------------------------------------------------------------------------
# Login + refresh + logout
# ---------------------------------------------------------------------------


def test_login_returns_jwt_pair(api_client, user, password):
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": password},
        format="json",
    )
    assert res.status_code == 200
    assert "access" in res.data and "refresh" in res.data


def test_login_with_wrong_password_fails(api_client, user):
    res = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": "wrong"},
        format="json",
    )
    assert res.status_code == 401


def test_refresh_rotates_token(api_client, user, password):
    login = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": password},
        format="json",
    )
    refresh = login.data["refresh"]
    res = api_client.post(reverse("v1:auth-refresh"), {"refresh": refresh}, format="json")
    assert res.status_code == 200
    assert "access" in res.data


def test_logout_blacklists_refresh_token(api_client, user, password):
    login = api_client.post(
        reverse("v1:auth-login"),
        {"identifier": user.email, "password": password},
        format="json",
    )
    refresh = login.data["refresh"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    res = api_client.post(reverse("v1:auth-logout"), {"refresh": refresh}, format="json")
    assert res.status_code == 205
    # Reusing the blacklisted refresh should now fail.
    api_client.credentials()
    again = api_client.post(reverse("v1:auth-refresh"), {"refresh": refresh}, format="json")
    assert again.status_code == 401


def test_logout_requires_refresh_field(auth_client):
    res = auth_client.post(reverse("v1:auth-logout"), {}, format="json")
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------


def test_change_password_updates_credentials(auth_client, user, password):
    new = "EvenB3tterPwd!42"
    res = auth_client.post(
        reverse("v1:auth-change-password"),
        {"old_password": password, "new_password": new},
        format="json",
    )
    assert res.status_code == 204
    user.refresh_from_db()
    assert user.check_password(new)


def test_change_password_rejects_wrong_old(auth_client):
    res = auth_client.post(
        reverse("v1:auth-change-password"),
        {"old_password": "nope", "new_password": "EvenB3tterPwd!42"},
        format="json",
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# /users/me/
# ---------------------------------------------------------------------------


def test_users_me_returns_self(auth_client, user):
    res = auth_client.get(reverse("v1:user-me"))
    assert res.status_code == 200
    assert res.data["email"] == user.email


def test_users_me_patch_updates_writable_fields(auth_client):
    res = auth_client.patch(
        reverse("v1:user-me"), {"first_name": "Ada"}, format="json"
    )
    assert res.status_code == 200
    assert res.data["first_name"] == "Ada"


def test_users_me_rejects_anonymous(api_client):
    assert api_client.get(reverse("v1:user-me")).status_code == 401
