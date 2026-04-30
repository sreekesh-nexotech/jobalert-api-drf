"""Idempotent data migration: create / promote the default administrator.

Reads DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_USERNAME / DEFAULT_ADMIN_PASSWORD
from environment. Skipped silently when DEFAULT_ADMIN_SKIP_BOOTSTRAP is set —
useful in CI or one-off contexts where the test fixtures own user creation.
"""
from decouple import config
from django.db import migrations


def create_default_admin(apps, schema_editor):
    if config("DEFAULT_ADMIN_SKIP_BOOTSTRAP", default=False, cast=bool):
        return

    User = apps.get_model("core", "User")
    UserDetails = apps.get_model("core", "UserDetails")

    email = config("DEFAULT_ADMIN_EMAIL", default="admin@jobalert.local")
    username = config("DEFAULT_ADMIN_USERNAME", default="admin")
    password = config("DEFAULT_ADMIN_PASSWORD", default="ChangeMe123!")

    if not email or not password:
        return

    # Hash via the real User model (apps.get_model returns historical models
    # without password hashing helpers).
    from django.contrib.auth.hashers import make_password

    user, created = User.objects.get_or_create(
        email=email, defaults={"username": username}
    )
    user.username = username or user.username
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    if created or not user.password:
        user.password = make_password(password)
    user.save()

    UserDetails.objects.get_or_create(user=user)


def remove_default_admin(apps, schema_editor):
    User = apps.get_model("core", "User")
    email = config("DEFAULT_ADMIN_EMAIL", default="admin@jobalert.local")
    User.objects.filter(email=email, is_superuser=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_admin, remove_default_admin),
    ]
