"""DRF views for the JobAlert core app.

Conventions
-----------
- All resources are looked up by ``uid`` (UUID) — never the internal ``id``.
- ``IsAdminOrReadOnly`` is the default for content where end users are
  read-only (listings as a whole, app meta, points/subs of others).
- ``IsOwnerOrReadOnly`` lets owners edit their own resources (comments,
  filter prefs, their own listings before approval).
- Admin (``is_staff``) has unrestricted write across the API.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.filters import (
    AppMetaDataFilter,
    BizListingFilter,
    CommentFilter,
    FileManagementFilter,
    JobListingFilter,
    ListingReportFilter,
    PointsHistoryFilter,
    SavedAndAppliedListingFilter,
    SubscriptionHistoryFilter,
    UpvoteFilter,
    UserActivityLogFilter,
)
from core.email import (
    RESEND_COOLDOWN,
    consume_otp,
    issue_otp,
    send_otp_email,
)
from core.models import (
    AppMetaData,
    BizListing,
    Comment,
    CommentLike,
    FileManagement,
    FiltersMetaData,
    JobListing,
    ListingReport,
    ListingStatus,
    ListingType,
    Notification,
    OTPCode,
    PointsHistory,
    SavedAndAppliedListing,
    StaticPage,
    SubscriptionHistory,
    Upvote,
    UserActivityLog,
    UserDetails,
)
from core.permissions import (
    IsAdminOrPublicRead,
    IsAdminOrReadOnly,
    IsOwnerOrAdmin,
    IsOwnerOrReadOnly,
)
from core.serializers import (
    AppMetaDataSerializer,
    AvatarUploadSerializer,
    BizListingSerializer,
    CanSubmitListingSerializer,
    ChangePasswordSerializer,
    CommentLikeSerializer,
    CommentSerializer,
    FileManagementSerializer,
    FiltersMetaDataSerializer,
    HomeFeedSerializer,
    JobListingSerializer,
    ListingModerationSerializer,
    ListingReportReviewSerializer,
    ListingReportSerializer,
    LoginByIdentifierSerializer,
    NotificationSerializer,
    OTPSendSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PointsHistorySerializer,
    ProfileStatsSerializer,
    RegisterSerializer,
    SavedAndAppliedListingSerializer,
    StaticPageSerializer,
    SubscriptionHistorySerializer,
    UpvoteSerializer,
    UserActivityLogSerializer,
    UserDetailsSerializer,
    UserSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class UidLookupMixin:
    """Look up resources by ``uid`` UUID instead of internal ``id``."""

    lookup_field = "uid"
    lookup_url_kwarg = "uid"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterView(GenericAPIView):
    """Public endpoint to create a new account.

    Returns the newly-created user plus an access/refresh JWT pair so the
    client can sign the user in immediately. As a side effect, a signup
    OTP is issued and emailed (best-effort — failures are swallowed so a
    transient mail outage doesn't block the registration).
    """

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=UserSerializer)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Best-effort signup OTP delivery.
        try:
            _, code = issue_otp(
                identifier=user.email,
                purpose=OTPCode.Purpose.SIGNUP_VERIFY,
                user=user,
            )
            send_otp_email(
                email=user.email, code=code, purpose=OTPCode.Purpose.SIGNUP_VERIFY
            )
        except Exception:  # noqa: BLE001 — never fail registration on mail issues
            pass

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "otp_sent": True,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(GenericAPIView):
    """Login with email *or* mobile (country_code + mobile_number)."""

    serializer_class = LoginByIdentifierSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        country_code = serializer.validated_data.get("country_code", "").strip()
        password = serializer.validated_data["password"]

        user = self._lookup_user(identifier, country_code)
        if user is None or not user.check_password(password):
            raise AuthenticationFailed("Invalid credentials.")
        if not user.is_active:
            raise AuthenticationFailed("Account is inactive.")

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        )

    @staticmethod
    def _lookup_user(identifier: str, country_code: str):
        if "@" in identifier:
            return User.objects.filter(email__iexact=identifier).first()
        digits = "".join(ch for ch in identifier if ch.isdigit())
        if not digits:
            return None
        qs = User.objects.exclude(mobile_number="").filter(mobile_number=digits)
        if country_code:
            qs = qs.filter(country_code=country_code)
        return qs.first()


class LogoutView(APIView):
    """Blacklist the supplied refresh token."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request={"application/json": {"type": "object", "properties": {"refresh": {"type": "string"}}}},
        responses={205: None},
    )
    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            raise ValidationError({"refresh": "This field is required."})
        try:
            RefreshToken(token).blacklist()
        except Exception as exc:  # noqa: BLE001 — surface upstream validation errors
            raise ValidationError({"refresh": str(exc)})
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Users / profile
# ---------------------------------------------------------------------------


