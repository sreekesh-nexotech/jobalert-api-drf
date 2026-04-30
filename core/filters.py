"""FilterSets for core resources."""
from django_filters import rest_framework as filters

from core.models import (
    AppMetaData,
    BizListing,
    Comment,
    FileManagement,
    JobListing,
    ListingReport,
    PointsHistory,
    SavedAndAppliedListing,
    SubscriptionHistory,
    Upvote,
    UserActivityLog,
)


class JobListingFilter(filters.FilterSet):
    category = filters.CharFilter(lookup_expr="iexact")
    sub_category = filters.CharFilter(lookup_expr="iexact")
    location = filters.CharFilter(lookup_expr="icontains")
    salary_min = filters.NumberFilter(field_name="salary_min", lookup_expr="gte")
    salary_max = filters.NumberFilter(field_name="salary_max", lookup_expr="lte")
    deadline_after = filters.DateFilter(field_name="application_deadline", lookup_expr="gte")
    posted_by = filters.UUIDFilter(field_name="posted_by__uid")

    class Meta:
        model = JobListing
        fields = [
            "status", "is_expired", "is_trending", "is_new",
            "is_featured", "is_verified", "experience_level",
            "category", "sub_category", "location",
            "salary_min", "salary_max", "deadline_after", "posted_by",
        ]


class BizListingFilter(filters.FilterSet):
    category = filters.CharFilter(lookup_expr="iexact")
    sub_category = filters.CharFilter(lookup_expr="iexact")
    venue = filters.CharFilter(lookup_expr="icontains")
    investment_min = filters.NumberFilter(field_name="investment_min", lookup_expr="gte")
    investment_max = filters.NumberFilter(field_name="investment_max", lookup_expr="lte")
    closing_after = filters.DateFilter(field_name="closing_date", lookup_expr="gte")
    posted_by = filters.UUIDFilter(field_name="posted_by__uid")

    class Meta:
        model = BizListing
        fields = [
            "status", "is_expired", "is_trending", "is_new",
            "is_featured", "is_verified", "opportunity_type",
            "category", "sub_category", "venue",
            "investment_min", "investment_max", "closing_after", "posted_by",
        ]


class FileManagementFilter(filters.FilterSet):
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")
    user = filters.UUIDFilter(field_name="user__uid")

    class Meta:
        model = FileManagement
        fields = ["file_type", "job_listing", "biz_listing", "user"]


class SavedAndAppliedListingFilter(filters.FilterSet):
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")

    class Meta:
        model = SavedAndAppliedListing
        fields = ["listing_type", "is_saved", "is_applied", "job_listing", "biz_listing"]


class UpvoteFilter(filters.FilterSet):
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")

    class Meta:
        model = Upvote
        fields = ["listing_type", "job_listing", "biz_listing"]


class CommentFilter(filters.FilterSet):
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")
    parent_comment = filters.UUIDFilter(field_name="parent_comment__uid")

    class Meta:
        model = Comment
        fields = ["listing_type", "is_deleted", "job_listing", "biz_listing", "parent_comment"]


class PointsHistoryFilter(filters.FilterSet):
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = PointsHistory
        fields = ["transaction_type", "reason", "created_after", "created_before"]


class SubscriptionHistoryFilter(filters.FilterSet):
    class Meta:
        model = SubscriptionHistory
        fields = ["plan_type", "payment_status", "payment_gateway", "is_auto_renew"]


class UserActivityLogFilter(filters.FilterSet):
    user = filters.UUIDFilter(field_name="user__uid")
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = UserActivityLog
        fields = [
            "user", "action_type", "listing_type", "device_type",
            "job_listing", "biz_listing", "created_after", "created_before",
        ]


class ListingReportFilter(filters.FilterSet):
    job_listing = filters.UUIDFilter(field_name="job_listing__uid")
    biz_listing = filters.UUIDFilter(field_name="biz_listing__uid")

    class Meta:
        model = ListingReport
        fields = ["listing_type", "reason", "status", "job_listing", "biz_listing"]


class AppMetaDataFilter(filters.FilterSet):
    valid_at = filters.DateTimeFilter(method="filter_valid_at")

    class Meta:
        model = AppMetaData
        fields = ["meta_type", "target_platform", "is_active", "valid_at"]

    def filter_valid_at(self, queryset, name, value):
        from django.db.models import Q
        return queryset.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=value),
            Q(valid_until__isnull=True) | Q(valid_until__gte=value),
        )
