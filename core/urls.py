"""URL routing for the JobAlert core app.

All endpoints are mounted under ``/api/v1/`` by ``config.urls``.
Resources are looked up by ``uid`` (UUID) — never the internal ``id``.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    AppMetaDataViewSet,
    BizListingViewSet,
    ChangePasswordView,
    CommentViewSet,
    CurrentUserView,
    FileManagementViewSet,
    FiltersMetaDataViewSet,
    JobListingViewSet,
    ListingReportViewSet,
    LoginView,
    LogoutView,
    PointsHistoryViewSet,
    RegisterView,
    SavedAndAppliedListingViewSet,
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

auth_patterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]

user_patterns = [
    path("me/", CurrentUserView.as_view(), name="user-me"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("users/", include(user_patterns)),
    path("", include(router.urls)),
]
