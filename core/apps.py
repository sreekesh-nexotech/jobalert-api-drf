from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "JobAlert Core"

    def ready(self):
        # Side-effect import: registers signal handlers.
        from core import signals  # noqa: F401
