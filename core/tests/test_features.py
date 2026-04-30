"""Comment likes, can-submit-listing, notifications, home feed, static pages."""
from __future__ import annotations

import pytest
from django.urls import reverse

from core.models import (
    Comment,
    CommentLike,
    ListingStatus,
    Notification,
    StaticPage,
    UserDetails,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Comment likes
# ---------------------------------------------------------------------------


def test_like_comment_creates_row_and_bumps_count(auth_client, user, job_listing):
    comment = Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="hi"
    )
    res = auth_client.post(reverse("v1:comment-like-toggle", args=[comment.uid]))
    assert res.status_code == 201
    assert res.data["liked"] is True
    assert res.data["likes_count"] == 1
    assert CommentLike.objects.filter(user=user, comment=comment).exists()


def test_like_comment_is_idempotent(auth_client, user, job_listing):
    comment = Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="hi"
    )
    auth_client.post(reverse("v1:comment-like-toggle", args=[comment.uid]))
    res = auth_client.post(reverse("v1:comment-like-toggle", args=[comment.uid]))
    assert res.status_code == 200  # already liked
    assert res.data["likes_count"] == 1


def test_unlike_comment_removes_row(auth_client, user, job_listing):
    comment = Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="hi"
    )
    auth_client.post(reverse("v1:comment-like-toggle", args=[comment.uid]))
    res = auth_client.delete(reverse("v1:comment-like-toggle", args=[comment.uid]))
    assert res.status_code == 204
    assert res.data["likes_count"] == 0


# ---------------------------------------------------------------------------
# Can-submit-listing gate
# ---------------------------------------------------------------------------


def test_can_submit_when_no_pending_listings(auth_client):
    res = auth_client.get(reverse("v1:listing-can-submit"))
    assert res.status_code == 200
    assert res.data["can_submit"] is True
    assert res.data["pending_listing_uid"] is None


def test_cannot_submit_when_pending_job_exists(auth_client, user, make_job_listing):
    pending = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    res = auth_client.get(reverse("v1:listing-can-submit"))
    assert res.status_code == 200
    assert res.data["can_submit"] is False
    assert res.data["pending_listing_type"] == "job"
    assert str(res.data["pending_listing_uid"]) == str(pending.uid)


def test_can_submit_when_only_approved_listings(auth_client, user, make_job_listing):
    make_job_listing(posted_by=user, status=ListingStatus.APPROVED)
    res = auth_client.get(reverse("v1:listing-can-submit"))
    assert res.data["can_submit"] is True


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def test_listing_approval_creates_notification(
    admin_client, admin_user, user, make_job_listing
):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    admin_client.post(reverse("v1:job-listing-approve", args=[listing.uid]))
    notif = Notification.objects.filter(
        user=user,
        notification_type=Notification.NotificationType.LISTING_APPROVED,
    ).first()
    assert notif is not None
    assert notif.related_job_listing_id == listing.id


def test_listing_rejection_creates_notification(
    admin_client, user, make_job_listing
):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    admin_client.post(reverse("v1:job-listing-reject", args=[listing.uid]))
    assert Notification.objects.filter(
        user=user,
        notification_type=Notification.NotificationType.LISTING_REJECTED,
    ).exists()


def test_comment_reply_pings_parent_author(
    auth_client, user, other_user, job_listing
):
    parent = Comment.objects.create(
        user=other_user, listing_type="job", job_listing=job_listing, text="parent"
    )
    auth_client.post(
        reverse("v1:comment-list"),
        {
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "parent_comment_uid": str(parent.uid),
            "text": "reply",
        },
        format="json",
    )
    assert Notification.objects.filter(
        user=other_user,
        notification_type=Notification.NotificationType.COMMENT_REPLY,
    ).exists()


def test_notifications_endpoint_returns_only_own(auth_client, user, other_user):
    Notification.objects.create(
        user=user, notification_type="announcement",
        title="A", message="for me",
    )
    Notification.objects.create(
        user=other_user, notification_type="announcement",
        title="B", message="not for me",
    )
    res = auth_client.get(reverse("v1:notification-list"))
    assert res.data["count"] == 1