class CurrentUserView(APIView):
    """`/users/me/` — read or partially update the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserDetailsViewSet(viewsets.ModelViewSet):
    """Profile data. Each user has exactly one row, accessed by their own
    user UUID. Admin can read/write any; users only their own."""

    queryset = UserDetails.objects.select_related("user").all()
    serializer_class = UserDetailsSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    lookup_field = "user__uid"
    lookup_url_kwarg = "uid"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        # End users cannot create UserDetails for anyone but themselves —
        # and registration auto-creates one row already. Admins may create
        # arbitrary rows (e.g. backfill).
        if not self.request.user.is_staff:
            serializer.save(user=self.request.user)
        else:
            serializer.save()


# ---------------------------------------------------------------------------
# Listings (Job + Biz)
# ---------------------------------------------------------------------------


class _ListingPermission(permissions.BasePermission):
    """Listing-specific rules:

    - Read: any authenticated user.
    - Create: any authenticated user (creates a PENDING listing).
    - Update/delete: owner while still PENDING, or any admin at any time.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        if obj.posted_by_id != request.user.id:
            return False
        return obj.status == ListingStatus.PENDING


class _ListingViewSetBase(UidLookupMixin, viewsets.ModelViewSet):
    """Shared listing behaviour for jobs and businesses."""

    permission_classes = [_ListingPermission]
    filter_backends = [
        *viewsets.ModelViewSet.filter_backends,
    ]
    search_fields = ["title", "description", "category", "sub_category", "tags"]
    ordering_fields = ["created_at", "upvotes_count", "comments_count", "saves_count", "views_count"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Non-admin end users only see approved & non-expired listings,
        # plus their own pending/rejected listings.
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            from django.db.models import Q

            qs = qs.filter(
                Q(status=ListingStatus.APPROVED, is_expired=False)
                | Q(posted_by=self.request.user)
            )
        return qs

    # --- Engagement sub-actions ---------------------------------------------

    def _toggle_engagement(self, request, listing, *, kind: str):
        """Shared upvote/save toggle. ``kind`` ∈ {"upvote", "save"}."""
        listing_type = (
            ListingType.JOB if isinstance(listing, JobListing) else ListingType.BIZ
        )
        is_job = listing_type == ListingType.JOB
        if kind == "upvote":
            qs = Upvote.objects.filter(
                user=request.user,
                **({"job_listing": listing} if is_job else {"biz_listing": listing}),
            )
            if request.method == "POST":
                _, created = Upvote.objects.get_or_create(
                    user=request.user,
                    listing_type=listing_type,
                    **({"job_listing": listing} if is_job else {"biz_listing": listing}),
                )
                return Response(
                    {"upvoted": True, "created": created},
                    status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
                )
            qs.delete()
            return Response({"upvoted": False}, status=status.HTTP_204_NO_CONTENT)

        # save
        kwargs = {"job_listing": listing} if is_job else {"biz_listing": listing}
        record, _ = SavedAndAppliedListing.objects.get_or_create(
            user=request.user, listing_type=listing_type, **kwargs
        )
        if request.method == "POST":
            record.is_saved = True
            record.saved_at = timezone.now()
            record.save(update_fields=["is_saved", "saved_at", "updated_at"])
            return Response({"saved": True}, status=status.HTTP_200_OK)
        record.is_saved = False
        record.saved_at = None
        record.save(update_fields=["is_saved", "saved_at", "updated_at"])
        return Response({"saved": False}, status=status.HTTP_204_NO_CONTENT)

    def get_permissions(self):
        # Engagement / view actions only need an authenticated user; ownership
        # rules don't apply because users are interacting with someone else's
        # listing by design. Moderation actions are admin-only.
        if self.action in {"upvote", "save_listing", "apply", "increment_view"}:
            return [permissions.IsAuthenticated()]
        if self.action in {"approve", "reject"}:
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return super().get_permissions()

    @action(detail=True, methods=["post", "delete"], url_path="upvote", url_name="upvote")
    def upvote(self, request, uid=None):
        return self._toggle_engagement(request, self.get_object(), kind="upvote")

    @action(detail=True, methods=["post", "delete"], url_path="save", url_name="save")
    def save_listing(self, request, uid=None):
        return self._toggle_engagement(request, self.get_object(), kind="save")

    @action(detail=True, methods=["post"], url_path="apply", url_name="apply")
    def apply(self, request, uid=None):
        listing = self.get_object()
        listing_type = (
            ListingType.JOB if isinstance(listing, JobListing) else ListingType.BIZ
        )
        kwargs = (
            {"job_listing": listing}
            if listing_type == ListingType.JOB
            else {"biz_listing": listing}
        )
        record, _ = SavedAndAppliedListing.objects.get_or_create(
            user=request.user, listing_type=listing_type, **kwargs
        )
        record.is_applied = True
        record.applied_at = timezone.now()
        record.save(update_fields=["is_applied", "applied_at", "updated_at"])
        return Response({"applied": True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="view", url_name="view")
    def increment_view(self, request, uid=None):
        """Idempotent-ish view counter bump. Cheap, no dedupe."""
        listing = self.get_object()
        type(listing).objects.filter(pk=listing.pk).update(
            views_count=F("views_count") + 1
        )
        listing.refresh_from_db(fields=["views_count"])
        return Response({"views_count": listing.views_count})

    # --- Admin moderation ---------------------------------------------------

    def _moderate(self, request, *, new_status: str):
        if not request.user.is_staff:
            self.permission_denied(request, message="Admin only.")
        listing = self.get_object()
        serializer = ListingModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing.status = new_status
        listing.approved_by = request.user if new_status == ListingStatus.APPROVED else listing.approved_by
        listing.approved_at = timezone.now() if new_status == ListingStatus.APPROVED else listing.approved_at
        listing.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return Response(self.get_serializer(listing).data)

    @action(detail=True, methods=["post"], url_path="approve", url_name="approve")
    def approve(self, request, uid=None):
        return self._moderate(request, new_status=ListingStatus.APPROVED)

    @action(detail=True, methods=["post"], url_path="reject", url_name="reject")
    def reject(self, request, uid=None):
        return self._moderate(request, new_status=ListingStatus.REJECTED)


class JobListingViewSet(_ListingViewSetBase):
    queryset = JobListing.objects.select_related("posted_by", "approved_by").all()
    serializer_class = JobListingSerializer
    filterset_class = JobListingFilter


class BizListingViewSet(_ListingViewSetBase):
    queryset = BizListing.objects.select_related("posted_by", "approved_by").all()
    serializer_class = BizListingSerializer
    filterset_class = BizListingFilter


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class FileManagementViewSet(UidLookupMixin, viewsets.ModelViewSet):
    queryset = FileManagement.objects.select_related(
        "uploaded_by", "user", "job_listing", "biz_listing"
    ).order_by("-created_at")
    serializer_class = FileManagementSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    filterset_class = FileManagementFilter
    search_fields = ["file_name", "description"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(uploaded_by=self.request.user)
        return qs


# ---------------------------------------------------------------------------
# Engagement: Saved/Applied + Upvotes (read-only listing of own data)
# ---------------------------------------------------------------------------


class SavedAndAppliedListingViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Read-only list of the current user's saved/applied listings."""

    serializer_class = SavedAndAppliedListingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = SavedAndAppliedListingFilter

    def get_queryset(self):
        return (
            SavedAndAppliedListing.objects.select_related(
                "user", "job_listing", "biz_listing"
            )
            .filter(user=self.request.user)
            .order_by("-updated_at")
        )


class UpvoteViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Read-only list of the current user's upvotes. Toggling happens via
    the listing's `/upvote/` action."""

    serializer_class = UpvoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = UpvoteFilter

    def get_queryset(self):
        return (
            Upvote.objects.select_related("user", "job_listing", "biz_listing")
            .filter(user=self.request.user)
            .order_by("-created_at")
        )


class CommentViewSet(UidLookupMixin, viewsets.ModelViewSet):
    queryset = Comment.objects.select_related(
        "user", "job_listing", "biz_listing", "parent_comment"
    ).filter(is_deleted=False)
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    filterset_class = CommentFilter
    search_fields = ["text"]

    def perform_destroy(self, instance):
        # Soft delete preserves thread structure.
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


# ---------------------------------------------------------------------------
# Points / Subscriptions
# ---------------------------------------------------------------------------


class PointsHistoryViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Each user sees only their own ledger; admin sees everyone's."""

    serializer_class = PointsHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = PointsHistoryFilter

    def get_queryset(self):
        qs = PointsHistory.objects.select_related("user", "job_listing", "biz_listing")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)


class SubscriptionHistoryViewSet(UidLookupMixin, viewsets.ModelViewSet):
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    filterset_class = SubscriptionHistoryFilter

    def get_queryset(self):
        qs = SubscriptionHistory.objects.select_related("user")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# Filter prefs / App meta / Activity / Reports
# ---------------------------------------------------------------------------


class FiltersMetaDataViewSet(viewsets.ModelViewSet):
    """One row per (user, filter_context). Upserted on create."""

    serializer_class = FiltersMetaDataSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            FiltersMetaData.objects.select_related("user")
            .filter(user=self.request.user)
            .order_by("-updated_at")
        )


class AppMetaDataViewSet(viewsets.ModelViewSet):
    """Public-readable app-level config. Admin write only."""

    queryset = AppMetaData.objects.select_related("created_by").all()
    serializer_class = AppMetaDataSerializer
    permission_classes = [IsAdminOrPublicRead]
    filterset_class = AppMetaDataFilter
    search_fields = ["key", "title", "message"]
    ordering_fields = ["priority", "created_at", "valid_from"]


class UserActivityLogViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only audit log. Users can write their own events; admin can
    read everyone's."""

    serializer_class = UserActivityLogSerializer
    filterset_class = UserActivityLogFilter

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        # Read endpoints are admin-only.
        return [permissions.IsAuthenticated(), permissions.IsAdminUser()]

    def get_queryset(self):
        return UserActivityLog.objects.select_related(
            "user", "job_listing", "biz_listing"
        ).all()

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class ListingReportViewSet(viewsets.ModelViewSet):
    """End users can create + view their own reports. Admin can review."""

    serializer_class = ListingReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = ListingReportFilter

    def get_queryset(self):
        qs = ListingReport.objects.select_related(
            "user", "reviewer", "job_listing", "biz_listing"
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in {"update", "partial_update", "destroy", "review"}:
            # Mutations after creation are admin-only.
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        report = self.get_object()
        serializer = ListingReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report.status = serializer.validated_data["status"]
        report.reviewer_notes = serializer.validated_data.get("reviewer_notes", "")
        report.reviewer = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=["status", "reviewer_notes", "reviewer", "reviewed_at", "updated_at"])
        return Response(self.get_serializer(report).data)


# ---------------------------------------------------------------------------
# OTP send / verify
# ---------------------------------------------------------------------------


class OTPSendView(APIView):
    """Issue a fresh OTP for either signup verification or password reset.

    Always returns 200 even when the email is unknown — this prevents the
    endpoint from being abused for account enumeration. The actual OTP
    is only sent if the identifier matches a registered user (signup) or
    any user (password reset).
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp_send"

    @extend_schema(request=OTPSendSerializer, responses={200: None})
    def post(self, request):
        serializer = OTPSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        purpose = serializer.validated_data["purpose"]

        user = User.objects.filter(email__iexact=identifier).first()
        # For signup verification we only send if the user exists and isn't
        # already verified. For password reset we send only if the user exists.
        if user is not None:
            details, _ = UserDetails.objects.get_or_create(user=user)
            if (
                purpose == OTPCode.Purpose.SIGNUP_VERIFY and not details.otp_verified
            ) or purpose == OTPCode.Purpose.PASSWORD_RESET:
                try:
                    _, code = issue_otp(
                        identifier=identifier, purpose=purpose, user=user
                    )
                    send_otp_email(email=identifier, code=code, purpose=purpose)
                except ValueError as exc:
                    raise ValidationError({"identifier": str(exc)})
                except Exception:  # noqa: BLE001
                    pass
        return Response({"sent": True})


class OTPVerifyView(APIView):
    """Verify a signup OTP and flip ``UserDetails.otp_verified``."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(request=OTPVerifySerializer, responses={200: None})
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        purpose = serializer.validated_data["purpose"]
        code = serializer.validated_data["code"]

        try:
            otp = consume_otp(identifier=identifier, purpose=purpose, code=code)
        except ValueError as exc:
            raise ValidationError({"code": str(exc)})

        if purpose == OTPCode.Purpose.SIGNUP_VERIFY and otp.user_id:
            UserDetails.objects.filter(user_id=otp.user_id).update(otp_verified=True)
        return Response({"verified": True})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp_send"

    @extend_schema(request=PasswordResetRequestSerializer, responses={200: None})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            try:
                _, code = issue_otp(
                    identifier=email,
                    purpose=OTPCode.Purpose.PASSWORD_RESET,
                    user=user,
                )
                send_otp_email(
                    email=email, code=code, purpose=OTPCode.Purpose.PASSWORD_RESET
                )
            except ValueError as exc:
                raise ValidationError({"email": str(exc)})
            except Exception:  # noqa: BLE001
                pass
        return Response({"sent": True})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]

        try:
            otp = consume_otp(
                identifier=email,
                purpose=OTPCode.Purpose.PASSWORD_RESET,
                code=code,
            )
        except ValueError as exc:
            raise ValidationError({"code": str(exc)})

        user = otp.user or User.objects.filter(email__iexact=email).first()
        if user is None:
            raise ValidationError({"email": "No account for this email."})
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Account lifecycle: deletion request + avatar upload + stats
# ---------------------------------------------------------------------------


