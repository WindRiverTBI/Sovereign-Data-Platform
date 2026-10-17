"""Forms for buffalo records, styled to match the shadcn components."""

from __future__ import annotations

from pathlib import PurePath
from typing import Any, ClassVar, cast

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model, QuerySet
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone

from buffalo.models import (
    Animal,
    ConditionReport,
    Gender,
    Lab,
    Location,
    MannerOfDeath,
    Sample,
    SampleType,
    Tribe,
)
from buffalo.permissions import TribeAccess

_CONTROL = (
    "w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs "
    "transition-colors placeholder:text-muted-foreground focus-visible:outline-hidden "
    "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed "
    "disabled:opacity-50 aria-invalid:border-destructive"
)
WIDGET_CLASSES: dict[str, str] = {
    "input": f"flex h-9 py-1 {_CONTROL}",
    "select": f"h-9 py-1 {_CONTROL}",
    "textarea": f"flex min-h-[60px] py-2 {_CONTROL}",
    "file": (
        f"flex h-9 py-1 {_CONTROL} file:mr-3 file:border-0 file:bg-transparent "
        "file:text-sm file:font-medium"
    ),
    "checkbox": "size-4 rounded border-input accent-primary",
}

# Executables and scripts are refused; anything else may be attached.
BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe", ".dll", ".bat", ".cmd", ".com", ".msi", ".scr",
        ".ps1", ".vbs", ".js", ".jar", ".sh", ".apk", ".msix",
    }
)  # fmt: skip


def validate_upload(file: UploadedFile) -> None:
    extension = PurePath(file.name or "").suffix.lower()
    if extension in BLOCKED_EXTENSIONS:
        raise ValidationError(f"Files of type {extension} are not allowed.")
    if file.size and file.size > settings.ATTACHMENT_MAX_BYTES:
        raise ValidationError(
            f"Files cannot be larger than {filesizeformat(settings.ATTACHMENT_MAX_BYTES)}."
        )


