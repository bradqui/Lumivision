from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        # Existing cover images keep behaving as banners (backdrop behind the name).
        migrations.RenameField(
            model_name="board",
            old_name="cover_image",
            new_name="banner_image",
        ),
        migrations.AlterField(
            model_name="board",
            name="banner_image",
            field=models.ImageField(
                blank=True,
                help_text="Backdrop shown behind the board name",
                upload_to="covers/%Y/%m/",
            ),
        ),
        migrations.AddField(
            model_name="board",
            name="logo_image",
            field=models.ImageField(
                blank=True,
                help_text="Displayed in place of the board name, like a logo",
                upload_to="logos/%Y/%m/",
            ),
        ),
    ]