def test_unread_count_endpoint(auth_client, user):
    Notification.objects.create(
        user=user, notification_type="announcement", title="X", message="x"
    )
    Notification.objects.create(
        user=user, notification_type="announcement",
        title="Y", message="y", is_read=True,
    )
    res = auth_client.get(reverse("v1:notification-unread-count"))
    assert res.data["unread"] == 1


def test_mark_notification_read(auth_client, user):
    n = Notification.objects.create(
        user=user, notification_type="announcement", title="X", message="x"
    )
    res = auth_client.post(reverse("v1:notification-mark-read", args=[n.uid]))
    assert res.status_code == 200
    n.refresh_from_db()
    assert n.is_read is True


def test_mark_all_read(auth_client, user):
    Notification.objects.create(
        user=user, notification_type="announcement", title="X", message="x"
    )
    Notification.objects.create(
        user=user, notification_type="announcement", title="Y", message="y"
    )
    auth_client.post(reverse("v1:notification-mark-all-read"))
    assert Notification.objects.filter(user=user, is_read=False).count() == 0


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------


def test_static_pages_are_publicly_readable(api_client, admin_user):
    StaticPage.objects.create(
        slug="privacy_policy", title="Privacy", body="…", updated_by=admin_user
    )
    res = api_client.get(reverse("v1:static-page-list"))
    assert res.status_code == 200
    assert res.data["count"] == 1


def test_static_page_lookup_by_slug(api_client, admin_user):
    StaticPage.objects.create(
        slug="terms_of_service", title="ToS", body="legal", updated_by=admin_user
    )
    res = api_client.get(
        reverse("v1:static-page-detail", args=["terms_of_service"])
    )
    assert res.status_code == 200
    assert res.data["title"] == "ToS"


def test_static_page_admin_only_write(user, admin_user):
    """Use independent clients — auth_client/admin_client share api_client,
    which causes the second force_authenticate call to clobber the first."""
    from rest_framework.test import APIClient

    user_client = APIClient()
    user_client.force_authenticate(user=user)
    admin = APIClient()
    admin.force_authenticate(user=admin_user)

    res = user_client.post(
        reverse("v1:static-page-list"),
        {"slug": "help", "title": "Help", "body": "…"},
        format="json",
    )
    assert res.status_code == 403

    res2 = admin.post(
        reverse("v1:static-page-list"),
        {"slug": "help", "title": "Help", "body": "…"},
        format="json",
    )
    assert res2.status_code == 201
    assert res2.data["version"] == 1


def test_static_page_version_bumps_on_update(admin_client, admin_user):
    page = StaticPage.objects.create(
        slug="about", title="About v1", body="b", updated_by=admin_user
    )
    res = admin_client.patch(
        reverse("v1:static-page-detail", args=["about"]),
        {"title": "About v2"},
        format="json",
    )
    assert res.status_code == 200
    page.refresh_from_db()
    assert page.version == 2
    assert page.title == "About v2"


def test_unpublished_static_page_hidden_from_public(api_client, admin_user):
    StaticPage.objects.create(
        slug="about", title="Draft", body="b",
        is_published=False, updated_by=admin_user,
    )
    res = api_client.get(reverse("v1:static-page-list"))
    assert res.data["count"] == 0


# ---------------------------------------------------------------------------
# Home feed
# ---------------------------------------------------------------------------


def test_home_feed_returns_aggregate_payload(
    auth_client, user, make_job_listing, make_biz_listing
):
    UserDetails.objects.filter(user=user).update(job_preferences=["Tech"])
    make_job_listing(category="Tech", title="Backend Eng")
    make_job_listing(category="Design", title="UX Designer")
    make_biz_listing()
    res = auth_client.get(reverse("v1:home-feed"))
    assert res.status_code == 200

    body = res.data
    # Tech-pref user sees only Tech jobs in suggestions.
    titles = [j["title"] for j in body["suggested_jobs"]]
    assert "Backend Eng" in titles
    assert "UX Designer" not in titles

    assert body["new_jobs_count"] >= 1
    assert isinstance(body["trending_biz"], list)
    assert "stats" in body
    assert "unread_notifications" in body


def test_home_feed_requires_auth(api_client):
    res = api_client.get(reverse("v1:home-feed"))
    assert res.status_code == 401
