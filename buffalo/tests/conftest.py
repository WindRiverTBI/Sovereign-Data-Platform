from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client
from pytest_django.fixtures import Settings

from buffalo.models import Animal, Lab, SampleType, Tribe, TribeMembership
from buffalo.tests.utils import make_member


@pytest.fixture(autouse=True)
def media_root(settings: Settings, tmp_path: Path) -> Path:
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def shoshone(db: None) -> Tribe:
    return Tribe.objects.get(name="Eastern Shoshone")


@pytest.fixture
def arapahoe(db: None) -> Tribe:
    return Tribe.objects.get(name="Northern Arapahoe")


@pytest.fixture
def blood(db: None) -> SampleType:
    return SampleType.objects.get(name="Blood")


@pytest.fixture
def lab(db: None) -> Lab:
    return Lab.objects.get(name="Wyoming Veterinary Clinic")


@pytest.fixture
def editor(shoshone: Tribe, arapahoe: Tribe) -> User:
    """Edits and exports Shoshone records; may only read Arapahoe ones."""
    user = make_member("editor", shoshone, can_edit=True, can_export=True)
    TribeMembership.objects.create(user=user, tribe=arapahoe)
    return user


@pytest.fixture
def reader(shoshone: Tribe) -> User:
    return make_member("reader", shoshone)


@pytest.fixture
def cow(shoshone: Tribe) -> Animal:
    return Animal.objects.create(
        animal_id="BUF-001", tribe=shoshone, intake_date=date(2024, 5, 1), gender="female"
    )


@pytest.fixture
def arapahoe_cow(arapahoe: Tribe) -> Animal:
    return Animal.objects.create(
        animal_id="BUF-900", tribe=arapahoe, intake_date=date(2024, 5, 1), gender="female"
    )


@pytest.fixture
def editor_client(client: Client, editor: User) -> Client:
    client.force_login(editor)
    return client


@pytest.fixture
def reader_client(client: Client, reader: User) -> Client:
    client.force_login(reader)
    return client
