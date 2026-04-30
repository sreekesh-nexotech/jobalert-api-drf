"""App meta, filter prefs, reports, activity logs, files, subscriptions, signals.

Smoke tests for everything the listings/engagement/auth files don't cover.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AppMetaData,
    FileManagement,
    FiltersMetaData,
    ListingReport,
    SubscriptionHistory,
    UserActivityLog,
    UserDetails,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# App meta
# ---------------------------------------------------------------------------


def test_app_meta_is_publicly_readable(api_client, admin_user):
    AppMetaData.objects.create(
        key="welcome",
        meta_type="announcement",
        title="Welcome",
        message="Hi",
        created_by=admin_user,
    )
    res = api_client.get(reverse("v1:app-meta-list"))
    assert res.status_code == 200
    assert res.data["count"] == 1


def test_app_meta_write_requires_admin(auth_client):
    res = auth_client.post(
        reverse("v1:app-meta-list"),
        {
            "key": "promo",
            "meta_type": "promotional",
            "title": "Promo",
            "message": "Hello",
        },
        format="json",
    )
    assert res.status_code == 403


def test_admin_can_create_app_meta(admin_client):
    res = admin_client.post(
        reverse("v1:app-meta-list"),
        {
            "key": "promo",
            "meta_type": "promotional",
            "title": "Promo",
            "message": "Hello",
        },
        format="json",
    )
    assert res.status_code == 201, res.content


# ---------------------------------------------------------------------------
# Filter prefs (per-user, upserted)
# ---------------------------------------------------------------------------


def test_filter_prefs_upsert_on_create(auth_client, user):
    payload = {
        "filter_context": "job",
        "selected_categories": ["Tech"],
        "sort_preference": "most_recent",
    }
    a = auth_client.post(reverse("v1:filter-pref-list"), payload, format="json")
    assert a.status_code == 201

    # Posting the same context should upsert, not duplicate.
    payload["selected_categories"] = ["Design"]
    b = auth_client.post(reverse("v1:filter-pref-list"), payload, format="json")
    assert b.status_code == 201
    assert FiltersMetaData.objects.filter(user=user, filter_context="job").count() == 1


def test_filter_prefs_returns_only_own(auth_client, user, other_user):
    FiltersMetaData.objects.create(user=user, filter_context="job")
    FiltersMetaData.objects.create(user=other_user, filter_context="biz")
    res = auth_client.get(reverse("v1:filter-pref-list"))
    assert res.data["count"] == 1


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def test_user_can_report_listing(auth_client, user, job_listing):
    res = auth_client.post(
        reverse("v1:report-list"),
        {
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "reason": "spam",
        },
        format="json",
    )
    assert res.status_code == 201
    assert ListingReport.objects.filter(user=user, job_listing=job_listing).exists()


def test_user_cannot_review_report(auth_client, user, job_listing):
    report = ListingReport.objects.create(
        user=user, listing_type="job", job_listing=job_listing, reason="spam"
    )
    res = auth_client.post(
        reverse("v1:report-review", args=[report.id]),
        {"status": "resolved"},
        format="json",
    )
    assert res.status_code == 403


def test_admin_can_review_report(admin_client, admin_user, user, job_listing):
    report = ListingReport.objects.create(
        user=user, listing_type="job", job_listing=job_listing, reason="spam"
    )
    res = admin_client.post(
        reverse("v1:report-review", args=[report.id]),
        {"status": "resolved", "reviewer_notes": "ok"},
        format="json",
    )
    assert res.status_code == 200
    report.refresh_from_db()
    assert report.status == "resolved"
    assert report.reviewer_id == admin_user.id


# ---------------------------------------------------------------------------
# Activity logs
# ---------------------------------------------------------------------------


def test_user_can_create_activity_log(auth_client, user, job_listing):
    res = auth_client.post(
        reverse("v1:activity-log-list"),
        {
            "action_type": "view_listing",
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "device_type": "android",
            "metadata": {"foo": "bar"},
        },
        format="json",
    )
    assert res.status_code == 201
    assert UserActivityLog.objects.filter(user=user, action_type="view_listing").exists()


def test_user_cannot_list_activity_logs(auth_client, user):
    UserActivityLog.objects.create(user=user, action_type="login")
    res = auth_client.get(reverse("v1:activity-log-list"))
    assert res.status_code == 403


def test_admin_can_list_activity_logs(admin_client, user):
    UserActivityLog.objects.create(user=user, action_type="login")
    res = admin_client.get(reverse("v1:activity-log-list"))
    assert res.status_code == 200
    assert res.data["count"] >= 1


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def test_user_can_upload_file_metadata_for_self(auth_client, user):
    res = auth_client.post(
        reverse("v1:file-list"),
        {
            "file_name": "resume.pdf",
            "file_url": "https://cdn.example.com/x.pdf",
            "file_type": "pdf",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    assert FileManagement.objects.filter(uploaded_by=user).exists()


def test_user_only_sees_own_files(auth_client, user, other_user):
    FileManagement.objects.create(
        user=user, uploaded_by=user, file_name="a", file_url="https://x"
    )
    FileManagement.objects.create(
        user=other_user, uploaded_by=other_user, file_name="b", file_url="https://x"
    )
    res = auth_client.get(reverse("v1:file-list"))
    assert res.data["count"] == 1


# ---------------------------------------------------------------------------
# Subscriptions + premium signal
# ---------------------------------------------------------------------------


def test_subscription_success_marks_user_premium(user):
    sub = SubscriptionHistory.objects.create(
        user=user,
        plan_type="premium_monthly",
        amount=99,
        payment_status="initiated",
    )
    UserDetails.objects.filter(user=user).update(is_premium=False)

    sub.payment_status = "success"
    sub.save()

    details = UserDetails.objects.get(user=user)
    assert details.is_premium is True
    assert details.premium_expires_at is not None
    assert details.premium_expires_at > timezone.now()


def test_subscription_initiated_does_not_grant_premium(user):
    SubscriptionHistory.objects.create(
        user=user, plan_type="premium_monthly", amount=99, payment_status="initiated"
    )
    details = UserDetails.objects.get(user=user)
    assert details.is_premium is False


# ---------------------------------------------------------------------------
# Default admin from migration
# ---------------------------------------------------------------------------


def test_default_admin_was_created_by_migration():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    assert User.objects.filter(
        email="admin@jobalert.local", is_staff=True, is_superuser=True
    ).exists()