class RequestAccountDeletionView(APIView):
    """Mark the account for deletion. Reversible — admin can restore by
    flipping ``account_status`` back to ``active``."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: None})
    def post(self, request):
        details, _ = UserDetails.objects.get_or_create(user=request.user)
        details.account_status = UserDetails.AccountStatus.DELETION_REQUESTED
        details.deletion_requested_at = timezone.now()
        details.save(update_fields=["account_status", "deletion_requested_at", "updated_at"])
        return Response(
            {
                "account_status": details.account_status,
                "deletion_requested_at": details.deletion_requested_at,
            }
        )


class AvatarUploadView(APIView):
    """Accept a multipart image and return the public URL.

    The file is saved under MEDIA_ROOT/avatars/{user-uid}/. In production
    swap this for a CDN upload; the response shape stays the same.
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [
        # Multipart uploads only.
        __import__("rest_framework.parsers", fromlist=["MultiPartParser"]).MultiPartParser,
        __import__("rest_framework.parsers", fromlist=["FormParser"]).FormParser,
    ]

    @extend_schema(request=AvatarUploadSerializer, responses=AvatarUploadSerializer)
    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.validated_data["image"]

        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import os

        ext = os.path.splitext(image.name)[1].lower() or ".jpg"
        path = f"avatars/{request.user.uid}{ext}"
        if default_storage.exists(path):
            default_storage.delete(path)
        saved_path = default_storage.save(path, ContentFile(image.read()))
        url = request.build_absolute_uri(default_storage.url(saved_path))

        details, _ = UserDetails.objects.get_or_create(user=request.user)
        details.profile_picture_url = url
        details.save(update_fields=["profile_picture_url", "updated_at"])

        return Response({"profile_picture_url": url})


