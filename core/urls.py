"""URL routing for the JobAlert core app.

All endpoints are mounted under ``/api/v1/`` by ``config.urls``.
Resources are looked up by ``uid`` (UUID) — never the internal ``id``.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    AppMetaDataViewSet,
    AvatarUploadView,
    BizListingViewSet,
    CanSubmitListingView,
    ChangePasswordView,
    CommentLikeToggleView,
    CommentViewSet,
    CurrentUserView,
    FileManagementViewSet,
    FiltersMetaDataViewSet,
    HomeFeedView,
    JobListingViewSet,
    ListingReportViewSet,
    LoginView,
    LogoutView,
    NotificationViewSet,
    OTPSendView,
    OTPVerifyView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PointsHistoryViewSet,
    ProfileStatsView,
    RegisterView,
    RequestAccountDeletionView,
    SavedAndAppliedListingViewSet,
    StaticPageViewSet,
    SubscriptionHistoryViewSet,
    UpvoteViewSet,
    UserActivityLogViewSet,
    UserDetailsViewSet,
)

router = DefaultRouter()
router.register(r"job-listings", JobListingViewSet, basename="job-listing")
router.register(r"biz-listings", BizListingViewSet, basename="biz-listing")
router.register(r"files", FileManagementViewSet, basename="file")
router.register(r"saved-listings", SavedAndAppliedListingViewSet, basename="saved-listing")
router.register(r"upvotes", UpvoteViewSet, basename="upvote")
router.register(r"comments", CommentViewSet, basename="comment")
router.register(r"points/history", PointsHistoryViewSet, basename="points-history")
router.register(r"subscriptions", SubscriptionHistoryViewSet, basename="subscription")
router.register(r"filter-prefs", FiltersMetaDataViewSet, basename="filter-pref")
router.register(r"app-meta", AppMetaDataViewSet, basename="app-meta")
router.register(r"activity-logs", UserActivityLogViewSet, basename="activity-log")
router.register(r"reports", ListingReportViewSet, basename="report")
router.register(r"user-details", UserDetailsViewSet, basename="user-details")
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"static-pages", StaticPageViewSet, basename="static-page")

auth_patterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("otp/send/", OTPSendView.as_view(), name="auth-otp-send"),
    path("otp/verify/", OTPVerifyView.as_view(), name="auth-otp-verify"),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]

user_patterns = [
    path("me/", CurrentUserView.as_view(), name="user-me"),
    path("me/avatar/", AvatarUploadView.as_view(), name="user-me-avatar"),
    path("me/stats/", ProfileStatsView.as_view(), name="user-me-stats"),
    path(
        "me/request-deletion/",
        RequestAccountDeletionView.as_view(),
        name="user-me-request-deletion",
    ),
]

listing_patterns = [
    path("can-submit/", CanSubmitListingView.as_view(), name="listing-can-submit"),
]

comment_like_patterns = [
    path(
        "<uuid:uid>/like/",
        CommentLikeToggleView.as_view(),
        name="comment-like-toggle",
    ),
]

home_patterns = [
    path("feed/", HomeFeedView.as_view(), name="home-feed"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("users/", include(user_patterns)),
    path("listings/", include(listing_patterns)),
    path("comments/", include(comment_like_patterns)),
    path("home/", include(home_patterns)),
    path("", include(router.urls)),
]
