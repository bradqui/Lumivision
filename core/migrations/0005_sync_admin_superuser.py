"""Repair accounts promoted to Admin before superuser syncing existed:
they received is_staff (Django-admin login) but no model permissions."""

from django.db import migrations


def grant_superuser_to_admins(apps, schema_editor):
    User = apps.get_model("core", "User")
    User.objects.filter(role="admin").update(is_staff=True, is_superuser=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_board_theme_user_theme"),
    ]

    operations = [
        migrations.RunPython(grant_superuser_to_admins, noop),
    ]
