from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.models import (
    AppMetaData,
    BizListing,
    Comment,
    FileManagement,
    FiltersMetaData,
    JobListing,
    ListingReport,
    PointsHistory,
    SavedAndAppliedListing,
    SubscriptionHistory,
    Upvote,
    User,
    UserActivityLog,
    UserDetails,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("email", "username", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("-date_joined",)
    readonly_fields = ("uid", "date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "username", "password", "uid")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2"),
        }),
    )


@admin.register(UserDetails)
class UserDetailsAdmin(admin.ModelAdmin):
    list_display = ("user", "account_status", "is_premium", "total_points", "points_level", "otp_verified")
    list_filter = ("account_status", "is_premium", "points_level", "otp_verified")
    search_fields = ("user__email", "user__username")
    raw_id_fields = ("user",)


class _ListingAdminBase(admin.ModelAdmin):
    list_display = ("title", "category", "status", "is_expired", "is_featured", "upvotes_count", "created_at")
    list_filter = ("status", "is_expired", "is_featured", "is_trending", "is_verified", "category")
    search_fields = ("title", "description", "category", "sub_category")
    readonly_fields = ("uid", "upvotes_count", "comments_count", "saves_count", "views_count", "created_at", "updated_at")
    raw_id_fields = ("posted_by", "approved_by")


@admin.register(JobListing)
class JobListingAdmin(_ListingAdminBase):
    list_filter = _ListingAdminBase.list_filter + ("experience_level",)


@admin.register(BizListing)
class BizListingAdmin(_ListingAdminBase):
    list_filter = _ListingAdminBase.list_filter + ("opportunity_type",)


@admin.register(FileManagement)
class FileManagementAdmin(admin.ModelAdmin):
    list_display = ("file_name", "file_type", "uploaded_by", "created_at")
    list_filter = ("file_type",)
    search_fields = ("file_name", "description")
    raw_id_fields = ("job_listing", "biz_listing", "user", "uploaded_by")


@admin.register(SavedAndAppliedListing)
class SavedAndAppliedListingAdmin(admin.ModelAdmin):
    list_display = ("user", "listing_type", "is_saved", "is_applied", "saved_at", "applied_at")
    list_filter = ("listing_type", "is_saved", "is_applied")
    raw_id_fields = ("user", "job_listing", "biz_listing")


@admin.register(Upvote)
class UpvoteAdmin(admin.ModelAdmin):
    list_display = ("user", "listing_type", "job_listing", "biz_listing", "created_at")
    list_filter = ("listing_type",)
    raw_id_fields = ("user", "job_listing", "biz_listing")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("user", "listing_type", "text", "is_deleted", "created_at")
    list_filter = ("listing_type", "is_deleted")
    search_fields = ("text",)
    raw_id_fields = ("user", "job_listing", "biz_listing", "parent_comment")


@admin.register(PointsHistory)
class PointsHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "transaction_type", "reason", "points", "balance_after", "created_at")
    list_filter = ("transaction_type", "reason")
    raw_id_fields = ("user", "job_listing", "biz_listing")
    search_fields = ("user__email",)


@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_type", "amount", "currency", "payment_status", "created_at")
    list_filter = ("plan_type", "payment_status", "currency", "payment_gateway")
    raw_id_fields = ("user",)
    search_fields = ("user__email", "gateway_order_id", "gateway_payment_id")


@admin.register(FiltersMetaData)
class FiltersMetaDataAdmin(admin.ModelAdmin):
    list_display = ("user", "filter_context", "sort_preference", "updated_at")
    list_filter = ("filter_context", "sort_preference")
    raw_id_fields = ("user",)


@admin.register(AppMetaData)
class AppMetaDataAdmin(admin.ModelAdmin):
    list_display = ("key", "meta_type", "target_platform", "is_active", "priority", "valid_from", "valid_until")
    list_filter = ("meta_type", "target_platform", "is_active")
    search_fields = ("key", "title")


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action_type", "listing_type", "device_type", "created_at")
    list_filter = ("action_type", "listing_type", "device_type")
    raw_id_fields = ("user", "job_listing", "biz_listing")
    readonly_fields = ("created_at",)


@admin.register(ListingReport)
class ListingReportAdmin(admin.ModelAdmin):
    list_display = ("user", "listing_type", "reason", "status", "reviewer", "created_at")
    list_filter = ("reason", "status", "listing_type")
    raw_id_fields = ("user", "reviewer", "job_listing", "biz_listing")
