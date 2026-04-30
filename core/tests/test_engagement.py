"""Comments, saved/applied lists, upvote list endpoint, points history."""
from __future__ import annotations

import pytest
from django.urls import reverse

from core.models import Comment, PointsHistory, UserDetails

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_user_can_post_comment_on_listing(auth_client, user, job_listing):
    res = auth_client.post(
        reverse("v1:comment-list"),
        {
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "text": "Looks good!",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    job_listing.refresh_from_db()
    assert job_listing.comments_count == 1


def test_comment_post_awards_points(auth_client, user, job_listing):
    auth_client.post(
        reverse("v1:comment-list"),
        {
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "text": "Looks good!",
        },
        format="json",
    )
    assert PointsHistory.objects.filter(
        user=user, reason=PointsHistory.EarnReason.COMMENT_POSTED
    ).exists()


def test_comment_reply_threading(auth_client, user, job_listing):
    parent = Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="parent"
    )
    res = auth_client.post(
        reverse("v1:comment-list"),
        {
            "listing_type": "job",
            "target_listing_uid": str(job_listing.uid),
            "parent_comment_uid": str(parent.uid),
            "text": "reply",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["parent_comment"] == str(parent.uid)


def test_user_cannot_edit_other_users_comment(
    auth_client, other_user, job_listing
):
    comment = Comment.objects.create(
        user=other_user, listing_type="job", job_listing=job_listing, text="hi"
    )
    res = auth_client.patch(
        reverse("v1:comment-detail", args=[comment.uid]),
        {"text": "hijacked"},
        format="json",
    )
    assert res.status_code == 403


def test_owner_can_soft_delete_comment(auth_client, user, job_listing):
    comment = Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="bye"
    )
    res = auth_client.delete(reverse("v1:comment-detail", args=[comment.uid]))
    assert res.status_code == 204
    comment.refresh_from_db()
    assert comment.is_deleted is True
    job_listing.refresh_from_db()
    assert job_listing.comments_count == 0


def test_comment_filter_by_listing(auth_client, user, job_listing, biz_listing):
    Comment.objects.create(
        user=user, listing_type="job", job_listing=job_listing, text="job"
    )
    Comment.objects.create(
        user=user, listing_type="biz", biz_listing=biz_listing, text="biz"
    )
    res = auth_client.get(
        reverse("v1:comment-list"), {"job_listing": str(job_listing.uid)}
    )
    assert res.data["count"] == 1


# ---------------------------------------------------------------------------
# Saved / applied / upvote read-only listings
# ---------------------------------------------------------------------------


def test_saved_listings_endpoint_returns_only_own(
    auth_client, user, other_user, job_listing, make_job_listing
):
    auth_client.post(reverse("v1:job-listing-save", args=[job_listing.uid]))
    other_listing = make_job_listing(posted_by=other_user)
    # Have the other user save their own listing — must not appear.
    from core.models import SavedAndAppliedListing

    SavedAndAppliedListing.objects.create(
        user=other_user,
        listing_type="job",
        job_listing=other_listing,
        is_saved=True,
    )

    res = auth_client.get(reverse("v1:saved-listing-list"))
    assert res.status_code == 200
    assert res.data["count"] == 1


def test_applied_listings_filter(auth_client, user, job_listing):
    auth_client.post(reverse("v1:job-listing-apply", args=[job_listing.uid]))
    res = auth_client.get(reverse("v1:saved-listing-list"), {"is_applied": "true"})
    assert res.data["count"] == 1


def test_upvote_list_endpoint(auth_client, user, job_listing):
    auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    res = auth_client.get(reverse("v1:upvote-list"))
    assert res.status_code == 200
    assert res.data["count"] == 1


# ---------------------------------------------------------------------------
# Points history
# ---------------------------------------------------------------------------


def test_points_history_returns_only_own(auth_client, user, other_user):
    PointsHistory.objects.create(
        user=user, transaction_type="earned", reason="bonus", points=10, balance_after=10
    )
    PointsHistory.objects.create(
        user=other_user,
        transaction_type="earned",
        reason="bonus",
        points=20,
        balance_after=20,
    )
    res = auth_client.get(reverse("v1:points-history-list"))
    assert res.data["count"] == 1
    assert res.data["results"][0]["points"] == 10


def test_admin_sees_all_points_history(admin_client, user, other_user):
    PointsHistory.objects.create(
        user=user, transaction_type="earned", reason="bonus", points=10, balance_after=10
    )
    PointsHistory.objects.create(
        user=other_user,
        transaction_type="earned",
        reason="bonus",
        points=20,
        balance_after=20,
    )
    res = admin_client.get(reverse("v1:points-history-list"))
    assert res.data["count"] == 2


# ---------------------------------------------------------------------------
# UserDetails counters maintained by signals
# ---------------------------------------------------------------------------


def test_user_details_counters_update_on_engagement(
    auth_client, user, job_listing
):
    auth_client.post(reverse("v1:job-listing-upvote", args=[job_listing.uid]))
    auth_client.post(reverse("v1:job-listing-save", args=[job_listing.uid]))
    details = UserDetails.objects.get(user=user)
    assert details.total_upvotes_given == 1
    assert details.total_saved == 1