def _profile_stats(user) -> dict:
    """Compute the stats dict surfaced on the profile screen."""
    details, _ = UserDetails.objects.get_or_create(user=user)
    thresholds = [
        (1000, UserDetails.PointsLevel.LEGEND),
        (500,  UserDetails.PointsLevel.CHAMPION),
        (100,  UserDetails.PointsLevel.CONTRIBUTOR),
        (0,    UserDetails.PointsLevel.NEWCOMER),
    ]
    pts = details.total_points
    level = details.points_level
    next_level, next_at = None, None
    # Walk thresholds in ascending order to find the next milestone.
    for threshold, name in sorted(thresholds, key=lambda t: t[0]):
        if pts < threshold:
            next_level, next_at = name, threshold
            break
    progress_pct = 100 if next_at is None else int(round(100 * pts / next_at))
    return {
        "posts": details.total_posts,
        "saved": details.total_saved,
        "upvotes_given": details.total_upvotes_given,
        "points": pts,
        "points_level": level,
        "next_level": next_level,
        "next_level_at": next_at,
        "progress_pct": progress_pct,
        "is_premium": details.is_premium,
        "premium_expires_at": details.premium_expires_at,
    }


class ProfileStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=ProfileStatsSerializer)
    def get(self, request):
        return Response(ProfileStatsSerializer(_profile_stats(request.user)).data)


