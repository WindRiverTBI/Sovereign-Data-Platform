"""Domain models for buffalo records.

Translated from the `wygisc` schema used by the original ASP.NET
application. The main structural changes from that schema:

TODO: does this ID scheme make sense?
* Surrogate integer keys replace the composite `(animalid, tribe)` keys.
  Animal IDs were already required to be unique across all tribes, so
  `Animal.animal_id` is simply unique.
"""

import uuid
from pathlib import PurePath
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.db.models.functions import Lower, Upper
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from simple_history.models import HistoricalRecords

from buffalo.constraints import FieldCheckConstraint, FieldUniqueConstraint

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models.fields.related_descriptors import RelatedManager

# Year-born may be at most this many years in the past.
MAX_ANIMAL_AGE_YEARS = 25
# TODO: are these reasonable? should they be removed?
MAX_WEIGHT_LBS = 2500
MAX_HEIGHT_IN = 150


def validate_year_born(value: int) -> None:
    # Relative to today, so it can't be a database CHECK: rows would start
    # failing on their next save once they aged past the limit.
    this_year = timezone.localdate().year
    if value > this_year:
        raise ValidationError("Year born cannot be in the future.")
    if value < this_year - MAX_ANIMAL_AGE_YEARS:
        raise ValidationError(
            f"Year born cannot be more than {MAX_ANIMAL_AGE_YEARS} years ago "
            f"({this_year - MAX_ANIMAL_AGE_YEARS} or later)."
        )


# ── Lookups ───────────────────────────────────────────────────────────────────


