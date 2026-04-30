"""Shared pagination classes."""
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """Default pagination: 20 per page, client may request up to 100."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class CursorResultsSetPagination(CursorPagination):
    """Cursor pagination for activity logs / feeds — newer first."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = "-created_at"
