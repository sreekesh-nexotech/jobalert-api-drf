"""DRF serializers for the JobAlert core app.

Conventions
-----------
- ``uid`` is the only public identifier exposed in API payloads. Internal
  ``id`` PKs are never serialised.
- Foreign keys to listings (job/biz) are accepted as a single ``listing_uid``
  + ``listing_type`` pair on write, then resolved to the right column.
- Explicit ``fields = [...]`` everywhere; no ``__all__``.
- Read serializers never expose password/permission internals.
"""
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from core.models import (
    AppMetaData,
    BizListing,
    Comment,
    CommentLike,
    FileManagement,
    FiltersMetaData,
    JobListing,
    ListingReport,
    ListingType,
    Notification,
    OTPCode,
    PointsHistory,
    SavedAndAppliedListing,
    StaticPage,
    SubscriptionHistory,
    Upvote,
    User,
    UserActivityLog,
    UserDetails,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_listing(listing_type: str, listing_uid):
    """Return ``(job_listing, biz_listing)`` tuple, exactly one set."""
    if listing_type == ListingType.JOB:
        try:
            return JobListing.objects.get(uid=listing_uid), None
        except JobListing.DoesNotExist:
            raise serializers.ValidationError({"listing_uid": "Job listing not found."})
    if listing_type == ListingType.BIZ:
        try:
            return None, BizListing.objects.get(uid=listing_uid)
        except BizListing.DoesNotExist:
            raise serializers.ValidationError({"listing_uid": "Business listing not found."})
    raise serializers.ValidationError({"listing_type": "Must be 'job' or 'biz'."})


class _PolymorphicListingMixin:
    """Adds writable ``listing_uid`` + ``listing_type`` and read-only
    ``listing_uid`` resolved from whichever FK is set."""

    def get_listing_uid(self, obj):
        if obj.job_listing_id:
            return str(obj.job_listing.uid)
        if obj.biz_listing_id:
            return str(obj.biz_listing.uid)
        return None


# ---------------------------------------------------------------------------
# User / auth
# ---------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    uid = serializers.UUIDField(read_only=True)
    country_code  = serializers.CharField(required=False, allow_blank=True, default="")
    mobile_number = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = User
        fields = [
            "uid", "email", "username", "first_name", "last_name",
            "country_code", "mobile_number",
            "is_active", "date_joined", "last_login",
        ]
        read_only_fields = ["uid", "email", "is_active", "date_joined", "last_login"]
        validators = []


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    # Declared explicitly so they bypass the auto-generated
    # UniqueTogetherValidator (which would treat both as required).
    country_code  = serializers.CharField(required=False, allow_blank=True, default="")
    mobile_number = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = User
        fields = [
            "email", "username", "password", "password_confirm",
            "first_name", "last_name", "country_code", "mobile_number",
        ]
        # Disable DRF's auto UniqueTogetherValidator — our explicit
        # ``validate()`` does the duplicate-mobile check with friendlier copy.
        validators = []
        extra_kwargs = {
            "first_name": {"required": False, "allow_blank": True},
            "last_name":  {"required": False, "allow_blank": True},
            "username":   {"required": False},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_mobile_number(self, value):
        # Strip non-digits for canonical storage.
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if digits and len(digits) < 7:
            raise serializers.ValidationError("Enter a valid mobile number.")
        return digits

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password": "Passwords do not match."})

        cc = attrs.get("country_code", "")
        mob = attrs.get("mobile_number", "")
        if mob and not cc:
            raise serializers.ValidationError(
                {"country_code": "Country code is required when mobile number is provided."}
            )
        if mob and User.objects.filter(country_code=cc, mobile_number=mob).exists():
            raise serializers.ValidationError(
                {"mobile_number": "A user with this mobile number already exists."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        if not validated_data.get("username"):
            validated_data["username"] = validated_data["email"].split("@")[0]
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        UserDetails.objects.get_or_create(user=user)
        return user

    def to_representation(self, instance):
        return UserSerializer(instance, context=self.context).data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class UserDetailsSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = UserDetails
        fields = [
            "user",
            "date_of_birth", "gender", "state", "city", "profile_picture_url",
            "job_preferences",
            "is_premium", "premium_expires_at",
            "account_status", "deletion_requested_at",
            "total_points", "points_level",
            "total_posts", "total_saved", "total_upvotes_given",
            "otp_verified",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "user",
            "is_premium", "premium_expires_at",
            "total_points", "points_level",
            "total_posts", "total_saved", "total_upvotes_given",
            "otp_verified",
            "created_at", "updated_at",
        ]


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


class _ListingBaseSerializer(serializers.ModelSerializer):
    """Shared logic for Job and Biz listings."""

    uid = serializers.UUIDField(read_only=True)
    posted_by = UserSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["posted_by"] = request.user
        return super().create(validated_data)


class JobListingSerializer(_ListingBaseSerializer):
    class Meta:
        model = JobListing
        fields = [
            "uid", "posted_by", "approved_by",
            "title", "category", "sub_category", "qualification", "description",
            "location", "experience_level",
            "salary_min", "salary_max", "salary_display",
            "application_deadline",
            "source_name", "source_url", "tags",
            "is_trending", "is_new", "is_featured", "is_verified",
            "thumbnail_url", "image_2_url", "image_3_url", "image_4_url", "image_5_url",
            "status", "is_expired", "approved_at",
            "upvotes_count", "comments_count", "saves_count", "views_count",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "uid", "posted_by", "approved_by", "approved_at",
            "status", "is_expired",
            "is_trending", "is_new", "is_featured", "is_verified",
            "upvotes_count", "comments_count", "saves_count", "views_count",
            "created_at", "updated_at",
        ]


class BizListingSerializer(_ListingBaseSerializer):
    class Meta:
        model = BizListing
        fields = [
            "uid", "posted_by", "approved_by",
            "title", "category", "sub_category", "description",
            "opportunity_type", "venue",
            "investment_min", "investment_max", "investment_display",
            "date_info", "closing_date",
            "source_name", "source_url", "tags",
            "is_trending", "is_new", "is_featured", "is_verified",
            "thumbnail_url", "image_2_url", "image_3_url", "image_4_url", "image_5_url",
            "status", "is_expired", "approved_at",
            "upvotes_count", "comments_count", "saves_count", "views_count",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "uid", "posted_by", "approved_by", "approved_at",
            "status", "is_expired",
            "is_trending", "is_new", "is_featured", "is_verified",
            "upvotes_count", "comments_count", "saves_count", "views_count",
            "created_at", "updated_at",
        ]


class ListingModerationSerializer(serializers.Serializer):
    """Admin-only payload for approve/reject/feature/verify actions."""

    notes = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class FileManagementSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    uid = serializers.UUIDField(read_only=True)
    listing_uid = serializers.SerializerMethodField()
    listing_type = serializers.ChoiceField(
        choices=ListingType.choices, required=False, write_only=True
    )
    target_listing_uid = serializers.UUIDField(required=False, write_only=True)
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = FileManagement
        fields = [
            "uid", "listing_uid", "listing_type", "target_listing_uid",
            "file_name", "file_url", "file_type", "mime_type", "file_size_bytes",
            "description", "uploaded_by", "created_at",
        ]
        read_only_fields = ["uid", "uploaded_by", "created_at"]

    def validate(self, attrs):
        listing_type = attrs.pop("listing_type", None)
        target_uid = attrs.pop("target_listing_uid", None)
        if listing_type and target_uid:
            job, biz = _resolve_listing(listing_type, target_uid)
            attrs["job_listing"] = job
            attrs["biz_listing"] = biz
        elif listing_type or target_uid:
            raise serializers.ValidationError(
                "Both listing_type and target_listing_uid must be provided together."
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["uploaded_by"] = request.user
            validated_data.setdefault("user", request.user)
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# Engagement: Saved/Applied, Upvote, Comment
# ---------------------------------------------------------------------------


class SavedAndAppliedListingSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    listing_uid = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True)

    class Meta:
        model = SavedAndAppliedListing
        fields = [
            "id", "user", "listing_type", "listing_uid",
            "is_saved", "is_applied", "saved_at", "applied_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class UpvoteSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    listing_uid = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True)

    class Meta:
        model = Upvote
        fields = ["id", "user", "listing_type", "listing_uid", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class CommentSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    uid = serializers.UUIDField(read_only=True)
    user = UserSerializer(read_only=True)
    listing_uid = serializers.SerializerMethodField()
    listing_type = serializers.ChoiceField(choices=ListingType.choices)
    target_listing_uid = serializers.UUIDField(required=False, write_only=True)
    parent_comment_uid = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    parent_comment = serializers.SerializerMethodField(read_only=True)
    replies_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            "uid", "user", "listing_type", "listing_uid",
            "target_listing_uid", "parent_comment_uid", "parent_comment",
            "text", "is_deleted", "replies_count", "likes_count",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "uid", "user", "is_deleted", "likes_count", "created_at", "updated_at",
        ]

    def get_parent_comment(self, obj):
        return str(obj.parent_comment.uid) if obj.parent_comment_id else None

    def get_replies_count(self, obj):
        return obj.replies.filter(is_deleted=False).count()

    def validate(self, attrs):
        listing_type = attrs.get("listing_type")
        target_uid = attrs.pop("target_listing_uid", None)
        parent_uid = attrs.pop("parent_comment_uid", None)

        if not target_uid:
            raise serializers.ValidationError({"target_listing_uid": "This field is required."})
        job, biz = _resolve_listing(listing_type, target_uid)
        attrs["job_listing"] = job
        attrs["biz_listing"] = biz

        if parent_uid:
            try:
                attrs["parent_comment"] = Comment.objects.get(uid=parent_uid)
            except Comment.DoesNotExist:
                raise serializers.ValidationError({"parent_comment_uid": "Parent comment not found."})
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# Points / Subscriptions
# ---------------------------------------------------------------------------


class PointsHistorySerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    listing_uid = serializers.SerializerMethodField()

    class Meta:
        model = PointsHistory
        fields = [
            "id", "user", "transaction_type", "reason",
            "points", "balance_after",
            "listing_uid", "notes", "created_at",
        ]
        read_only_fields = fields


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    uid = serializers.UUIDField(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = SubscriptionHistory
        fields = [
            "uid", "user",
            "plan_type", "plan_display_name", "amount", "currency",
            "payment_status", "payment_gateway",
            "gateway_order_id", "gateway_payment_id", "gateway_signature",
            "subscription_start", "subscription_end", "is_auto_renew",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "uid", "user",
            "payment_status", "gateway_payment_id", "gateway_signature",
            "subscription_start", "subscription_end",
            "created_at", "updated_at",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# Filters / App meta / Activity / Reports
# ---------------------------------------------------------------------------


class FiltersMetaDataSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = FiltersMetaData
        fields = [
            "id", "user", "filter_context",
            "selected_categories", "selected_locations",
            "selected_experience_levels", "selected_opportunity_types",
            "sort_preference", "search_query",
            "remote_only", "verified_only", "hide_expired",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user
        instance, _ = FiltersMetaData.objects.update_or_create(
            user=request.user,
            filter_context=validated_data.pop("filter_context"),
            defaults=validated_data,
        )
        return instance


class AppMetaDataSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = AppMetaData
        fields = [
            "id", "key", "meta_type", "title", "message",
            "cta_label", "cta_url",
            "target_platform", "min_app_version", "max_app_version",
            "is_active", "is_dismissible", "priority",
            "valid_from", "valid_until", "extra_data",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class UserActivityLogSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    listing_uid = serializers.SerializerMethodField()
    listing_type = serializers.ChoiceField(
        choices=ListingType.choices, required=False, allow_blank=True
    )
    target_listing_uid = serializers.UUIDField(required=False, write_only=True)

    class Meta:
        model = UserActivityLog
        fields = [
            "id", "user", "action_type", "listing_type", "listing_uid",
            "target_listing_uid",
            "ip_address", "device_type", "app_version",
            "metadata", "created_at",
        ]
        read_only_fields = ["id", "user", "ip_address", "created_at"]

    def validate(self, attrs):
        listing_type = attrs.get("listing_type")
        target_uid = attrs.pop("target_listing_uid", None)
        if listing_type and target_uid:
            job, biz = _resolve_listing(listing_type, target_uid)
            attrs["job_listing"] = job
            attrs["biz_listing"] = biz
        return attrs


class ListingReportSerializer(_PolymorphicListingMixin, serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    reviewer = UserSerializer(read_only=True)
    listing_uid = serializers.SerializerMethodField()
    listing_type = serializers.ChoiceField(choices=ListingType.choices)
    target_listing_uid = serializers.UUIDField(write_only=True)

    class Meta:
        model = ListingReport
        fields = [
            "id", "user", "listing_type", "listing_uid", "target_listing_uid",
            "reason", "status",
            "reviewer", "reviewer_notes", "reviewed_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user", "status",
            "reviewer", "reviewer_notes", "reviewed_at",
            "created_at", "updated_at",
        ]

    def validate(self, attrs):
        listing_type = attrs.get("listing_type")
        target_uid = attrs.pop("target_listing_uid")
        job, biz = _resolve_listing(listing_type, target_uid)
        attrs["job_listing"] = job
        attrs["biz_listing"] = biz
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)


class ListingReportReviewSerializer(serializers.Serializer):
    """Admin-only payload for reviewing a report."""

    status = serializers.ChoiceField(choices=ListingReport.ReportStatus.choices)
    reviewer_notes = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# OTP / password reset / login by email-or-mobile
# ---------------------------------------------------------------------------


class OTPSendSerializer(serializers.Serializer):
    """Request payload for issuing an OTP. ``identifier`` is an email."""

    identifier = serializers.CharField()
    purpose = serializers.ChoiceField(choices=OTPCode.Purpose.choices)

    def validate_identifier(self, value):
        return value.strip().lower()


class OTPVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField()
    purpose    = serializers.ChoiceField(choices=OTPCode.Purpose.choices)
    code       = serializers.CharField(min_length=4, max_length=10)

    def validate_identifier(self, value):
        return value.strip().lower()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email        = serializers.EmailField()
    code         = serializers.CharField(min_length=4, max_length=10)
    new_password = serializers.CharField(validators=[validate_password])


class LoginByIdentifierSerializer(serializers.Serializer):
    """Login by email *or* country_code+mobile_number. Returns JWT pair."""

    identifier = serializers.CharField(help_text="Email or mobile number")
    country_code = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)


# ---------------------------------------------------------------------------
# Comment likes
# ---------------------------------------------------------------------------


class CommentLikeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    comment_uid = serializers.SerializerMethodField()

    class Meta:
        model = CommentLike
        fields = ["id", "user", "comment_uid", "created_at"]
        read_only_fields = fields

    def get_comment_uid(self, obj):
        return str(obj.comment.uid)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationSerializer(serializers.ModelSerializer):
    related_job_listing_uid = serializers.SerializerMethodField()
    related_biz_listing_uid = serializers.SerializerMethodField()
    related_comment_uid     = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "uid", "notification_type", "title", "message", "link_url",
            "related_job_listing_uid", "related_biz_listing_uid",
            "related_comment_uid",
            "is_read", "read_at", "created_at",
        ]
        read_only_fields = fields

    def get_related_job_listing_uid(self, obj):
        return str(obj.related_job_listing.uid) if obj.related_job_listing_id else None

    def get_related_biz_listing_uid(self, obj):
        return str(obj.related_biz_listing.uid) if obj.related_biz_listing_id else None

    def get_related_comment_uid(self, obj):
        return str(obj.related_comment.uid) if obj.related_comment_id else None


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------


class StaticPageSerializer(serializers.ModelSerializer):
    updated_by = UserSerializer(read_only=True)

    class Meta:
        model = StaticPage
        fields = [
            "slug", "title", "body", "is_published", "version",
            "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = ["version", "updated_by", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Profile stats / avatar / pending-listing check
# ---------------------------------------------------------------------------


class ProfileStatsSerializer(serializers.Serializer):
    posts          = serializers.IntegerField()
    saved          = serializers.IntegerField()
    upvotes_given  = serializers.IntegerField()
    points         = serializers.IntegerField()
    points_level   = serializers.CharField()
    next_level     = serializers.CharField(allow_null=True)
    next_level_at  = serializers.IntegerField(allow_null=True)
    progress_pct   = serializers.IntegerField()
    is_premium     = serializers.BooleanField()
    premium_expires_at = serializers.DateTimeField(allow_null=True)


class AvatarUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(write_only=True)
    profile_picture_url = serializers.URLField(read_only=True)


class CanSubmitListingSerializer(serializers.Serializer):
    can_submit = serializers.BooleanField()
    pending_listing_type = serializers.CharField(allow_null=True)
    pending_listing_uid  = serializers.UUIDField(allow_null=True)
    pending_title        = serializers.CharField(allow_null=True)
    pending_submitted_at = serializers.DateTimeField(allow_null=True)


# ---------------------------------------------------------------------------
# Home feed
# ---------------------------------------------------------------------------


class HomeFeedSerializer(serializers.Serializer):
    new_jobs_count   = serializers.IntegerField()
    suggested_jobs   = JobListingSerializer(many=True)
    trending_biz     = BizListingSerializer(many=True)
    unread_notifications = serializers.IntegerField()
    stats            = ProfileStatsSerializer()
