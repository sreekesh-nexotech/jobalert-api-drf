"""Listings: CRUD, ownership rules, moderation, visibility, engagement actions."""
from __future__ import annotations

import pytest
from django.urls import reverse

from core.models import (
    BizListing,
    JobListing,
    ListingStatus,
    PointsHistory,
    SavedAndAppliedListing,
    Upvote,
    UserDetails,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def test_anonymous_cannot_list_jobs(api_client):
    assert api_client.get(reverse("v1:job-listing-list")).status_code == 401


def test_user_sees_approved_listings_and_own_pending(
    auth_client, user, other_user, make_job_listing
):
    # Approved by someone else (visible)
    approved = make_job_listing(posted_by=other_user, status=ListingStatus.APPROVED)
    # Pending by someone else (hidden)
    make_job_listing(posted_by=other_user, status=ListingStatus.PENDING)
    # Own pending (visible)
    own_pending = make_job_listing(posted_by=user, status=ListingStatus.PENDING)

    res = auth_client.get(reverse("v1:job-listing-list"))
    assert res.status_code == 200
    uids = {item["uid"] for item in res.data["results"]}
    assert str(approved.uid) in uids
    assert str(own_pending.uid) in uids
    assert len(uids) == 2


def test_admin_sees_all_listings(admin_client, make_job_listing, user):
    make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    make_job_listing(posted_by=user, status=ListingStatus.APPROVED)
    make_job_listing(posted_by=user, status=ListingStatus.REJECTED)
    res = admin_client.get(reverse("v1:job-listing-list"))
    assert res.status_code == 200
    assert res.data["count"] == 3


# ---------------------------------------------------------------------------
# Create / update / delete
# ---------------------------------------------------------------------------


def test_user_can_create_job_listing_in_pending_state(auth_client, user):
    res = auth_client.post(
        reverse("v1:job-listing-list"),
        {
            "title": "Frontend dev",
            "category": "Tech",
            "description": "Some desc",
            "location": "Remote",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    assert res.data["status"] == ListingStatus.PENDING
    assert res.data["posted_by"]["uid"] == str(user.uid)


def test_user_can_edit_own_pending_listing(auth_client, user, make_job_listing):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    res = auth_client.patch(
        reverse("v1:job-listing-detail", args=[listing.uid]),
        {"title": "Updated"},
        format="json",
    )
    assert res.status_code == 200
    listing.refresh_from_db()
    assert listing.title == "Updated"


def test_user_cannot_edit_after_approval(auth_client, user, make_job_listing):
    listing = make_job_listing(posted_by=user, status=ListingStatus.APPROVED)
    res = auth_client.patch(
        reverse("v1:job-listing-detail", args=[listing.uid]),
        {"title": "Hacked"},
        format="json",
    )
    assert res.status_code == 403


def test_user_cannot_edit_others_listing(auth_client, other_user, make_job_listing):
    listing = make_job_listing(posted_by=other_user, status=ListingStatus.PENDING)
    res = auth_client.patch(
        reverse("v1:job-listing-detail", args=[listing.uid]),
        {"title": "Hacked"},
        format="json",
    )
    # Either 403 (object permission) or 404 (filtered out from queryset).
    assert res.status_code in (403, 404)


def test_admin_can_edit_any_listing(admin_client, user, make_job_listing):
    listing = make_job_listing(posted_by=user, status=ListingStatus.APPROVED)
    res = admin_client.patch(
        reverse("v1:job-listing-detail", args=[listing.uid]),
        {"title": "Curated"},
        format="json",
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------


def test_admin_can_approve_listing_and_award_points(
    admin_client, admin_user, user, make_job_listing
):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    res = admin_client.post(
        reverse("v1:job-listing-approve", args=[listing.uid]), {}, format="json"
    )
    assert res.status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.APPROVED
    assert listing.approved_by_id == admin_user.id
    assert listing.approved_at is not None
    assert PointsHistory.objects.filter(
        user=user, reason=PointsHistory.EarnReason.LISTING_APPROVED
    ).exists()
    details = UserDetails.objects.get(user=user)
    assert details.total_points >= 50


def test_user_cannot_approve_listing(auth_client, user, make_job_listing):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    res = auth_client.post(
        reverse("v1:job-listing-approve", args=[listing.uid]), {}, format="json"
    )
    assert res.status_code == 403


def test_admin_can_reject_listing(admin_client, user, make_job_listing):
    listing = make_job_listing(posted_by=user, status=ListingStatus.PENDING)
    res = admin_client.post(
        reverse("v1:job-listing-reject", args=[listing.uid]), {}, format="json"
    )
    assert res.status_code == 200
    listing.refresh_from_db()
    assert listing.status == ListingStatus.REJECTED


# ---------------------------------------------------------------------------
# Engagement actions
# ---------------------------------------------------------------------------


def test_upvote_action_increments_counter(auth_client, user, job_listing):
    res = auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    assert res.status_code == 201
    job_listing.refresh_from_db()
    assert job_listing.upvotes_count == 1
    assert Upvote.objects.filter(user=user, job_listing=job_listing).exists()


def test_upvote_is_idempotent(auth_client, job_listing):
    auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    res = auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    # Second hit returns 200 (already created).
    assert res.status_code == 200
    job_listing.refresh_from_db()
    assert job_listing.upvotes_count == 1


def test_upvote_delete_decrements_counter(auth_client, job_listing):
    auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    res = auth_client.delete(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    assert res.status_code == 204
    job_listing.refresh_from_db()
    assert job_listing.upvotes_count == 0


def test_save_action_increments_counter(auth_client, user, job_listing):
    res = auth_client.post(reverse("v1:job-listing-save", args=[job_listing.uid]))
    assert res.status_code == 200
    job_listing.refresh_from_db()
    assert job_listing.saves_count == 1


def test_save_then_unsave(auth_client, job_listing):
    auth_client.post(reverse("v1:job-listing-save", args=[job_listing.uid]))
    res = auth_client.delete(reverse("v1:job-listing-save", args=[job_listing.uid]))
    assert res.status_code == 204
    job_listing.refresh_from_db()
    assert job_listing.saves_count == 0


def test_apply_action_records_application(auth_client, user, job_listing):
    res = auth_client.post(reverse("v1:job-listing-apply", args=[job_listing.uid]))
    assert res.status_code == 200
    record = SavedAndAppliedListing.objects.get(user=user, job_listing=job_listing)
    assert record.is_applied is True
    assert record.applied_at is not None


def test_view_action_increments_views(auth_client, job_listing):
    res = auth_client.post(reverse("v1:job-listing-view", args=[job_listing.uid]))
    assert res.status_code == 200
    assert res.data["views_count"] == 1


# ---------------------------------------------------------------------------
# Filtering / ordering / search
# ---------------------------------------------------------------------------


def test_filter_by_category(auth_client, user, make_job_listing):
    make_job_listing(posted_by=user, category="Tech")
    make_job_listing(posted_by=user, category="Design")
    res = auth_client.get(reverse("v1:job-listing-list"), {"category": "Tech"})
    assert res.status_code == 200
    assert res.data["count"] == 1
    assert res.data["results"][0]["category"] == "Tech"


def test_search_term_matches_title(auth_client, user, make_job_listing):
    make_job_listing(posted_by=user, title="Backend Engineer")
    make_job_listing(posted_by=user, title="UX Designer")
    res = auth_client.get(reverse("v1:job-listing-list"), {"search": "backend"})
    assert res.data["count"] == 1


def test_ordering_by_upvotes(auth_client, user, make_job_listing):
    a = make_job_listing(posted_by=user, title="A", upvotes_count=10)
    b = make_job_listing(posted_by=user, title="B", upvotes_count=5)
    res = auth_client.get(reverse("v1:job-listing-list"), {"ordering": "-upvotes_count"})
    assert [r["uid"] for r in res.data["results"]][:2] == [str(a.uid), str(b.uid)]


# ---------------------------------------------------------------------------
# Biz listings — sanity check (mirrors Job behaviour)
# ---------------------------------------------------------------------------


def test_biz_listing_create(auth_client):
    res = auth_client.post(
        reverse("v1:biz-listing-list"),
        {
            "title": "Cafe Franchise",
            "category": "Food",
            "description": "Great brand",
            "opportunity_type": "franchise",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["status"] == ListingStatus.PENDING
    assert res.data["opportunity_type"] == "franchise"


def test_biz_listing_upvote_and_save(auth_client, biz_listing):
    auth_client.post(reverse("v1:biz-listing-upvote", args=[biz_listing.uid]))
    biz_listing.refresh_from_db()
    assert biz_listing.upvotes_count == 1

    auth_client.post(reverse("v1:biz-listing-save", args=[biz_listing.uid]))
    biz_listing.refresh_from_db()
    assert biz_listing.saves_count == 1
