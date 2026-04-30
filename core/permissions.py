"""Custom DRF permissions for the core app."""
from rest_framework import permissions

SAFE_METHODS = permissions.SAFE_METHODS


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Read for any authenticated user; write only by the resource owner.

    Looks up ownership through one of: ``user``, ``posted_by``, ``uploaded_by``
    on the object, in that order.
    """

    owner_attrs = ("user", "posted_by", "uploaded_by", "created_by")

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        for attr in self.owner_attrs:
            owner = getattr(obj, attr, None)
            if owner is not None:
                return owner == request.user
        return False


class IsOwnerOrAdmin(permissions.BasePermission):
    """Read+write only by the owner or staff/admin."""

    owner_attrs = ("user", "posted_by", "uploaded_by", "created_by")

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        for attr in self.owner_attrs:
            owner = getattr(obj, attr, None)
            if owner is not None:
                return owner == request.user
        return False


class IsAdminOrReadOnly(permissions.BasePermission):
    """Read for any authenticated user; write only by admin/staff."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return bool(request.user and request.user.is_staff)


class IsAdminOrPublicRead(permissions.BasePermission):
    """Read for anyone (incl. anon); write only by admin/staff.

    Used for public app metadata (announcements, banners).
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)
