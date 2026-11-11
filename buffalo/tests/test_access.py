"""Sign-in and tribe-scoped permissions, including gaps in the original app."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from buffalo.models import Animal, Lab

pytestmark = pytest.mark.django_db


def test_user_without_tribe_access_cannot_sign_in(client: Client) -> None:
    User.objects.create_user("outsider", password="pw")
    response = client.post(reverse("login"), {"username": "outsider", "password": "pw"})
    assert "You do not have permission to access this application" in response.text
    assert "_auth_user_id" not in client.session


def test_member_signs_in(client: Client, reader: User) -> None:
    response = client.post(reverse("login"), {"username": "reader", "password": "pw"})
    assert response.status_code == 302
    assert response["Location"] == reverse("buffalo:index")


def test_pages_require_login(client: Client) -> None:
    response = client.get(reverse("buffalo:index"))
    assert response.status_code == 302
    assert response["Location"] == f"{reverse('login')}?next=/"


def test_reader_sees_animals_but_no_entry_forms(reader_client: Client, cow: Animal) -> None:
    response = reader_client.get(reverse("buffalo:index"))
    assert "BUF-001" in response.text
    assert 'id="entry-panel"' not in response.text


def test_reader_cannot_edit(reader_client: Client, cow: Animal) -> None:
    url = reverse("buffalo:animal_edit", args=[cow.pk])
    assert reader_client.get(url).status_code == 403
    assert reader_client.post(url, {"comments": "x"}).status_code == 403


def test_edit_rights_are_per_tribe(editor_client: Client, arapahoe_cow: Animal) -> None:
    # The original app let an editor of any tribe edit every tribe they could read.
    url = reverse("buffalo:animal_edit", args=[arapahoe_cow.pk])
    assert editor_client.post(url, {"comments": "x"}).status_code == 403


def test_other_tribes_animals_are_invisible(reader_client: Client, arapahoe_cow: Animal) -> None:
    url = reverse("buffalo:animal_detail", args=[arapahoe_cow.pk])
    assert reader_client.get(url).status_code == 404


def test_reader_cannot_add_lookups(reader_client: Client) -> None:
    # The original lookup "add" endpoints had no permission check at all.
    url = reverse("buffalo:lookup_add", args=["lab"]) + "?target=id_lab"
    assert reader_client.post(url, {"name": "New Lab"}).status_code == 403
    assert not Lab.objects.filter(name="New Lab").exists()
