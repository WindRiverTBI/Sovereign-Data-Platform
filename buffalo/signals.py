"""Keep stored files in step with the database."""

from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from buffalo.models import Attachment


@receiver(post_delete, sender=Attachment)
def delete_attachment_files(sender: type[Attachment], instance: Attachment, **kwargs: Any) -> None:
    # A receiver (rather than a delete() override) also sees cascaded deletes,
    # e.g. deleting an animal. Wait for commit so a rollback keeps the files.
    files = [field for field in (instance.file, instance.thumbnail) if field]

    def delete_files() -> None:
        for field in files:
            if field.name:
                field.storage.delete(field.name)

    transaction.on_commit(delete_files)
