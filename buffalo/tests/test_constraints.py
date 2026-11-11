"""The validation rules declared as model constraints.

Each rule must hold in two places: Postgres rejects violating rows however they
are written, and forms report the violation next to the offending field.
"""

from datetime import date
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from buffalo.forms import (
    AnimalIntakeForm,
    ConditionReportEditForm,
    DeathForm,
    LabForm,
)
from buffalo.models import Animal, ConditionReport, Lab, Tribe
from buffalo.permissions import TribeAccess

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("make", "constraint"),
    [
        (
            lambda cow: ConditionReport(animal=cow, visit_date=date(2025, 1, 1), injury=True),
            "injury_has_location",
        ),
        (
            lambda cow: ConditionReport(animal=cow, visit_date=date(2025, 1, 1), weight=3000),
            "weight_range",
        ),
        (
            lambda cow: ConditionReport(animal=cow, visit_date=date(2025, 1, 1), body_score=9),
            "body_score_range",
        ),
        (
            lambda cow: Animal(
                animal_id="buf-001", tribe_id=cow.tribe_id, intake_date=date(2025, 1, 1)
            ),
            "unique_animal_id_ci",
        ),
        (
            lambda cow: Animal(
                animal_id="BUF-777",
                tribe_id=cow.tribe_id,
                intake_date=date(2025, 1, 1),
                date_of_death=date(2025, 2, 1),
            ),
            "death_recorded_together",
        ),
        (lambda cow: Lab(name="wyoming VETERINARY clinic"), "buffalo_lab_name_unique_ci"),
        (lambda cow: Lab(name=""), "buffalo_lab_name_not_blank"),
    ],
)
def test_database_rejects_rows_that_skip_validation(
    cow: Animal, make: Any, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        make(cow).save()


def test_animal_cannot_be_its_own_mother_in_the_database(cow: Animal) -> None:
    cow.mother = cow
    with pytest.raises(IntegrityError, match="not_own_mother"), transaction.atomic():
        cow.save()


def test_constraint_errors_are_reported_on_their_field(cow: Animal) -> None:
    report = ConditionReport.objects.create(animal=cow, visit_date=date(2025, 1, 1))
    form = ConditionReportEditForm(
        {"injury": "on", "injury_location": "", "weight": "3000", "body_score": ""},
        instance=report,
    )
    assert not form.is_valid()
    assert form.errors["injury_location"] == [
        "Injury location is required when an injury is present."
    ]
    assert form.errors["weight"] == ["Weight must be between 0 and 2500 lbs."]
    assert "__all__" not in form.errors


def test_duplicate_animal_id_is_reported_on_the_id_field(
    editor: Any, shoshone: Tribe, cow: Animal
) -> None:
    form = AnimalIntakeForm(
        {"tribe": shoshone.pk, "animal_id": "buf-001", "intake_date": "2025-06-01"},
        access=TribeAccess(editor),
    )
    assert not form.is_valid()
    assert form.errors["animal_id"] == [
        "This animal ID is already registered. Animal IDs must be unique across all tribes."
    ]


def test_death_needs_both_date_and_manner(cow: Animal) -> None:
    form = DeathForm({"date_of_death": "2025-07-01", "manner_of_death": ""}, instance=cow)
    assert not form.is_valid()
    assert "manner_of_death" in form.errors  # required on the form itself
    cow.refresh_from_db()
    assert cow.date_of_death is None


def test_lookup_names_are_unique_ignoring_case() -> None:
    form = LabForm({"name": "  WYOMING veterinary clinic "})
    assert not form.is_valid()
    assert form.errors["name"] == ["An entry with this name already exists."]


def test_mother_must_be_female(editor: Any, shoshone: Tribe) -> None:
    bull = Animal.objects.create(
        animal_id="BUF-100", tribe=shoshone, intake_date=date(2024, 5, 1), gender="male"
    )
    calf = Animal(animal_id="BUF-101", tribe=shoshone, intake_date=date(2025, 5, 1), mother=bull)
    with pytest.raises(ValidationError) as caught:
        calf.full_clean()
    assert "mother" in caught.value.message_dict
