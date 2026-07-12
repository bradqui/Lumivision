"""Delete files from disk when their owning rows are removed (requirement #8)."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Asset, Board


def _delete_field_file(field_file):
    if field_file:
        field_file.delete(save=False)


@receiver(post_delete, sender=Asset)
def delete_asset_files(sender, instance, **kwargs):
    _delete_field_file(instance.file)
    _delete_field_file(instance.thumb)


@receiver(post_delete, sender=Board)
def delete_board_cover(sender, instance, **kwargs):
    _delete_field_file(instance.cover_image)
