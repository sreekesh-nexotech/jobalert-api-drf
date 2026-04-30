"""Shared pytest fixtures for the JobAlert API test suite."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import BizListing, JobListing, ListingStatus, UserDetails

User = get_user_model()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@pytest.fixture
def password() -> str:
    return "Sup3rSecret!42"


@pytest.fixture
def make_user(db, password):
    """Factory for creating users. Auto-attaches a UserDetails row."""

    counter = {"n": 0}

    def _make(
        *,
        email=None,
        username=None,
        is_staff=False,
        is_superuser=False,
        country_code="",
        mobile_number="",
        **extra,
    ):
        counter["n"] += 1
        n = counter["n"]
        user = User.objects.create_user(
            email=email or f"user{n}@example.com",
            username=username or f"user{n}",
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser,
            country_code=country_code,
            mobile_number=mobile_number,
            **extra,
        )
        UserDetails.objects.get_or_create(user=user)
        return user

    return _make


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def other_user(make_user):
    return make_user()


@pytest.fixture
def admin_user(make_user):
    return make_user(
        email="admin-test@jobalert.local",
        username="admin-test",
        is_staff=True,
        is_superuser=True,
    )


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


@pytest.fixture
def make_job_listing(db, user):
    def _make(*, posted_by=None, status=ListingStatus.APPROVED, **extra):
        defaults = {
            "title": "Backend Engineer",
            "category": "Tech",
            "description": "Join us.",
            "location": "Remote",
            "status": status,
        }
        defaults.update(extra)
        return JobListing.objects.create(
            posted_by=posted_by or user, **defaults
        )

    return _make


@pytest.fixture
def make_biz_listing(db, user):
    def _make(*, posted_by=None, status=ListingStatus.APPROVED, **extra):
        defaults = {
            "title": "Cafe Franchise",
            "category": "Food",
            "description": "Great chain.",
            "opportunity_type": "franchise",
            "status": status,
        }
        defaults.update(extra)
        return BizListing.objects.create(
            posted_by=posted_by or user, **defaults
        )

    return _make


@pytest.fixture
def job_listing(make_job_listing):
    return make_job_listing()


@pytest.fixture
def biz_listing(make_biz_listing):
    return make_biz_listing()
