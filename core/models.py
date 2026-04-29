"""
Job Alert App — Django Database Schema
=======================================
14 tables derived from the UI/UX design.

Conventions
-----------
- Every table has an auto-increment integer `id` as the true PK.
- Content-facing tables add a `uid` UUID surrogate key for safe external
  exposure (URLs, API responses, joins across services) so the internal
  PK is never leaked.
- Timestamps: `created_at` (auto_now_add) and `updated_at` (auto_now)
  on every mutable table.
- Denormalised counters (upvotes_count, comments_count, …) live on the
  listing rows for cheap read queries; the source-of-truth tables
  (Upvote, Comment) are the canonical store.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


# ---------------------------------------------------------------------------
# 1. User
# ---------------------------------------------------------------------------

class User(AbstractUser):
    """
    Primary auth model. Email is the login credential.
    Extends AbstractUser which already provides:
        id, username, first_name, last_name, email,
        password, is_active, is_staff, date_joined, last_login.
    """

    # Surrogate key for external references
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Email login
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]  # kept for createsuperuser compatibility

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email


# ---------------------------------------------------------------------------
# 2. UserDetails
# ---------------------------------------------------------------------------

class UserDetails(models.Model):
    """
    Extended profile data collected during and after signup.
    Always accessed through user.details (one-to-one).
    """

    class Gender(models.TextChoices):
        MALE              = "male",              "Male"
        FEMALE            = "female",            "Female"
        OTHER             = "other",             "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    class AccountStatus(models.TextChoices):
        ACTIVE             = "active",             "Active"
        SUSPENDED          = "suspended",          "Suspended"
        DELETION_REQUESTED = "deletion_requested", "Deletion Requested"
        DEACTIVATED        = "deactivated",        "Deactivated"

    class PointsLevel(models.TextChoices):
        NEWCOMER    = "newcomer",    "Newcomer"     # 0 – 99
        CONTRIBUTOR = "contributor", "Contributor"  # 100 – 499
        CHAMPION    = "champion",    "Champion"     # 500 – 999
        LEGEND      = "legend",      "Legend"       # 1000+

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="details"
    )

    # Collected on signup — Additional Details screen
    date_of_birth = models.DateField(null=True, blank=True)
    gender        = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    state         = models.CharField(max_length=100, blank=True)

    # Set / updated from Profile screen
    city                = models.CharField(max_length=100, blank=True)
    profile_picture_url = models.URLField(max_length=500, blank=True)

    # Personalisation — multi-select category chips from Profile screen
    job_preferences = models.JSONField(default=list, blank=True)
    # e.g. ["Design", "Marketing", "Tech"]

    # Premium status — managed by SubscriptionHistory signals
    is_premium         = models.BooleanField(default=False)
    premium_expires_at = models.DateTimeField(null=True, blank=True)

    # Account lifecycle
    account_status        = models.CharField(
        max_length=25,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
    )
    deletion_requested_at = models.DateTimeField(null=True, blank=True)

    # Denormalised point stats — updated by PointsHistory signals
    total_points = models.PositiveIntegerField(default=0)
    points_level = models.CharField(
        max_length=15, choices=PointsLevel.choices, default=PointsLevel.NEWCOMER
    )

    # Denormalised activity counters shown on Profile stats row
    total_posts        = models.PositiveIntegerField(default=0)
    total_saved        = models.PositiveIntegerField(default=0)
    total_upvotes_given = models.PositiveIntegerField(default=0)

    # OTP verification flag set after email OTP flow completes
    otp_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_details"

    def __str__(self):
        return f"Details — {self.user.email}"


# ---------------------------------------------------------------------------
# Shared choices reused across Job and Biz listing models
# ---------------------------------------------------------------------------

class ListingStatus(models.TextChoices):
    PENDING  = "pending",  "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED  = "expired",  "Expired"


class ListingType(models.TextChoices):
    JOB = "job", "Job"
    BIZ = "biz", "Business"


# ---------------------------------------------------------------------------
# 3. JobListing
# ---------------------------------------------------------------------------

class JobListing(models.Model):
    """
    A job opening. Submitted by any user, approved by admin.
    Holds up to 5 CDN image URLs (thumbnail + 4 extras).
    """

    class ExperienceLevel(models.TextChoices):
        FRESHER        = "fresher",   "Fresher"
        ONE_TO_THREE   = "1-3_yrs",  "1–3 Years"
        THREE_TO_FIVE  = "3-5_yrs",  "3–5 Years"
        FIVE_PLUS      = "5+_yrs",   "5+ Years"

    # Surrogate key
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Ownership
    posted_by   = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="job_listings",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_job_listings",
    )

    # Core identity
    title         = models.CharField(max_length=255)
    category      = models.CharField(max_length=100)
    sub_category  = models.CharField(max_length=100, blank=True)
    qualification = models.CharField(max_length=255, blank=True)
    description   = models.TextField()

    # Job-specific fields
    location         = models.CharField(max_length=200)
    experience_level = models.CharField(
        max_length=10, choices=ExperienceLevel.choices, blank=True
    )
    # Numeric min/max for range queries; display string for rendering
    salary_min     = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max     = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_display = models.CharField(max_length=100, blank=True)  # "₹8L – ₹14L"

    application_deadline = models.DateField(null=True, blank=True)

    # Source attribution (where the listing was originally found)
    source_name = models.CharField(max_length=100, blank=True)  # "LinkedIn", "Naukri"
    source_url  = models.URLField(max_length=500, blank=True)

    # Taxonomy — stored as JSON list, e.g. ["#GraphicDesign", "#FullTime"]
    tags = models.JSONField(default=list, blank=True)

    # Label flags — set by admin after approval
    is_trending  = models.BooleanField(default=False)
    is_new       = models.BooleanField(default=True)
    is_featured  = models.BooleanField(default=False)
    is_verified  = models.BooleanField(default=False)

    # CDN image links: slot 1 = thumbnail, slots 2-5 = gallery
    thumbnail_url = models.URLField(max_length=500, blank=True)
    image_2_url   = models.URLField(max_length=500, blank=True)
    image_3_url   = models.URLField(max_length=500, blank=True)
    image_4_url   = models.URLField(max_length=500, blank=True)
    image_5_url   = models.URLField(max_length=500, blank=True)

    # Lifecycle
    status     = models.CharField(
        max_length=10, choices=ListingStatus.choices, default=ListingStatus.PENDING
    )
    is_expired  = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)

    # Denormalised engagement counters (updated via signals)
    upvotes_count  = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    saves_count    = models.PositiveIntegerField(default=0)
    views_count    = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_listings"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_expired"]),
            models.Index(fields=["category"]),
            models.Index(fields=["location"]),
            models.Index(fields=["upvotes_count"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# 4. BizListing
# ---------------------------------------------------------------------------

class BizListing(models.Model):
    """
    A business opportunity (franchise, investment, channel partner, etc.).
    Mirrors JobListing structure; fields differ for biz-specific data.
    """

    class OpportunityType(models.TextChoices):
        FRANCHISE       = "franchise",       "Franchise"
        INVESTMENT      = "investment",      "Investment"
        CHANNEL_PARTNER = "channel_partner", "Channel Partner"
        JOINT_VENTURE   = "joint_venture",   "Joint Venture"
        OTHER           = "other",           "Other"

    # Surrogate key
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Ownership
    posted_by   = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="biz_listings",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_biz_listings",
    )

    # Core identity
    title        = models.CharField(max_length=255)
    category     = models.CharField(max_length=100)
    sub_category = models.CharField(max_length=100, blank=True)
    description  = models.TextField()

    # Biz-specific fields
    opportunity_type   = models.CharField(max_length=20, choices=OpportunityType.choices)
    venue              = models.CharField(max_length=200, blank=True)  # "Pan India", "Chennai"
    # Numeric range for filtering; display string for rendering
    investment_min     = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    investment_max     = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    investment_display = models.CharField(max_length=100, blank=True)  # "₹25L – ₹80L"
    # Free-text date/deadline displayed on card ("Ongoing", "Closes 20 May 2026")
    date_info    = models.CharField(max_length=100, blank=True)
    closing_date = models.DateField(null=True, blank=True)  # machine-readable counterpart

    # Source attribution
    source_name = models.CharField(max_length=100, blank=True)
    source_url  = models.URLField(max_length=500, blank=True)

    # Taxonomy
    tags = models.JSONField(default=list, blank=True)

    # Label flags
    is_trending = models.BooleanField(default=False)
    is_new      = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    # CDN image links
    thumbnail_url = models.URLField(max_length=500, blank=True)
    image_2_url   = models.URLField(max_length=500, blank=True)
    image_3_url   = models.URLField(max_length=500, blank=True)
    image_4_url   = models.URLField(max_length=500, blank=True)
    image_5_url   = models.URLField(max_length=500, blank=True)

    # Lifecycle
    status     = models.CharField(
        max_length=10, choices=ListingStatus.choices, default=ListingStatus.PENDING
    )
    is_expired  = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)

    # Denormalised engagement counters
    upvotes_count  = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    saves_count    = models.PositiveIntegerField(default=0)
    views_count    = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "biz_listings"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_expired"]),
            models.Index(fields=["category"]),
            models.Index(fields=["opportunity_type"]),
            models.Index(fields=["upvotes_count"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# 5. FileManagement
# ---------------------------------------------------------------------------

class FileManagement(models.Model):
    """
    CDN links for non-image files (PDFs, docs, etc.) attached to a
    job listing, biz listing, or user account (receipts/billing — future).
    Exactly one of job_listing / biz_listing / user must be set.
    """

    class FileType(models.TextChoices):
        PDF   = "pdf",   "PDF"
        DOC   = "doc",   "Word Document"
        XLSX  = "xlsx",  "Excel"
        CSV   = "csv",   "CSV"
        PPT   = "ppt",   "PowerPoint"
        OTHER = "other", "Other"

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Polymorphic owner — only one of these should be non-null per row
    job_listing = models.ForeignKey(
        JobListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="files",
    )
    biz_listing = models.ForeignKey(
        BizListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="files",
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        null=True, blank=True, related_name="files",
    )

    file_name       = models.CharField(max_length=255)
    file_url        = models.URLField(max_length=500)
    file_type       = models.CharField(max_length=10, choices=FileType.choices, default=FileType.OTHER)
    mime_type       = models.CharField(max_length=100, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    description     = models.CharField(max_length=255, blank=True)

    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="uploaded_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "file_management"

    def __str__(self):
        return self.file_name


# ---------------------------------------------------------------------------
# 6. SavedAndAppliedListing
# ---------------------------------------------------------------------------

class SavedAndAppliedListing(models.Model):
    """
    Tracks a user's save and mark-as-applied actions per listing.
    One row per (user, listing) pair — unique constraints enforce this.
    is_applied maps to "Mark as Applied" (jobs) or "Mark as Enquired" (biz).
    """

    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_applied")
    listing_type = models.CharField(max_length=5, choices=ListingType.choices)
    job_listing  = models.ForeignKey(
        JobListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="saved_by_users",
    )
    biz_listing  = models.ForeignKey(
        BizListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="saved_by_users",
    )

    is_saved   = models.BooleanField(default=False)
    is_applied = models.BooleanField(default=False)

    saved_at   = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saved_and_applied_listings"
        # Prevents duplicate rows for the same user+listing
        constraints = [
            models.UniqueConstraint(
                fields=["user", "job_listing"],
                condition=models.Q(job_listing__isnull=False),
                name="unique_user_job_listing",
            ),
            models.UniqueConstraint(
                fields=["user", "biz_listing"],
                condition=models.Q(biz_listing__isnull=False),
                name="unique_user_biz_listing",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_saved"]),
            models.Index(fields=["user", "is_applied"]),
        ]

    def __str__(self):
        return f"{self.user.email} — {self.listing_type}"


# ---------------------------------------------------------------------------
# 7. Upvote
# ---------------------------------------------------------------------------

class Upvote(models.Model):
    """
    One upvote per user per listing (enforced by unique constraints).
    Toggling removes the row; adding creates it.
    After insert/delete, a signal updates the listing's upvotes_count.
    """

    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="upvotes")
    listing_type = models.CharField(max_length=5, choices=ListingType.choices)
    job_listing  = models.ForeignKey(
        JobListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="upvotes",
    )
    biz_listing  = models.ForeignKey(
        BizListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="upvotes",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "upvotes"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "job_listing"],
                condition=models.Q(job_listing__isnull=False),
                name="unique_upvote_job",
            ),
            models.UniqueConstraint(
                fields=["user", "biz_listing"],
                condition=models.Q(biz_listing__isnull=False),
                name="unique_upvote_biz",
            ),
        ]
        indexes = [
            models.Index(fields=["job_listing"]),
            models.Index(fields=["biz_listing"]),
        ]

    def __str__(self):
        return f"{self.user.email} ▲ {self.listing_type}"


# ---------------------------------------------------------------------------
# 8. Comment
# ---------------------------------------------------------------------------

class Comment(models.Model):
    """
    User comments on listings. Supports one level of threading via
    parent_comment (reply-to). Comment likes are not tracked per the
    product decision; only the text content is stored.
    """

    uid          = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user         = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="comments"
    )
    listing_type = models.CharField(max_length=5, choices=ListingType.choices)
    job_listing  = models.ForeignKey(
        JobListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="comments",
    )
    biz_listing  = models.ForeignKey(
        BizListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="comments",
    )

    parent_comment = models.ForeignKey(
        "self", on_delete=models.CASCADE,
        null=True, blank=True, related_name="replies",
    )

    text = models.TextField(max_length=2000)

    # Soft delete — preserves thread structure when a comment is removed
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "comments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["job_listing", "is_deleted"]),
            models.Index(fields=["biz_listing", "is_deleted"]),
            models.Index(fields=["parent_comment"]),
        ]

    def __str__(self):
        return f"{self.user} on {self.listing_type} — {self.text[:40]}"


# ---------------------------------------------------------------------------
# 9. PointsHistory
# ---------------------------------------------------------------------------

class PointsHistory(models.Model):
    """
    Immutable ledger of every point transaction.
    balance_after is a snapshot of the user's total after this transaction —
    allows reconstructing history without summing all rows.
    """

    class TransactionType(models.TextChoices):
        EARNED   = "earned",   "Earned"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED  = "expired",  "Expired"
        ADJUSTED = "adjusted", "Admin Adjusted"

    class EarnReason(models.TextChoices):
        LISTING_APPROVED = "listing_approved", "Listing Approved"
        REFERRAL         = "referral",         "Referral"
        PROFILE_COMPLETE = "profile_complete", "Profile Completed"
        DAILY_LOGIN      = "daily_login",      "Daily Login"
        COMMENT_POSTED   = "comment_posted",   "Comment Posted"
        BONUS            = "bonus",            "Bonus"
        OTHER            = "other",            "Other"

    user             = models.ForeignKey(User, on_delete=models.CASCADE, related_name="points_history")
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    reason           = models.CharField(max_length=20, choices=EarnReason.choices, blank=True)

    # Positive = earned, negative = redeemed/expired
    points        = models.IntegerField()
    balance_after = models.PositiveIntegerField()

    # Optional back-reference to the listing that triggered the points
    job_listing = models.ForeignKey(
        JobListing, on_delete=models.SET_NULL, null=True, blank=True
    )
    biz_listing = models.ForeignKey(
        BizListing, on_delete=models.SET_NULL, null=True, blank=True
    )

    notes = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "points_history"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{self.user.email} {sign}{self.points}pts — {self.reason}"


# ---------------------------------------------------------------------------
# 10. SubscriptionHistory
# ---------------------------------------------------------------------------

class SubscriptionHistory(models.Model):
    """
    Payment and subscription records for premium features (future use).
    One row per payment attempt; gateway_* fields store provider IDs for
    reconciliation with Razorpay / Stripe etc.
    """

    class PlanType(models.TextChoices):
        FREE             = "free",             "Free"
        PREMIUM_MONTHLY  = "premium_monthly",  "Premium Monthly"
        PREMIUM_YEARLY   = "premium_yearly",   "Premium Yearly"

    class PaymentStatus(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        SUCCESS   = "success",   "Success"
        FAILED    = "failed",    "Failed"
        REFUNDED  = "refunded",  "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    uid  = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions")

    plan_type         = models.CharField(max_length=20, choices=PlanType.choices)
    plan_display_name = models.CharField(max_length=100, blank=True)  # "Premium Monthly — ₹99/mo"
    amount            = models.DecimalField(max_digits=10, decimal_places=2)
    currency          = models.CharField(max_length=5, default="INR")

    payment_status    = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.INITIATED
    )
    payment_gateway   = models.CharField(max_length=50, blank=True)   # "Razorpay", "Stripe"
    gateway_order_id  = models.CharField(max_length=255, blank=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    gateway_signature = models.CharField(max_length=500, blank=True)  # webhook verification hash

    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end   = models.DateTimeField(null=True, blank=True)
    is_auto_renew      = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_history"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} — {self.plan_type} ({self.payment_status})"


# ---------------------------------------------------------------------------
# 11. FiltersMetaData
# ---------------------------------------------------------------------------

class FiltersMetaData(models.Model):
    """
    Persisted filter + sort state for a user per listing context (job/biz).
    One row per (user, filter_context) pair — upserted on every filter change.
    Used to restore filter state on app relaunch and to power personalised feeds.
    """

    class FilterContext(models.TextChoices):
        JOB = "job", "Job Listings"
        BIZ = "biz", "Biz Listings"

    class SortPreference(models.TextChoices):
        MOST_RECENT    = "most_recent",    "Most Recent"
        MOST_UPVOTED   = "most_upvoted",   "Most Upvoted"
        SALARY_HIGH    = "salary_high",    "Salary High to Low"
        INVESTMENT_LOW = "investment_low", "Investment Low to High"

    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name="filters")
    filter_context = models.CharField(max_length=5, choices=FilterContext.choices)

    # Multi-value filter state stored as JSON arrays
    selected_categories        = models.JSONField(default=list, blank=True)  # ["Design", "Marketing"]
    selected_locations         = models.JSONField(default=list, blank=True)  # ["Remote", "Bengaluru"]
    selected_experience_levels = models.JSONField(default=list, blank=True)  # ["Fresher", "1-3_yrs"]
    selected_opportunity_types = models.JSONField(default=list, blank=True)  # ["Franchise", "Investment"]

    sort_preference = models.CharField(
        max_length=15, choices=SortPreference.choices, default=SortPreference.MOST_RECENT
    )
    search_query = models.CharField(max_length=255, blank=True)

    # Boolean toggles matching filter chip states
    remote_only   = models.BooleanField(default=False)
    verified_only = models.BooleanField(default=False)
    hide_expired  = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "filters_meta_data"
        unique_together = [("user", "filter_context")]

    def __str__(self):
        return f"{self.user.email} — {self.filter_context} filters"


# ---------------------------------------------------------------------------
# 12. AppMetaData
# ---------------------------------------------------------------------------

class AppMetaData(models.Model):
    """
    Admin-managed app-level config: announcement popups, force-update
    warnings, maintenance banners, home screen banners, etc.
    Keyed by a unique slug so the app can fetch by known key names.
    """

    class MetaType(models.TextChoices):
        ANNOUNCEMENT  = "announcement",  "Announcement Popup"
        UPDATE_WARNING = "update_warning", "Force Update Warning"
        MAINTENANCE   = "maintenance",   "Maintenance Notice"
        PROMOTIONAL   = "promotional",   "Promotional Banner"
        HOME_BANNER   = "home_banner",   "Home Screen Banner"

    class TargetPlatform(models.TextChoices):
        ALL     = "all",     "All Platforms"
        ANDROID = "android", "Android"
        IOS     = "ios",     "iOS"
        WEB     = "web",     "Web"

    key      = models.CharField(max_length=100, unique=True)  # e.g. "summer_promo_2026"
    meta_type = models.CharField(max_length=15, choices=MetaType.choices)

    title   = models.CharField(max_length=255)
    message = models.TextField()

    cta_label = models.CharField(max_length=50, blank=True)
    cta_url   = models.URLField(max_length=500, blank=True)

    target_platform  = models.CharField(
        max_length=10, choices=TargetPlatform.choices, default=TargetPlatform.ALL
    )
    min_app_version  = models.CharField(max_length=20, blank=True)  # "1.2.0" — only show to older builds
    max_app_version  = models.CharField(max_length=20, blank=True)  # upper bound for targeted warnings

    is_active     = models.BooleanField(default=True)
    is_dismissible = models.BooleanField(default=True)
    priority      = models.PositiveSmallIntegerField(default=0)  # higher = shown first

    valid_from  = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    # Freeform JSON for future extension (deep-link params, image URLs, etc.)
    extra_data = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="app_metadata"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_meta_data"
        ordering = ["-priority", "-created_at"]

    def __str__(self):
        return f"{self.key} ({self.meta_type})"


# ---------------------------------------------------------------------------
# 13. UserActivityLog
# ---------------------------------------------------------------------------

class UserActivityLog(models.Model):
    """
    Append-only audit log of user actions. Never updated after insert.
    Used for analytics, abuse detection, and personalisation signals.
    user is nullable to capture pre-login events (e.g. anonymous views).
    """

    class ActionType(models.TextChoices):
        LOGIN           = "login",           "Login"
        LOGOUT          = "logout",          "Logout"
        SIGNUP          = "signup",          "Sign Up"
        VIEW_LISTING    = "view_listing",    "View Listing"
        SAVE_LISTING    = "save_listing",    "Save Listing"
        UNSAVE_LISTING  = "unsave_listing",  "Unsave Listing"
        UPVOTE          = "upvote",          "Upvote"
        UNVOTE          = "unvote",          "Remove Upvote"
        MARK_APPLIED    = "mark_applied",    "Mark as Applied"
        POST_COMMENT    = "post_comment",    "Post Comment"
        REPORT_LISTING  = "report_listing",  "Report Listing"
        SUBMIT_LISTING  = "submit_listing",  "Submit Listing"
        PROFILE_UPDATE  = "profile_update",  "Profile Update"
        FILTER_CHANGE   = "filter_change",   "Filter Changed"
        SEARCH          = "search",          "Search"
        SHARE_LISTING   = "share_listing",   "Share Listing"
        UPGRADE_PREMIUM = "upgrade_premium", "Upgrade to Premium"

    user         = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="activity_logs",
    )
    action_type  = models.CharField(max_length=20, choices=ActionType.choices)

    listing_type = models.CharField(max_length=5, choices=ListingType.choices, blank=True)
    job_listing  = models.ForeignKey(
        JobListing, on_delete=models.SET_NULL, null=True, blank=True
    )
    biz_listing  = models.ForeignKey(
        BizListing, on_delete=models.SET_NULL, null=True, blank=True
    )

    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    device_type = models.CharField(max_length=15, blank=True)  # "android", "ios", "web"
    app_version = models.CharField(max_length=20, blank=True)

    # Freeform context: search query, filter state, report reason, etc.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_activity_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "action_type"]),
            models.Index(fields=["action_type", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.action_type} @ {self.created_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# 14. ListingReport
# ---------------------------------------------------------------------------

class ListingReport(models.Model):
    """
    User-submitted reports on job or biz listings (spam, outdated, etc.).
    Admin reviews reports and updates status. Multiple users can report
    the same listing — one row per (user, listing) pair.
    """

    class ReportReason(models.TextChoices):
        INCORRECT_INFO = "incorrect_info", "Incorrect information"
        DUPLICATE      = "duplicate",      "Duplicate listing"
        SPAM           = "spam",           "Spam or misleading"
        EXPIRED        = "expired",        "Expired / outdated"
        OTHER          = "other",          "Other"

    class ReportStatus(models.TextChoices):
        PENDING   = "pending",   "Pending Review"
        REVIEWED  = "reviewed",  "Reviewed"
        RESOLVED  = "resolved",  "Resolved — action taken"
        DISMISSED = "dismissed", "Dismissed — no action"

    user         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="reports")
    listing_type = models.CharField(max_length=5, choices=ListingType.choices)
    job_listing  = models.ForeignKey(
        JobListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="reports",
    )
    biz_listing  = models.ForeignKey(
        BizListing, on_delete=models.CASCADE,
        null=True, blank=True, related_name="reports",
    )

    reason = models.CharField(max_length=20, choices=ReportReason.choices)
    status = models.CharField(
        max_length=10, choices=ReportStatus.choices, default=ReportStatus.PENDING
    )

    reviewer       = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_reports",
    )
    reviewer_notes = models.TextField(blank=True)
    reviewed_at    = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "listing_reports"
        # One report reason per user per listing
        constraints = [
            models.UniqueConstraint(
                fields=["user", "job_listing"],
                condition=models.Q(job_listing__isnull=False),
                name="unique_report_job",
            ),
            models.UniqueConstraint(
                fields=["user", "biz_listing"],
                condition=models.Q(biz_listing__isnull=False),
                name="unique_report_biz",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["job_listing", "status"]),
            models.Index(fields=["biz_listing", "status"]),
        ]

    def __str__(self):
        return f"{self.user} reported {self.listing_type} — {self.reason}"