# TODO: should these be modeled in data or should they be code for the time being?
class Lookup(models.Model):
    """A named value picked from a dropdown, managed by editors and admins."""

    name = models.CharField(max_length=200)

    class Meta:
        abstract = True
        ordering = ["name"]
        constraints = [
            FieldUniqueConstraint(
                Lower("name"),
                name="%(app_label)s_%(class)s_name_unique_ci",
                field="name",
                violation_error_message="An entry with this name already exists.",
            ),
            FieldCheckConstraint(
                condition=~Q(name=""),
                name="%(app_label)s_%(class)s_name_not_blank",
                field="name",
                violation_error_message="This field is required.",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Tribe(Lookup):
    name = models.CharField(max_length=100)


class Location(Lookup):
    point = models.PointField(srid=4326, null=True, blank=True)


class Lab(Lookup):
    pass


class SampleType(Lookup):
    name = models.CharField(max_length=100)


class MannerOfDeath(Lookup):
    class Meta(Lookup.Meta):
        verbose_name_plural = "manners of death"


class Gender(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"


# ── Access control ────────────────────────────────────────────────────────────


class TribeMembership(models.Model):
    """Grants a user access to one tribe's records.

    Membership alone grants read access. Replaces the Umbraco member groups
    (`ShoshoneReader`, `ArapahoeEditor`, `ShoshoneExport`, ...); unlike those,
    edit and export rights here are scoped to the tribe.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tribe_memberships"
    )
    tribe = models.ForeignKey(Tribe, on_delete=models.CASCADE, related_name="memberships")
    can_edit = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)

    if TYPE_CHECKING:
        tribe_id: int

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "tribe"], name="unique_tribe_membership")
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.tribe}"


# ── Records ───────────────────────────────────────────────────────────────────


class Tracked(models.Model):
    """Who created and last changed a record, and when."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# TODO: should probably review these for null/blank stuff
class Animal(Tracked):
    # TODO: is this always unique? Is it always a USDA AIN or can it be something else?
    # should we use something unique here like a UUID?
    animal_id = models.CharField(
        "animal ID",
        max_length=15,
        help_text="AIN: the 15-digit USDA eartag number, or another unique identifier.",
    )
    # TODO: name field? Do they do that?
    # Does it make sense that an animal belongs to a tribe? Or is it just that this is one tribe's
    # record of an animal?
    tribe = models.ForeignKey(Tribe, on_delete=models.PROTECT, related_name="animals")
    intake_date = models.DateField()
    # aside, but curious how this is thought about
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    year_born = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[validate_year_born]
    )
    original_location = models.ForeignKey(
        # TODO: why is this a reference like this? What does it drive?
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    mother = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calves",
        limit_choices_to={"gender": Gender.FEMALE},
    )
    date_of_death = models.DateField(null=True, blank=True)
    # TODO: if this is something that actually should be editable by admins, I wonder if there's
    # a more django-native way of expressing this kind of thing.
    manner_of_death = models.ForeignKey(
        MannerOfDeath, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    comments = models.TextField(blank=True)

    history = HistoricalRecords()

    if TYPE_CHECKING:
        # Generated by Django; declared for type checkers without a Django plugin.
        tribe_id: int
        mother_id: int | None
        manner_of_death_id: int | None
        get_gender_display: Callable[[], str]
        calves: RelatedManager[Animal]
        condition_reports: RelatedManager[ConditionReport]
        samples: RelatedManager[Sample]
        attachments: RelatedManager[Attachment]

    class Meta:
        ordering = ["animal_id"]
        constraints = [
            FieldUniqueConstraint(
                Upper("animal_id"),
                name="unique_animal_id_ci",
                field="animal_id",
                violation_error_message=(
                    "This animal ID is already registered. "
                    "Animal IDs must be unique across all tribes."
                ),
            ),
            FieldCheckConstraint(
                condition=Q(gender__in=["", *Gender.values]),
                name="animal_gender_valid",
                field="gender",
                violation_error_message="Select a valid gender.",
            ),
            FieldCheckConstraint(
                condition=Q(date_of_death__isnull=True, manner_of_death__isnull=True)
                | Q(date_of_death__isnull=False, manner_of_death__isnull=False),
                name="death_recorded_together",
                field="date_of_death",
                violation_error_message="Date and manner of death must be recorded together.",
            ),
            # Forms never include the primary key, so they skip this check;
            # clean() gives users the friendly message.
            models.CheckConstraint(condition=~Q(mother=F("pk")), name="not_own_mother"),
        ]

    def __str__(self) -> str:
        return self.animal_id

    @property
    def is_deceased(self) -> bool:
        return self.date_of_death is not None

    def clean(self) -> None:
        # Normalization, plus the rules a CHECK constraint can't express
        # because they compare this row with its mother's.
        super().clean()
        self.animal_id = self.animal_id.strip().upper()
        mother = self.mother if self.mother_id is not None else None
        if mother is None:
            return
        if self.pk is not None and mother.pk == self.pk:
            raise ValidationError({"mother": "An animal cannot be its own mother."})
        if self.tribe_id is not None and mother.tribe_id != self.tribe_id:
            raise ValidationError({"mother": "The mother must belong to the same tribe."})


class ObservationPoint(models.Model):
    """An optional GPS fix for where an observation was made."""

    point = models.PointField(
        srid=4326, # 4326 references WGS 84; decimal degrees
        null=True,
        blank=True,
        help_text="Where the animal was observed or sampled.",
    )

    class Meta:
        abstract = True


class ConditionReport(Tracked, ObservationPoint):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="condition_reports")
    visit_date = models.DateField()
    body_score = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=[(n, str(n)) for n in range(1, 6)]
    )
    weight = models.DecimalField(
        "weight (lbs)", max_digits=6, decimal_places=1, null=True, blank=True
    )
    height = models.DecimalField(
        "height (in)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    injury = models.BooleanField("injury present", default=False)
    injury_location = models.CharField(max_length=500, blank=True)
    comments = models.TextField(blank=True)

    history = HistoricalRecords()

    if TYPE_CHECKING:
        animal_id: int
        attachments: RelatedManager[Attachment]

    class Meta:
        ordering = ["-visit_date"]
        constraints = [
            # Samples are grouped under the condition report taken the same
            # day, so a second report on one date would be ambiguous.
            models.UniqueConstraint(
                fields=["animal", "visit_date"],
                name="one_condition_report_per_day",
                violation_error_message=(
                    "A condition report already exists for this animal on this date. "
                    "Edit that report instead."
                ),
            ),
            FieldCheckConstraint(
                condition=Q(body_score__isnull=True) | Q(body_score__range=(1, 5)),
                name="body_score_range",
                field="body_score",
                violation_error_message="Body score must be between 1 and 5.",
            ),
            FieldCheckConstraint(
                condition=Q(weight__isnull=True) | Q(weight__range=(0, MAX_WEIGHT_LBS)),
                name="weight_range",
                field="weight",
                violation_error_message=f"Weight must be between 0 and {MAX_WEIGHT_LBS} lbs.",
            ),
            FieldCheckConstraint(
                condition=Q(height__isnull=True) | Q(height__range=(0, MAX_HEIGHT_IN)),
                name="height_range",
                field="height",
                violation_error_message=f"Height must be between 0 and {MAX_HEIGHT_IN} inches.",
            ),
            FieldCheckConstraint(
                condition=Q(injury=False) | ~Q(injury_location=""),
                name="injury_has_location",
                field="injury_location",
                violation_error_message="Injury location is required when an injury is present.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.animal} on {self.visit_date:%Y-%m-%d}"

    def clean(self) -> None:
        # Normalization only; the rules themselves are constraints above.
        super().clean()
        self.injury_location = self.injury_location.strip() if self.injury else ""


class Sample(Tracked, ObservationPoint):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="samples")
    sample_date = models.DateField()
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    lab = models.ForeignKey(Lab, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    result_value = models.CharField(max_length=100, blank=True)
    result_date = models.DateField(null=True, blank=True)
    comments = models.TextField(blank=True)

    history = HistoricalRecords()

    if TYPE_CHECKING:
        animal_id: int
        attachments: RelatedManager[Attachment]

    class Meta:
        ordering = ["-sample_date", "sample_type__name"]

    def __str__(self) -> str:
        return f"{self.sample_type} from {self.animal} on {self.sample_date:%Y-%m-%d}"

    @property
    def is_pending(self) -> bool:
        return not self.result_value and self.result_date is None


# ── Attachments ───────────────────────────────────────────────────────────────


def attachment_upload_to(instance: Attachment, filename: str) -> str:
    animal = instance.animal
    safe_name = get_valid_filename(PurePath(filename).name)
    return (
        f"attachments/{slugify(animal.tribe.name)}/{slugify(animal.animal_id)}/"
        f"{uuid.uuid4().hex[:8]}-{safe_name}"
    )


def thumbnail_upload_to(instance: Attachment, filename: str) -> str:
    return f"thumbnails/{PurePath(instance.file.name or 'thumbnail').with_suffix('.jpg')}"


class Attachment(models.Model):
    """A file attached to an animal, or to one of its condition reports or samples."""

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="attachments")
    condition_report = models.ForeignKey(
        ConditionReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    sample = models.ForeignKey(
        Sample, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments"
    )
    file = models.FileField(upload_to=attachment_upload_to, max_length=500)
    thumbnail = models.ImageField(upload_to=thumbnail_upload_to, max_length=500, blank=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField()
    description = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="+",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    if TYPE_CHECKING:
        condition_report_id: int | None
        sample_id: int | None

    class Meta:
        ordering = ["uploaded_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(condition_report__isnull=True) | Q(sample__isnull=True),
                name="attachment_has_one_parent_record",
                violation_error_message=(
                    "Attach a file to a condition report or a sample, not both."
                ),
            )
        ]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    @property
    def extension(self) -> str:
        return PurePath(self.original_filename).suffix.lstrip(".").upper()