# ---------------------------------------------------------------------------
# Pending-listing check
# ---------------------------------------------------------------------------


class CanSubmitListingView(APIView):
    """Plus button gate: the design blocks new submissions when the user
    has any listing still in PENDING moderation. Returns the offending
    listing so the client can render a "post under review" card."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=CanSubmitListingSerializer)
    def get(self, request):
        for model, label in ((JobListing, "job"), (BizListing, "biz")):
            pending = (
                model.objects.filter(
                    posted_by=request.user, status=ListingStatus.PENDING
                )
                .order_by("-created_at")
                .first()
            )
            if pending is not None:
                return Response(
                    {
                        "can_submit": False,
                        "pending_listing_type": label,
                        "pending_listing_uid": pending.uid,
                        "pending_title": pending.title,
                        "pending_submitted_at": pending.created_at,
                    }
                )
        return Response(
            {
                "can_submit": True,
                "pending_listing_type": None,
                "pending_listing_uid": None,
                "pending_title": None,
                "pending_submitted_at": None,
            }
        )


# ---------------------------------------------------------------------------
# Comment likes
# ---------------------------------------------------------------------------


class CommentLikeToggleView(APIView):
    """Toggle a like on a single comment. ``POST`` adds, ``DELETE`` removes."""

    permission_classes = [permissions.IsAuthenticated]

    def _get_comment(self, uid):
        try:
            return Comment.objects.get(uid=uid, is_deleted=False)
        except Comment.DoesNotExist:
            raise NotFound("Comment not found.")

    def post(self, request, uid):
        comment = self._get_comment(uid)
        _, created = CommentLike.objects.get_or_create(
            user=request.user, comment=comment
        )
        comment.refresh_from_db(fields=["likes_count"])
        return Response(
            {"liked": True, "likes_count": comment.likes_count, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, uid):
        comment = self._get_comment(uid)
        CommentLike.objects.filter(user=request.user, comment=comment).delete()
        comment.refresh_from_db(fields=["likes_count"])
        return Response(
            {"liked": False, "likes_count": comment.likes_count},
            status=status.HTTP_204_NO_CONTENT,
        )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uid"

    def get_queryset(self):
        return Notification.objects.select_related(
            "related_job_listing", "related_biz_listing", "related_comment"
        ).filter(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread": n})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, uid=None):
        notif = self.get_object()
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(notif).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({"ok": True})


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------


class StaticPageViewSet(viewsets.ModelViewSet):
    """Privacy Policy / Terms / Help / About. Slug-keyed for the client."""

    queryset = StaticPage.objects.order_by("slug")
    serializer_class = StaticPageSerializer
    permission_classes = [IsAdminOrPublicRead]
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs
        return qs.filter(is_published=True)

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user, version=1)

    def perform_update(self, serializer):
        instance = serializer.instance
        serializer.save(updated_by=self.request.user, version=instance.version + 1)


# ---------------------------------------------------------------------------
# Home feed (personalised)
# ---------------------------------------------------------------------------


class HomeFeedView(APIView):
    """Aggregates everything the home screen needs in one round-trip:
    new-listings count (matched to the user's preferences), a few
    suggested jobs, trending biz, profile stats, unread notifications."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=HomeFeedSerializer)
    def get(self, request):
        from datetime import timedelta
        from django.db.models import Q

        details, _ = UserDetails.objects.get_or_create(user=request.user)
        prefs = details.job_preferences or []

        approved_jobs = JobListing.objects.filter(
            status=ListingStatus.APPROVED, is_expired=False
        )
        if prefs:
            pref_q = Q()
            for p in prefs:
                pref_q |= Q(category__iexact=p)
            approved_jobs = approved_jobs.filter(pref_q)

        new_jobs_count = approved_jobs.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()

        suggested_jobs = list(
            approved_jobs.select_related("posted_by", "approved_by")
            .order_by("-created_at")[:5]
        )

        trending_biz = list(
            BizListing.objects.filter(
                status=ListingStatus.APPROVED, is_expired=False
            )
            .select_related("posted_by", "approved_by")
            .order_by("-upvotes_count", "-created_at")[:5]
        )

        unread = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()

        payload = {
            "new_jobs_count": new_jobs_count,
            "suggested_jobs": JobListingSerializer(suggested_jobs, many=True).data,
            "trending_biz":  BizListingSerializer(trending_biz, many=True).data,
            "unread_notifications": unread,
            "stats": _profile_stats(request.user),
        }
        return Response(payload)
