"""Custom DRF exception handler.

Normalises every error response to:
    {"code": <http_status>, "message": <human_readable>, "errors": <field_map?>}
"""
import logging

from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.exception(
            "Unhandled exception in %s", context.get("view", "<unknown view>")
        )
        return None

    data = response.data
    payload = {"code": response.status_code}

    if isinstance(data, dict) and "detail" in data:
        payload["message"] = str(data["detail"])
    elif isinstance(data, dict):
        payload["message"] = "Validation Error"
        payload["errors"] = data
    elif isinstance(data, list):
        payload["message"] = "Validation Error"
        payload["errors"] = data
    else:
        payload["message"] = str(exc)

    response.data = payload
    return response
