import csv
import io
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import StreamingHttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from buffalo.models import (
    Animal,
    Attachment,
    ConditionReport,
    Gender,
    Lab,
    MannerOfDeath,
    Sample,
    SampleType,
    Tribe,
)
from buffalo.tests.utils import htmx_post, make_member, png_bytes

pytestmark = pytest.mark.django_db


# ── Intake ────────────────────────────────────────────────────────────────────


@pytest.fixture
def intake(editor_client: Client, shoshone: Tribe) -> Any:
    def post(**overrides: object) -> Any:
        data: dict[str, Any] = {
            "tribe": shoshone.pk,
            "animal_id": " buf-002 ",
            "intake_date": "2025-06-01",
        }
        return htmx_post(editor_client, reverse("buffalo:entry_intake"), data | overrides)

    return post


def test_intake_registers_animal_with_normalised_id(intake: Any, cow: Animal, editor: User) -> None:
    response = intake(mother=cow.pk, gender=Gender.MALE)
    assert "Animal BUF-002 registered." in response.text
    calf = Animal.objects.get(animal_id="BUF-002")
    assert calf.mother == cow
    assert calf.created_by == editor
    assert "animals-changed" in response["HX-Trigger"]


def test_animal_ids_are_unique_across_tribes(intake: Any, arapahoe_cow: Animal) -> None:
    assert "already registered" in intake(animal_id="buf-900").text


def test_year_born_limits(intake: Any) -> None:
    this_year = timezone.localdate().year
    assert "cannot be in the future" in intake(year_born=this_year + 1).text
    assert "more than 25 years ago" in intake(year_born=this_year - 26).text


def test_mother_must_belong_to_the_same_tribe(intake: Any, arapahoe_cow: Animal) -> None:
    assert "Select a valid choice" in intake(mother=arapahoe_cow.pk).text
    assert not Animal.objects.filter(animal_id="BUF-002").exists()


def test_cannot_register_into_read_only_tribe(intake: Any, arapahoe: Tribe) -> None:
    assert "Select a valid choice" in intake(tribe=arapahoe.pk).text


def test_intake_with_image_attachment_gets_thumbnail(intake: Any) -> None:
    intake(attachment=SimpleUploadedFile("photo.png", png_bytes(), content_type="image/png"))
    attachment = Attachment.objects.get()
    assert attachment.animal.animal_id == "BUF-002"
    with Image.open(attachment.thumbnail.path) as thumb:
        assert max(thumb.size) <= 200


# ── Condition reports and samples ─────────────────────────────────────────────


def test_condition_report_with_location(
    editor_client: Client, shoshone: Tribe, cow: Animal
) -> None:
    response = htmx_post(
        editor_client,
        reverse("buffalo:entry_condition"),
        {
            "tribe": shoshone.pk,
            "animal": cow.pk,
            "visit_date": "2025-06-01",
            "body_score": 3,
            "weight": "1100",
            "latitude": "42.92",
            "longitude": "-108.95",
        },
    )
    assert "Condition report saved" in response.text
    point = ConditionReport.objects.get().point
    assert point is not None
    assert (point.y, point.x) == pytest.approx((42.92, -108.95))
    assert response["HX-Trigger"] == f'{{"animal-updated-{cow.pk}": {{}}}}'


def test_injury_requires_location_and_limits_apply(
    editor_client: Client, shoshone: Tribe, cow: Animal
) -> None:
    response = htmx_post(
        editor_client,
        reverse("buffalo:entry_condition"),
        {
            "tribe": shoshone.pk,
            "animal": cow.pk,
            "visit_date": "2025-06-01",
            "weight": "3000",
            "injury": "on",
        },
    )
    assert "Injury location is required" in response.text
    assert "Weight must be between 0 and 2500 lbs." in response.text
    assert not ConditionReport.objects.exists()


def test_one_condition_report_per_day(editor_client: Client, shoshone: Tribe, cow: Animal) -> None:
    ConditionReport.objects.create(animal=cow, visit_date=date(2025, 6, 1))
    response = htmx_post(
        editor_client,
        reverse("buffalo:entry_condition"),
        {"tribe": shoshone.pk, "animal": cow.pk, "visit_date": "2025-06-01"},
    )
    assert "already exists for this animal on this date" in response.text


def test_cannot_pick_animal_from_another_tribe(
    editor_client: Client, shoshone: Tribe, arapahoe_cow: Animal, blood: SampleType
) -> None:
    response = htmx_post(
        editor_client,
        reverse("buffalo:entry_sample"),
        {
            "tribe": shoshone.pk,
            "animal": arapahoe_cow.pk,
            "sample_date": "2025-06-01",
            "sample_type": blood.pk,
        },
    )
    assert "Select a valid choice" in response.text


def test_enter_sample_result(
    editor_client: Client, editor: User, cow: Animal, blood: SampleType, lab: Lab
) -> None:
    sample = Sample.objects.create(animal=cow, sample_date=date(2025, 6, 1), sample_type=blood)
    assert sample.is_pending
    response = htmx_post(
        editor_client,
        reverse("buffalo:sample_edit", args=[sample.pk]),
        {"result_value": "Negative", "result_date": "2025-06-10", "lab": lab.pk},
    )
    assert response.content == b""  # clears the dialog
    sample.refresh_from_db()
    assert not sample.is_pending
    assert sample.updated_by == editor


