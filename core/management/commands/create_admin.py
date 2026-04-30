"""Idempotent command to create / promote the default administrator account.

Reads from environment by default (DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_USERNAME,
DEFAULT_ADMIN_PASSWORD) but each can be overridden via flags.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from decouple import config

from core.models import UserDetails

User = get_user_model()


class Command(BaseCommand):
    help = "Create or promote the default admin account (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=None)
        parser.add_argument("--username", default=None)
        parser.add_argument("--password", default=None)
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress info output (e.g. when run from a migration).",
        )

    def handle(self, *args, **options):
        email = options["email"] or config(
            "DEFAULT_ADMIN_EMAIL", default="admin@jobalert.local"
        )
        username = options["username"] or config(
            "DEFAULT_ADMIN_USERNAME", default="admin"
        )
        password = options["password"] or config(
            "DEFAULT_ADMIN_PASSWORD", default="ChangeMe123!"
        )
        quiet = options["quiet"]

        if not email or not password:
            raise CommandError(
                "Email and password are required (set DEFAULT_ADMIN_EMAIL / "
                "DEFAULT_ADMIN_PASSWORD or pass --email / --password)."
            )

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": username},
        )
        # Always reaffirm admin permissions and ensure password is current.
        user.username = username or user.username
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        if created or options["password"] is not None:
            user.set_password(password)
        user.save()

        UserDetails.objects.get_or_create(user=user)

        if not quiet:
            verb = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{verb} admin account: {email}")
            )