class StyledFormMixin(forms.BaseForm):
    """Applies the shadcn control styles to every widget and flags invalid fields."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                kind = "checkbox"
            elif isinstance(widget, forms.Select):
                kind = "select"
            elif isinstance(widget, forms.Textarea):
                kind = "textarea"
                widget.attrs["rows"] = 3  # Django defaults to 10
            elif isinstance(widget, forms.FileInput):
                kind = "file"
            else:
                kind = "input"
            widget.attrs["class"] = (
                f"{WIDGET_CLASSES[kind]} {widget.attrs.get('class', '')}".strip()
            )

    def full_clean(self) -> None:
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"


class TribeAuthenticationForm(StyledFormMixin, AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            f"Invalid username or password. Please try again or contact {settings.SUPPORT_EMAIL}."
        ),
        "no_tribe_access": (
            "You do not have permission to access this application. "
            f"Please contact {settings.SUPPORT_EMAIL}."
        ),
    }

    def confirm_login_allowed(self, user: Any) -> None:
        super().confirm_login_allowed(user)
        if not TribeAccess(user).has_any_access:
            raise ValidationError(self.error_messages["no_tribe_access"], code="no_tribe_access")


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


class PointFieldsMixin(forms.Form):
    """Optional latitude/longitude inputs backing a model's `point` field."""

    latitude = forms.FloatField(
        required=False,
        min_value=-90,
        max_value=90,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 43.0125"}),
    )
    longitude = forms.FloatField(
        required=False,
        min_value=-180,
        max_value=180,
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. -108.3801"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        point: Point | None = getattr(getattr(self, "instance", None), "point", None)
        if point is not None:
            self.initial.setdefault("latitude", point.y)
            self.initial.setdefault("longitude", point.x)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        latitude, longitude = cleaned.get("latitude"), cleaned.get("longitude")
        if (latitude is None) != (longitude is None) and not self.has_error("latitude"):
            self.add_error("latitude", "Enter both latitude and longitude, or neither.")
        elif instance := getattr(self, "instance", None):
            instance.point = None if latitude is None else Point(longitude, latitude, srid=4326)
        return cleaned


class AttachmentFieldMixin(forms.Form):
    """An optional file to attach when the record is saved."""

    attachment = forms.FileField(label="Attach file", required=False, validators=[validate_upload])


def _model_choice(form: forms.BaseForm, name: str) -> forms.ModelChoiceField:
    return cast("forms.ModelChoiceField", form.fields[name])


def _date_widget() -> forms.DateInput:
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _animal_options_attrs(*, female_only: bool = False) -> dict[str, str]:
    url = reverse("buffalo:animal_options")
    return {
        "hx-get": f"{url}?female=1" if female_only else url,
        "hx-trigger": "change",
        "hx-target": "#id_mother" if female_only else "#id_animal",
        "hx-include": "this",
    }


# ── Animals ───────────────────────────────────────────────────────────────────


class AnimalIntakeForm(StyledFormMixin, AttachmentFieldMixin, forms.ModelForm):
    class Meta:
        model = Animal
        fields = [
            "tribe",
            "animal_id",
            "intake_date",
            "gender",
            "year_born",
            "original_location",
            "mother",
            "comments",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "animal_id": forms.TextInput(attrs={"placeholder": "e.g. 840003123456789"}),
            "intake_date": _date_widget(),
            "year_born": forms.NumberInput(attrs={"placeholder": "e.g. 2019"}),
            "comments": forms.Textarea(attrs={"placeholder": "Any additional notes…"}),
        }

    def __init__(self, *args: Any, access: TribeAccess, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _model_choice(self, "tribe").queryset = access.editable_tribes()
        _preselect_only_tribe(self, access)
        self.fields["tribe"].widget.attrs.update(_animal_options_attrs(female_only=True))
        self.fields["intake_date"].initial = timezone.localdate
        self.fields["mother"].required = False
        _model_choice(self, "mother").queryset = _females_for(self, "tribe")
        self.fields["mother"].help_text = "Lists females already recorded for the selected tribe."

    def clean_animal_id(self) -> str:
        # Uniqueness is the model's case-insensitive constraint; this just tidies input.
        return self.cleaned_data["animal_id"].strip().upper()


class AnimalEditForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Animal
        fields = ["gender", "year_born", "original_location", "mother", "comments"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        animal: Animal = self.instance
        _model_choice(self, "mother").queryset = Animal.objects.filter(
            tribe_id=animal.tribe_id, gender=Gender.FEMALE
        ).exclude(pk=animal.pk)


class DeathForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Animal
        fields = ["date_of_death", "manner_of_death"]
        widgets: ClassVar[dict[str, forms.Widget]] = {"date_of_death": _date_widget()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["date_of_death"].required = True
        # The instance's empty date_of_death would otherwise win over a field initial.
        if self.instance.date_of_death is None:
            self.initial["date_of_death"] = timezone.localdate()
        self.fields["manner_of_death"].required = True


def _preselect_only_tribe(form: forms.BaseForm, access: TribeAccess) -> None:
    """Most users edit a single tribe; save them choosing it every time."""
    if "tribe" not in form.initial and len(access.editable_ids) == 1:
        (form.initial["tribe"],) = access.editable_ids


def _females_for(form: forms.BaseForm, tribe_field: str) -> QuerySet[Animal]:
    tribe_id = _selected_pk(form, tribe_field)
    if tribe_id is None:
        return Animal.objects.none()
    return Animal.objects.filter(tribe_id=tribe_id, gender=Gender.FEMALE)


def _selected_pk(form: forms.BaseForm, field_name: str) -> int | None:
    """The primary key chosen for a field, whether submitted or pre-filled."""
    raw = form.data.get(form.add_prefix(field_name)) if form.is_bound else None
    if raw is None:
        raw = form.initial.get(field_name)
    if isinstance(raw, Model):
        return raw.pk
    try:
        return int(raw) if raw not in (None, "") else None
    except TypeError, ValueError:
        return None


# ── Condition reports and samples ─────────────────────────────────────────────


class AnimalPickerMixin(forms.Form):
    """Tribe and animal dropdowns, where the tribe narrows the animal list."""

    tribe = forms.ModelChoiceField(queryset=Tribe.objects.none())

    fields: dict[str, Any]

    def setup_picker(self, access: TribeAccess) -> None:
        tribe_field = _model_choice(self, "tribe")
        tribe_field.queryset = access.editable_tribes()
        tribe_field.widget.attrs.update(_animal_options_attrs())
        _preselect_only_tribe(self, access)
        tribe_id = _selected_pk(self, "tribe")
        animals = access.editable_animals()
        _model_choice(self, "animal").queryset = (
            animals.filter(tribe_id=tribe_id) if tribe_id else animals.none()
        )


class ConditionReportForm(
    StyledFormMixin, AnimalPickerMixin, PointFieldsMixin, AttachmentFieldMixin, forms.ModelForm
):
    class Meta:
        model = ConditionReport
        fields = [
            "animal",
            "visit_date",
            "body_score",
            "weight",
            "height",
            "injury",
            "injury_location",
            "comments",
        ]
        labels: ClassVar[dict[str, str]] = {"visit_date": "Date"}
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "visit_date": _date_widget(),
            "weight": forms.NumberInput(attrs={"placeholder": "0 to 2500", "step": "1"}),
            "height": forms.NumberInput(attrs={"placeholder": "0 to 150", "step": "1"}),
            "injury": forms.CheckboxInput(attrs={"x-model": "injury"}),
            "comments": forms.Textarea(attrs={"placeholder": "Any additional notes…"}),
        }

    def __init__(self, *args: Any, access: TribeAccess, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setup_picker(access)
        self.fields["visit_date"].initial = timezone.localdate


class ConditionReportEditForm(StyledFormMixin, PointFieldsMixin, forms.ModelForm):
    class Meta:
        model = ConditionReport
        fields = ["body_score", "weight", "height", "injury", "injury_location", "comments"]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "injury": forms.CheckboxInput(attrs={"x-model": "injury"}),
        }


class SampleForm(
    StyledFormMixin, AnimalPickerMixin, PointFieldsMixin, AttachmentFieldMixin, forms.ModelForm
):
    class Meta:
        model = Sample
        fields = ["animal", "sample_date", "sample_type", "location", "lab", "comments"]
        labels: ClassVar[dict[str, str]] = {"location": "Sample location"}
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "sample_date": _date_widget(),
            "comments": forms.Textarea(attrs={"placeholder": "Any additional notes…"}),
        }

    def __init__(self, *args: Any, access: TribeAccess, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setup_picker(access)
        self.fields["sample_date"].initial = timezone.localdate


class SampleEditForm(StyledFormMixin, PointFieldsMixin, forms.ModelForm):
    class Meta:
        model = Sample
        fields = ["location", "lab", "result_value", "result_date", "comments"]
        labels: ClassVar[dict[str, str]] = {"location": "Sample location"}
        widgets: ClassVar[dict[str, forms.Widget]] = {"result_date": _date_widget()}


# ── Attachments ───────────────────────────────────────────────────────────────


class AttachmentUploadForm(StyledFormMixin, forms.Form):
    file = forms.FileField(validators=[validate_upload])
    condition_report = forms.ModelChoiceField(
        queryset=ConditionReport.objects.none(), required=False, widget=forms.HiddenInput
    )
    sample = forms.ModelChoiceField(
        queryset=Sample.objects.none(), required=False, widget=forms.HiddenInput
    )

    def __init__(self, *args: Any, animal: Animal, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _model_choice(self, "condition_report").queryset = animal.condition_reports.all()
        _model_choice(self, "sample").queryset = animal.samples.all()

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if cleaned.get("condition_report") and cleaned.get("sample"):
            raise ValidationError("Attach a file to a condition report or a sample, not both.")
        return cleaned


# ── Lookups ───────────────────────────────────────────────────────────────────


class LookupForm(StyledFormMixin, forms.ModelForm):
    """The form field strips names; model constraints reject blanks and duplicates."""


class LocationForm(LookupForm, PointFieldsMixin):
    class Meta:
        model = Location
        fields = ["name"]
        labels: ClassVar[dict[str, str]] = {"name": "Location name"}


class LabForm(LookupForm):
    class Meta:
        model = Lab
        fields = ["name"]
        labels: ClassVar[dict[str, str]] = {"name": "Lab name"}


class SampleTypeForm(LookupForm):
    class Meta:
        model = SampleType
        fields = ["name"]
        labels: ClassVar[dict[str, str]] = {"name": "Sample type"}


class MannerOfDeathForm(LookupForm):
    class Meta:
        model = MannerOfDeath
        fields = ["name"]
        labels: ClassVar[dict[str, str]] = {"name": "Manner of death"}