def test_record_death(editor_client: Client, cow: Animal) -> None:
    disease = MannerOfDeath.objects.get(name="Disease")
    htmx_post(
        editor_client,
        reverse("buffalo:animal_death", args=[cow.pk]),
        {"date_of_death": "2025-07-01", "manner_of_death": disease.pk},
    )
    cow.refresh_from_db()
    assert cow.is_deceased


# ── Attachments ───────────────────────────────────────────────────────────────


def upload(client: Client, animal: Animal, name: str, content: bytes, content_type: str) -> Any:
    return htmx_post(
        client,
        reverse("buffalo:attachment_upload", args=[animal.pk]),
        {"file": SimpleUploadedFile(name, content, content_type=content_type)},
    )


def test_blocked_extension_is_refused(editor_client: Client, cow: Animal) -> None:
    response = upload(editor_client, cow, "evil.exe", b"MZ", "application/octet-stream")
    assert response.status_code == 204
    assert "not allowed" in response["HX-Trigger"]
    assert not Attachment.objects.exists()


def test_html_is_always_downloaded_not_rendered(editor_client: Client, cow: Animal) -> None:
    upload(editor_client, cow, "notes.html", b"<script>alert(1)</script>", "text/html")
    attachment = Attachment.objects.get()
    response = editor_client.get(reverse("buffalo:attachment_download", args=[attachment.pk]))
    assert response["Content-Disposition"].startswith("attachment")


def test_delete_removes_stored_files(
    editor_client: Client, cow: Animal, django_capture_on_commit_callbacks: Any
) -> None:
    upload(editor_client, cow, "photo.png", png_bytes(), "image/png")
    attachment = Attachment.objects.get()
    paths = [Path(attachment.file.path), Path(attachment.thumbnail.path)]
    with django_capture_on_commit_callbacks(execute=True):
        response = editor_client.delete(reverse("buffalo:attachment_delete", args=[attachment.pk]))
    assert response.status_code == 200
    assert not any(path.exists() for path in paths)


def test_other_tribes_cannot_download_files(
    editor_client: Client, client: Client, cow: Animal, arapahoe: Tribe
) -> None:
    upload(editor_client, cow, "a.txt", b"hello", "text/plain")
    attachment = Attachment.objects.get()
    client.force_login(make_member("arapahoe-only", arapahoe))
    response = client.get(reverse("buffalo:attachment_download", args=[attachment.pk]))
    assert response.status_code == 404


# ── Export ────────────────────────────────────────────────────────────────────


def test_export_requires_export_permission(reader_client: Client, shoshone: Tribe) -> None:
    response = reader_client.get(reverse("buffalo:export_csv"), {"tribe": shoshone.pk})
    assert response.status_code == 403


def test_export_pairs_samples_with_same_day_reports(
    editor_client: Client, shoshone: Tribe, cow: Animal, blood: SampleType
) -> None:
    day = date(2025, 6, 1)
    ConditionReport.objects.create(animal=cow, visit_date=day, body_score=4)
    Sample.objects.create(animal=cow, sample_date=day, sample_type=blood)
    # No condition report that day; the original export silently dropped these.
    Sample.objects.create(animal=cow, sample_date=day + timedelta(days=3), sample_type=blood)

    response = editor_client.get(reverse("buffalo:export_csv"), {"tribe": shoshone.pk})
    body = cast("StreamingHttpResponse", response).getvalue().decode()
    rows = list(csv.DictReader(io.StringIO(body)))
    assert [(r["Visit Date"], r["Sample Date"]) for r in rows] == [
        ("2025-06-01", "2025-06-01"),
        ("", "2025-06-04"),
    ]
    assert rows[0]["Sample Type"] == "Blood"


# ── History and lookups ───────────────────────────────────────────────────────


def test_history_lists_field_changes(editor_client: Client, cow: Animal) -> None:
    htmx_post(
        editor_client,
        reverse("buffalo:animal_edit", args=[cow.pk]),
        {"gender": Gender.FEMALE, "comments": "Limping"},
    )
    response = editor_client.get(reverse("buffalo:animal_history", args=[cow.pk]))
    assert "Limping" in response.text
    assert "editor" in response.text


def test_add_location_appends_selected_option(editor_client: Client) -> None:
    url = reverse("buffalo:lookup_add", args=["location"]) + "?target=id_location"
    response = htmx_post(
        editor_client, url, {"name": "North Pasture", "latitude": "43", "longitude": "-108.5"}
    )
    assert 'hx-swap-oob="beforeend:#id_location"' in response.text
    assert "selected>North Pasture</option>" in response.text


def test_lookup_rejects_duplicates_and_bad_targets(editor_client: Client) -> None:
    url = reverse("buffalo:lookup_add", args=["lab"])
    response = htmx_post(
        editor_client, url + "?target=id_lab", {"name": "wyoming veterinary clinic"}
    )
    assert "already exists" in response.text
    assert editor_client.get(url + "?target=<script>").status_code == 404
