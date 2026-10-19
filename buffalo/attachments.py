"""Storing uploaded files and their thumbnails."""

from __future__ import annotations

import logging
import mimetypes
from io import BytesIO

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps

from buffalo.models import Animal, Attachment, ConditionReport, Sample

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (200, 200)


def create(
    upload: UploadedFile,
    *,
    animal: Animal,
    user: AbstractBaseUser,
    condition_report: ConditionReport | None = None,
    sample: Sample | None = None,
) -> Attachment:
    filename = upload.name or "upload"
    content_type = upload.content_type or mimetypes.guess_type(filename)[0] or ""
    attachment = Attachment(
        animal=animal,
        condition_report=condition_report,
        sample=sample,
        original_filename=filename,
        content_type=content_type,
        size=upload.size or 0,
        uploaded_by=user,
    )
    attachment.file.save(filename, upload, save=False)
    if attachment.is_image:
        _add_thumbnail(attachment)
    attachment.save()
    return attachment


def _add_thumbnail(attachment: Attachment) -> None:
    """Best effort: a file the browser called an image but Pillow can't read gets none."""
    try:
        with attachment.file.open("rb") as source, Image.open(source) as image:
            thumb = ImageOps.exif_transpose(image)
            thumb.thumbnail(THUMBNAIL_SIZE)
            buffer = BytesIO()
            thumb.convert("RGB").save(buffer, "JPEG", quality=80)
    except OSError, Image.DecompressionBombError, ValueError:
        logger.info("No thumbnail for attachment %s", attachment.file.name, exc_info=True)
        return
    attachment.thumbnail.save("thumbnail.jpg", ContentFile(buffer.getvalue()), save=False)
