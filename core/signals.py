"""Signal handlers for denormalised counters, points ledger, and lifecycle events.

Counters
--------
- Upvote create/delete -> Job/Biz listing.upvotes_count
- Comment create/soft-delete -> listing.comments_count
- SavedAndAppliedListing.is_saved transitions -> listing.saves_count
- Upvote / SavedAndApplied / Comment per-user -> UserDetails counters

Points
------
- Listing approved (status PENDING -> APPROVED) -> +50 points (LISTING_APPROVED)
- Comment posted -> +2 points (COMMENT_POSTED)
- Each PointsHistory insert keeps UserDetails.total_points and points_level
  in sync. ``balance_after`` is computed from the previous balance, so the
  ledger is internally consistent.

Premium
-------
- SubscriptionHistory.payment_status -> SUCCESS sets UserDetails.is_premium
  and premium_expires_at based on plan_type.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from core.models import (
    BizListing,
    Comment,
    JobListing,
    ListingStatus,
    PointsHistory,
    SavedAndAppliedListing,
    SubscriptionHistory,
    Upvote,
    UserDetails,
)

POINTS_FOR_LISTING_APPROVED = 50
POINTS_FOR_COMMENT_POSTED = 2

LEVEL_THRESHOLDS = [
    (1000, UserDetails.PointsLevel.LEGEND),
    (500, UserDetails.PointsLevel.CHAMPION),
    (100, UserDetails.PointsLevel.CONTRIBUTOR),
    (0, UserDetails.PointsLevel.NEWCOMER),
]


def _level_for(points: int) -> str:
    for threshold, level in LEVEL_THRESHOLDS:
        if points >= threshold:
            return level
    return UserDetails.PointsLevel.NEWCOMER


def _adjust_listing_counter(instance, *, field: str, delta: int):
    """Atomically bump a denormalised counter on the parent listing."""
    if instance.job_listing_id:
        JobListing.objects.filter(pk=instance.job_listing_id).update(
            **{field: F(field) + delta}
        )
    elif instance.biz_listing_id:
        BizListing.objects.filter(pk=instance.biz_listing_id).update(
            **{field: F(field) + delta}
        )


def _award_points(user, *, points: int, reason: str, listing=None, notes: str = ""):
    """Append a row to PointsHistory and refresh denormalised totals."""
    if user is None:
        return
    details, _ = UserDetails.objects.get_or_create(user=user)
    new_total = max(details.total_points + points, 0)
    PointsHistory.objects.create(
        user=user,
        transaction_type=(
            PointsHistory.TransactionType.EARNED
            if points >= 0
            else PointsHistory.TransactionType.REDEEMED
        ),
        reason=reason,
        points=points,
        balance_after=new_total,
        job_listing=listing if isinstance(listing, JobListing) else None,
        biz_listing=listing if isinstance(listing, BizListing) else None,
        notes=notes,
    )
    UserDetails.objects.filter(pk=details.pk).update(
        total_points=new_total, points_level=_level_for(new_total)
    )


# ---------------------------------------------------------------------------
# Upvotes
# ---------------------------------------------------------------------------


@receiver(post_save, sender=Upvote)
def upvote_created(sender, instance, created, **kwargs):
    if not created:
        return
    _adjust_listing_counter(instance, field="upvotes_count", delta=1)
    UserDetails.objects.filter(user=instance.user).update(
        total_upvotes_given=F("total_upvotes_given") + 1
    )


@receiver(post_delete, sender=Upvote)
def upvote_deleted(sender, instance, **kwargs):
    _adjust_listing_counter(instance, field="upvotes_count", delta=-1)
    UserDetails.objects.filter(user=instance.user).update(
        total_upvotes_given=F("total_upvotes_given") - 1
    )


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Comment)
def comment_pre_save(sender, instance, **kwargs):
    """Track the prior is_deleted state so post_save can detect transitions."""
    if instance.pk is None:
        instance._was_deleted = None
        return
    try:
        instance._was_deleted = sender.objects.values_list(
            "is_deleted", flat=True
        ).get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._was_deleted = None


@receiver(post_save, sender=Comment)
def comment_post_save(sender, instance, created, **kwargs):
    if created and not instance.is_deleted:
        _adjust_listing_counter(instance, field="comments_count", delta=1)
        if instance.user_id:
            _award_points(
                instance.user,
                points=POINTS_FOR_COMMENT_POSTED,
                reason=PointsHistory.EarnReason.COMMENT_POSTED,
                notes=f"Comment {instance.uid}",
            )
        return

    was_deleted = getattr(instance, "_was_deleted", None)
    if was_deleted is False and instance.is_deleted:
        _adjust_listing_counter(instance, field="comments_count", delta=-1)
    elif was_deleted is True and not instance.is_deleted:
        _adjust_listing_counter(instance, field="comments_count", delta=1)


@receiver(post_delete, sender=Comment)
def comment_deleted(sender, instance, **kwargs):
    if not instance.is_deleted:
        _adjust_listing_counter(instance, field="comments_count", delta=-1)


# ---------------------------------------------------------------------------
# Saved listings (toggle is_saved)
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=SavedAndAppliedListing)
def saved_pre_save(sender, instance, **kwargs):
    if instance.pk is None:
        instance._was_saved = False
        return
    try:
        instance._was_saved = sender.objects.values_list(
            "is_saved", flat=True
        ).get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._was_saved = False


@receiver(post_save, sender=SavedAndAppliedListing)
def saved_post_save(sender, instance, created, **kwargs):
    was_saved = getattr(instance, "_was_saved", False)
    delta = 0
    if instance.is_saved and not was_saved:
        delta = 1
    elif not instance.is_saved and was_saved:
        delta = -1
    if delta:
        _adjust_listing_counter(instance, field="saves_count", delta=delta)
        UserDetails.objects.filter(user=instance.user).update(
            total_saved=F("total_saved") + delta
        )


@receiver(post_delete, sender=SavedAndAppliedListing)
def saved_deleted(sender, instance, **kwargs):
    if instance.is_saved:
        _adjust_listing_counter(instance, field="saves_count", delta=-1)
        UserDetails.objects.filter(user=instance.user).update(
            total_saved=F("total_saved") - 1
        )


# ---------------------------------------------------------------------------
# Listings: posts counter + approval points
# ---------------------------------------------------------------------------


def _attach_listing_signals(model):
    @receiver(post_save, sender=model, weak=False)
    def listing_created(sender, instance, created, **kwargs):
        if created and instance.posted_by_id:
            UserDetails.objects.filter(user_id=instance.posted_by_id).update(
                total_posts=F("total_posts") + 1
            )

    @receiver(pre_save, sender=model, weak=False)
    def listing_pre_save(sender, instance, **kwargs):
        if instance.pk is None:
            instance._old_status = None
            return
        try:
            instance._old_status = sender.objects.values_list(
                "status", flat=True
            ).get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._old_status = None

    @receiver(post_save, sender=model, weak=False)
    def listing_status_changed(sender, instance, created, **kwargs):
        if created:
            return
        old = getattr(instance, "_old_status", None)
        if old != ListingStatus.APPROVED and instance.status == ListingStatus.APPROVED:
            _award_points(
                instance.posted_by,
                points=POINTS_FOR_LISTING_APPROVED,
                reason=PointsHistory.EarnReason.LISTING_APPROVED,
                listing=instance,
                notes=f"{model.__name__} approved: {instance.title}",
            )


_attach_listing_signals(JobListing)
_attach_listing_signals(BizListing)


# ---------------------------------------------------------------------------
# Subscriptions -> premium flag
# ---------------------------------------------------------------------------


@receiver(post_save, sender=SubscriptionHistory)
def subscription_post_save(sender, instance, created, **kwargs):
    if instance.payment_status != SubscriptionHistory.PaymentStatus.SUCCESS:
        return
    duration = timedelta(days=30)
    if instance.plan_type == SubscriptionHistory.PlanType.PREMIUM_YEARLY:
        duration = timedelta(days=365)
    expires = (instance.subscription_end or timezone.now()) + duration
    if instance.subscription_end:
        # Already explicitly set; respect it.
        expires = instance.subscription_end
    UserDetails.objects.filter(user=instance.user).update(
        is_premium=True, premium_expires_at=expires
    )
    if not instance.subscription_start or not instance.subscription_end:
        with transaction.atomic():
            SubscriptionHistory.objects.filter(pk=instance.pk).update(
                subscription_start=instance.subscription_start or timezone.now(),
                subscription_end=instance.subscription_end or expires,
            )
