"""Helpers shared by the test modules."""

import io
from typing import Any

from django.contrib.auth.models import User
from django.test import Client
from PIL import Image

from buffalo.models import Tribe, TribeMembership


def make_member(
    username: str, tribe: Tribe, *, can_edit: bool = False, can_export: bool = False
) -> User:
    user = User.objects.create_user(username, f"{username}@example.org", "pw")
    TribeMembership.objects.create(user=user, tribe=tribe, can_edit=can_edit, can_export=can_export)
    return user


def htmx_post(client: Client, url: str, data: dict[str, Any]) -> Any:
    return client.post(url, data, headers={"HX-Request": "true"})


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), "brown").save(buffer, "PNG")
    return buffer.getvalue()
