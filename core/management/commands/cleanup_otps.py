"""Delete OTP rows that are expired or already used.

Run this on a schedule (cron, systemd timer, Celery beat). One row per
signup / password-reset request adds up quickly otherwise.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models import OTPCode


class Command(BaseCommand):
    help = "Delete expired or used OTP codes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-used-for-days",
            type=int,
            default=7,
            help="How long to keep already-used codes for audit (default: 7).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts without deleting.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        keep_used_for = timedelta(days=options["keep_used_for_days"])

        qs = OTPCode.objects.filter(
            Q(expires_at__lt=now) | Q(is_used=True, used_at__lt=now - keep_used_for)
        )
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} OTP rows.")
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} OTP rows."))
