"""Create the initial admin account from environment variables (idempotent).

Used by the container entrypoint so a fresh install is immediately usable:
  LUMIVISION_ADMIN_USER / LUMIVISION_ADMIN_PASSWORD / LUMIVISION_ADMIN_EMAIL
"""

import os

from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Create the initial admin user from LUMIVISION_ADMIN_* env vars."

    def handle(self, *args, **options):
        username = os.environ.get("LUMIVISION_ADMIN_USER", "").strip()
        password = os.environ.get("LUMIVISION_ADMIN_PASSWORD", "")
        email = os.environ.get("LUMIVISION_ADMIN_EMAIL", "").strip()

        if not username or not password:
            self.stdout.write("LUMIVISION_ADMIN_USER/PASSWORD not set — skipping.")
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "role": User.Role.ADMIN},
        )
        if created:
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Admin user “{username}” created."))
        else:
            self.stdout.write(f"User “{username}” already exists — leaving untouched.")
