"""Views for the buffalo data-entry page.

The page is server-rendered; htmx swaps in partials for the entry forms, the
animals table, expanded animal details, and dialogs. Every queryset is
scoped through `TribeAccess`, so a user can never read or change records for
a tribe they do not belong to.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import wraps
from typing import Any, Concatenate, cast

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.views import redirect_to_login
from django.contrib.gis.geos import Point
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Model, Prefetch, QuerySet
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    QueryDict,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_htmx.http import trigger_client_event
from simple_history.manager import HistoryManager

from buffalo import attachments
from buffalo.forms import (
    AnimalEditForm,
    AnimalIntakeForm,
    AttachmentUploadForm,
    ConditionReportEditForm,
    ConditionReportForm,
    DeathForm,
    LabForm,
    LocationForm,
    LookupForm,
    MannerOfDeathForm,
    SampleEditForm,
    SampleForm,
    SampleTypeForm,
)
from buffalo.models import (
    Animal,
    Attachment,
    ConditionReport,
    Gender,
    Sample,
    Tracked,
    Tribe,
)
from buffalo.permissions import TribeAccess

PAGE_SIZES = (10, 25, 50)


def access_for(request: HttpRequest) -> TribeAccess:
    """The current user's tribe access, computed once per request."""
    access: TribeAccess | None = getattr(request, "_tribe_access", None)
    if access is None:
        access = TribeAccess(request.user)
        setattr(request, "_tribe_access", access)  # noqa: B010
    return access


def member_required[**P, R: HttpResponseBase](
    view: Callable[Concatenate[HttpRequest, P], R],
) -> Callable[Concatenate[HttpRequest, P], R]:
    """Require a signed-in user with access to at least one tribe."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: P.args, **kwargs: P.kwargs) -> R:
        if not request.user.is_authenticated:
            return cast("R", redirect_to_login(request.get_full_path()))
        if not access_for(request).has_any_access:
            raise PermissionDenied("You do not have access to any tribe's records.")
        return view(request, *args, **kwargs)

    return wrapper


def _user(request: HttpRequest) -> AbstractBaseUser:
    # Only reachable behind @member_required, so the user is always signed in.
    if not isinstance(request.user, AbstractBaseUser):
        raise PermissionDenied
    return request.user


def _stamp(record: Tracked, request: HttpRequest) -> None:
    user = _user(request)
    if record.pk is None:
        record.created_by = user  # type: ignore[assignment]
    record.updated_by = user  # type: ignore[assignment]


def _notify(response: HttpResponse, message: str, level: str = "success") -> HttpResponse:
    return trigger_client_event(response, "notify", {"message": message, "level": level})


def _animal_updated(response: HttpResponse, animal: Animal) -> HttpResponse:
    """Tell the page to re-render this animal's row (if it is on screen)."""
    return trigger_client_event(response, f"animal-updated-{animal.pk}", {})


# ── Page ──────────────────────────────────────────────────────────────────────


@require_http_methods(["GET"])
@member_required
def index(request: HttpRequest) -> HttpResponse:
    access = access_for(request)
    tribes = access.readable_tribes()
    context: dict[str, Any] = {
        "tribes": tribes,
        "table": _table_context(request, request.GET),
        "can_edit": access.can_edit_any,
    }
    if access.can_edit_any:
        context.update(_entry_context("intake", AnimalIntakeForm(access=access)))
    return render(request, "buffalo/index.html", context)


# ── Entry forms (Intake / Condition Report / Add Sample tabs) ─────────────────


def _entry_context(tab: str, form: Any, saved: str | None = None) -> dict[str, Any]:
    return {"tab": tab, "form": form, "saved": saved}


def _render_entry(
    request: HttpRequest, tab: str, form: Any, saved: str | None = None
) -> HttpResponse:
    return render(request, "buffalo/partials/entry_panel.html", _entry_context(tab, form, saved))


@require_http_methods(["GET", "POST"])
@member_required
def entry_intake(request: HttpRequest) -> HttpResponse:
    access = access_for(request)
    access.require_edit_any()
    if request.method != "POST":
        return _render_entry(request, "intake", AnimalIntakeForm(access=access))

    form = AnimalIntakeForm(request.POST, request.FILES, access=access)
    if not form.is_valid():
        return _render_entry(request, "intake", form)

    with transaction.atomic():
        animal: Animal = form.save(commit=False)
        _stamp(animal, request)
        animal.save()
        if upload := form.cleaned_data.get("attachment"):
            attachments.create(upload, animal=animal, user=_user(request))

    response = _render_entry(
        request,
        "intake",
        AnimalIntakeForm(access=access, initial={"tribe": animal.tribe_id}),
        saved=f"Animal {animal.animal_id} registered.",
    )
    return trigger_client_event(response, "animals-changed", {"tribe": animal.tribe_id})


def _prefill_animal(request: HttpRequest, access: TribeAccess) -> dict[str, Any]:
    """Initial tribe/animal (and date) when a form is opened from an animal's row."""
    initial: dict[str, Any] = {}
    if animal_pk := request.GET.get("animal"):
        animal = get_object_or_404(access.editable_animals(), pk=animal_pk)
        initial.update(tribe=animal.tribe_id, animal=animal.pk)
    return initial


@require_http_methods(["GET", "POST"])
@member_required
def entry_condition(request: HttpRequest) -> HttpResponse:
    access = access_for(request)
    access.require_edit_any()
    if request.method != "POST":
        form = ConditionReportForm(access=access, initial=_prefill_animal(request, access))
        return _render_entry(request, "condition", form)

    form = ConditionReportForm(request.POST, request.FILES, access=access)
    if not form.is_valid():
        return _render_entry(request, "condition", form)

    with transaction.atomic():
        report: ConditionReport = form.save(commit=False)
        _stamp(report, request)
        report.save()
        if upload := form.cleaned_data.get("attachment"):
            attachments.create(
                upload, animal=report.animal, user=_user(request), condition_report=report
            )

    response = _render_entry(
        request,
        "condition",
        ConditionReportForm(access=access, initial={"tribe": report.animal.tribe_id}),
        saved=f"Condition report saved for {report.animal}.",
    )
    return _animal_updated(response, report.animal)


@require_http_methods(["GET", "POST"])
@member_required
def entry_sample(request: HttpRequest) -> HttpResponse:
    access = access_for(request)
    access.require_edit_any()
    if request.method != "POST":
        initial = _prefill_animal(request, access)
        if sample_date := request.GET.get("date"):
            initial["sample_date"] = sample_date
        return _render_entry(request, "sample", SampleForm(access=access, initial=initial))

    form = SampleForm(request.POST, request.FILES, access=access)
    if not form.is_valid():
        return _render_entry(request, "sample", form)

    with transaction.atomic():
        sample: Sample = form.save(commit=False)
        _stamp(sample, request)
        sample.save()
        if upload := form.cleaned_data.get("attachment"):
            attachments.create(upload, animal=sample.animal, user=_user(request), sample=sample)

    response = _render_entry(
        request,
        "sample",
        SampleForm(access=access, initial={"tribe": sample.animal.tribe_id}),
        saved=f"{sample.sample_type} sample saved for {sample.animal}. It is pending until "
        "results are entered.",
    )
    return _animal_updated(response, sample.animal)


@require_http_methods(["GET"])
@member_required
def animal_options(request: HttpRequest) -> HttpResponse:
    """`<option>`s for the animal (or mother) dropdown once a tribe is picked."""
    access = access_for(request)
    tribe_id = request.GET.get("tribe")
    animals = (
        access.editable_animals().filter(tribe_id=tribe_id) if tribe_id else Animal.objects.none()
    )
    female_only = request.GET.get("female") == "1"
    if female_only:
        animals = animals.filter(gender=Gender.FEMALE)
    return render(
        request,
        "buffalo/partials/animal_options.html",
        {"animals": animals, "tribe_selected": bool(tribe_id), "optional": female_only},
    )


# ── Animals table ─────────────────────────────────────────────────────────────


def _table_context(request: HttpRequest, params: QueryDict) -> dict[str, Any]:
    access = access_for(request)
    tribes = access.readable_tribes()
    tribe: Tribe | None = None
    if tribe_id := params.get("tribe"):
        tribe = get_object_or_404(tribes, pk=tribe_id)
    else:
        tribe = tribes.first()

    try:
        page_size = int(params.get("page_size", PAGE_SIZES[0]))
    except ValueError:
        page_size = PAGE_SIZES[0]
    if page_size not in PAGE_SIZES:
        page_size = PAGE_SIZES[0]

    animals = (
        Animal.objects.filter(tribe=tribe).select_related("original_location")
        if tribe
        else Animal.objects.none()
    )
    page = Paginator(animals, page_size).get_page(params.get("page"))
    return {
        "tribes": tribes,
        "tribe": tribe,
        "page": page,
        "page_size": page_size,
        "page_sizes": PAGE_SIZES,
        "can_edit_tribe": tribe is not None and access.can_edit(tribe.pk),
        "can_export_tribe": tribe is not None and access.can_export(tribe.pk),
    }


@require_http_methods(["GET"])
@member_required
def animal_table(request: HttpRequest) -> HttpResponse:
    return render(
        request, "buffalo/partials/animal_table.html", _table_context(request, request.GET)
    )


@require_http_methods(["GET"])
@member_required
def animal_row(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    animal = get_object_or_404(access.readable_animals().select_related("original_location"), pk=pk)
    return render(
        request,
        "buffalo/partials/animal_row.html",
        {
            "animal": animal,
            "expanded": request.GET.get("expanded") == "1",
            "can_edit_tribe": access.can_edit(animal.tribe_id),
        },
    )


@require_http_methods(["GET"])
@member_required
def animal_detail(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    animal = get_object_or_404(
        access.readable_animals()
        .select_related("mother", "manner_of_death")
        .prefetch_related(
            "calves",
            "condition_reports",
            Prefetch(
                "samples",
                queryset=Sample.objects.select_related("sample_type", "location", "lab"),
            ),
            "attachments",
        ),
        pk=pk,
    )

    by_condition: defaultdict[int, list[Attachment]] = defaultdict(list)
    by_sample: defaultdict[int, list[Attachment]] = defaultdict(list)
    animal_files: list[Attachment] = []
    for attachment in animal.attachments.all():
        if attachment.condition_report_id:
            by_condition[attachment.condition_report_id].append(attachment)
        elif attachment.sample_id:
            by_sample[attachment.sample_id].append(attachment)
        else:
            animal_files.append(attachment)

    return render(
        request,
        "buffalo/partials/animal_detail.html",
        {
            "animal": animal,
            "can_edit_tribe": access.can_edit(animal.tribe_id),
            "animal_files": animal_files,
            "conditions": [(c, by_condition[c.pk]) for c in animal.condition_reports.all()],
            "samples": [(s, by_sample[s.pk]) for s in animal.samples.all()],
        },
    )


# ── Dialogs ───────────────────────────────────────────────────────────────────


def _dialog(
    request: HttpRequest, title: str, form: Any, post_url: str, **extra: Any
) -> HttpResponse:
    return render(
        request,
        "buffalo/partials/form_dialog.html",
        {"title": title, "form": form, "post_url": post_url, **extra},
    )


def _dialog_saved(message: str, animal: Animal) -> HttpResponse:
    # An empty body clears the #modal container, which closes the dialog.
    return _animal_updated(_notify(HttpResponse(), message), animal)


@require_http_methods(["GET", "POST"])
@member_required
def animal_edit(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    animal = get_object_or_404(access.readable_animals(), pk=pk)
    access.require_edit(animal.tribe_id)
    form = AnimalEditForm(request.POST or None, instance=animal)
    if request.method == "POST" and form.is_valid():
        _stamp(animal, request)
        form.save()
        return _dialog_saved(f"Animal {animal} updated.", animal)
    return _dialog(request, f"Edit animal {animal}", form, request.path)


@require_http_methods(["GET", "POST"])
@member_required
def animal_death(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    animal = get_object_or_404(access.readable_animals(), pk=pk)
    access.require_edit(animal.tribe_id)
    form = DeathForm(request.POST or None, instance=animal)
    if request.method == "POST" and form.is_valid():
        _stamp(animal, request)
        form.save()
        return _dialog_saved(f"Death recorded for {animal}.", animal)
    return _dialog(request, f"Record death of {animal}", form, request.path, destructive=True)


@require_http_methods(["GET", "POST"])
@member_required
def condition_edit(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    report = get_object_or_404(
        ConditionReport.objects.filter(animal__in=access.readable_animals()).select_related(
            "animal"
        ),
        pk=pk,
    )
    access.require_edit(report.animal.tribe_id)
    form = ConditionReportEditForm(request.POST or None, instance=report)
    if request.method == "POST" and form.is_valid():
        _stamp(report, request)
        form.save()
        return _dialog_saved("Condition report updated.", report.animal)
    return _dialog(request, f"Edit condition report: {report}", form, request.path)


@require_http_methods(["GET", "POST"])
@member_required
def sample_edit(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    sample = get_object_or_404(
        Sample.objects.filter(animal__in=access.readable_animals()).select_related(
            "animal", "sample_type"
        ),
        pk=pk,
    )
    access.require_edit(sample.animal.tribe_id)
    form = SampleEditForm(request.POST or None, instance=sample)
    if request.method == "POST" and form.is_valid():
        _stamp(sample, request)
        form.save()
        return _dialog_saved("Sample updated.", sample.animal)
    return _dialog(request, f"Sample: {sample}", form, request.path)


# ── Lookups ("+ Add" next to a dropdown) ──────────────────────────────────────

LOOKUP_FORMS: dict[str, tuple[str, type[LookupForm]]] = {
    "location": ("Add location", LocationForm),
    "lab": ("Add lab", LabForm),
    "sample-type": ("Add sample type", SampleTypeForm),
    "manner-of-death": ("Add manner of death", MannerOfDeathForm),
}
_SELECT_ID = re.compile(r"^[A-Za-z][\w-]*$")


@require_http_methods(["GET", "POST"])
@member_required
def lookup_add(request: HttpRequest, kind: str) -> HttpResponse:
    access_for(request).require_edit_any()
    if kind not in LOOKUP_FORMS:
        raise Http404
    title, form_class = LOOKUP_FORMS[kind]
    target = request.GET.get("target", "")
    if not _SELECT_ID.match(target):
        raise Http404

    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        response = render(
            request, "buffalo/partials/lookup_added.html", {"item": item, "target": target}
        )
        return _notify(response, f"Added “{item}”.")
    return render(
        request,
        "buffalo/partials/lookup_dialog.html",
        {"title": title, "form": form, "post_url": request.get_full_path()},
    )


# ── Attachments ───────────────────────────────────────────────────────────────


def _render_strip(
    request: HttpRequest,
    animal: Animal,
    *,
    condition_report: ConditionReport | None = None,
    sample: Sample | None = None,
) -> HttpResponse:
    files = Attachment.objects.filter(
        animal=animal, condition_report=condition_report, sample=sample
    )
    return render(
        request,
        "buffalo/partials/attachment_strip.html",
        {
            "animal": animal,
            "files": files,
            "condition_report": condition_report,
            "sample": sample,
            "can_edit_tribe": access_for(request).can_edit(animal.tribe_id),
        },
    )


@require_http_methods(["POST"])
@member_required
def attachment_upload(request: HttpRequest, pk: int) -> HttpResponse:
    access = access_for(request)
    animal = get_object_or_404(access.readable_animals(), pk=pk)
    access.require_edit(animal.tribe_id)
    form = AttachmentUploadForm(request.POST, request.FILES, animal=animal)
    if not form.is_valid():
        response = HttpResponse(status=204)
        message = " ".join(str(e) for errors in form.errors.values() for e in errors)
        return _notify(response, f"Upload failed: {message}", level="error")

    condition_report = form.cleaned_data.get("condition_report")
    sample = form.cleaned_data.get("sample")
    attachments.create(
        form.cleaned_data["file"],
        animal=animal,
        user=_user(request),
        condition_report=condition_report,
        sample=sample,
    )
    return _render_strip(request, animal, condition_report=condition_report, sample=sample)


def _attachment_for(request: HttpRequest, pk: int) -> Attachment:
    access = access_for(request)
    return get_object_or_404(
        Attachment.objects.filter(animal__in=access.readable_animals()).select_related(
            "animal", "condition_report", "sample"
        ),
        pk=pk,
    )


@require_http_methods(["DELETE"])
@member_required
def attachment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    attachment = _attachment_for(request, pk)
    access_for(request).require_edit(attachment.animal.tribe_id)
    attachment.delete()
    return _render_strip(
        request,
        attachment.animal,
        condition_report=attachment.condition_report,
        sample=attachment.sample,
    )


@require_http_methods(["GET"])
@member_required
def attachment_download(request: HttpRequest, pk: int) -> FileResponse:
    attachment = _attachment_for(request, pk)
    # Only raster images Pillow could read (i.e. that have a thumbnail) are
    # shown inline; anything else is forced to download so an uploaded HTML or
    # SVG file can never run script on this site.
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=not attachment.thumbnail,
        filename=attachment.original_filename,
        content_type=attachment.content_type if attachment.thumbnail else None,
    )


@require_http_methods(["GET"])
@member_required
def attachment_thumbnail(request: HttpRequest, pk: int) -> FileResponse:
    attachment = _attachment_for(request, pk)
    if not attachment.thumbnail:
        raise Http404("No thumbnail is available for this file.")
    response = FileResponse(attachment.thumbnail.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=86400"
    return response


# ── Change history ────────────────────────────────────────────────────────────

HIDDEN_HISTORY_FIELDS = ["created_at", "created_by", "updated_at", "updated_by", "thumbnail"]
ACTIONS = {"+": "Created", "~": "Changed", "-": "Deleted"}


@dataclass
class HistoryEntry:
    when: datetime
    user: str
    record: str
    action: str
    changes: list[tuple[str, str, str]] = field(default_factory=list)


def _display(value: object) -> str:
    match value:
        case None | "":
            return "—"
        case bool():
            return "Yes" if value else "No"
        case Point():
            return f"{value.y:.6f}, {value.x:.6f}"
        case date():
            return f"{value:%Y-%m-%d}"
        case _:
            return str(value)


def _history_entries(
    records: Iterable[Any], model: type[Model], describe: Callable[[Any], str]
) -> Iterator[HistoryEntry]:
    labels = {
        f.name: str(f.verbose_name).capitalize()
        for f in model._meta.get_fields()
        if hasattr(f, "verbose_name")
    }
    for record in records:
        entry = HistoryEntry(
            when=record.history_date,
            user=str(record.history_user or "unknown"),
            record=describe(record),
            action=ACTIONS[record.history_type],
        )
        if record.history_type == "~" and (previous := record.prev_record):
            delta = record.diff_against(
                previous, excluded_fields=HIDDEN_HISTORY_FIELDS, foreign_keys_are_objs=True
            )
            entry.changes = [
                (labels.get(c.field, c.field), _display(c.old), _display(c.new))
                for c in delta.changes
            ]
            if not entry.changes:
                continue
        yield entry


def _history(model: type[Model]) -> HistoryManager:
    # HistoricalRecords installs the manager at runtime; type checkers only see the descriptor.
    return cast("HistoryManager", getattr(model, "history"))  # noqa: B009


@require_http_methods(["GET"])
@member_required
def animal_history(request: HttpRequest, pk: int) -> HttpResponse:
    animal = get_object_or_404(access_for(request).readable_animals(), pk=pk)

    def history(qs: QuerySet[Any]) -> QuerySet[Any]:
        return qs.select_related("history_user").order_by("history_date")

    entries = [
        *_history_entries(
            history(_history(Animal).filter(id=animal.pk)), Animal, lambda r: "Animal"
        ),
        *_history_entries(
            history(_history(ConditionReport).filter(animal_id=animal.pk)),
            ConditionReport,
            lambda r: f"Condition report {r.visit_date:%Y-%m-%d}",
        ),
        *_history_entries(
            history(_history(Sample).filter(animal_id=animal.pk).select_related("sample_type")),
            Sample,
            lambda r: f"{r.sample_type} sample {r.sample_date:%Y-%m-%d}",
        ),
        *_history_entries(
            history(_history(Attachment).filter(animal_id=animal.pk)),
            Attachment,
            lambda r: f"File “{r.original_filename}”",
        ),
    ]
    entries.sort(key=lambda e: e.when, reverse=True)
    return render(
        request, "buffalo/partials/animal_history.html", {"animal": animal, "entries": entries}
    )


# ── CSV export ────────────────────────────────────────────────────────────────

EXPORT_HEADERS = [
    "Animal ID", "Tribe", "Intake Date", "Gender", "Year Born", "Original Location",
    "Mother ID", "Status", "Date of Death", "Manner of Death",
    "Animal Created By", "Animal Created On", "Animal Last Updated By",
    "Animal Last Updated On", "Animal Comments",
    "Visit Date", "Body Score", "Weight (lbs)", "Height (in)", "Injury", "Injury Location",
    "Visit Latitude", "Visit Longitude",
    "Condition Created By", "Condition Created On", "Condition Last Updated By",
    "Condition Last Updated On", "Condition Comments",
    "Sample Date", "Sample Type", "Sample Location", "Lab", "Result Value", "Result Date",
    "Sample Latitude", "Sample Longitude",
    "Sample Created By", "Sample Created On", "Sample Last Updated By",
    "Sample Last Updated On", "Sample Comments",
]  # fmt: skip


class _Echo:
    def write(self, value: str) -> str:
        return value


def _cell(value: object) -> object:
    match value:
        case None:
            return ""
        case datetime():
            return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
        case date():
            return value.isoformat()
        case _:
            return value


def _coords(point: Point | None) -> list[object]:
    return [point.y, point.x] if point else ["", ""]


def _tracked_cols(record: Tracked) -> list[object]:
    return [record.created_by, record.created_at, record.updated_by, record.updated_at]


def _export_rows(animals: QuerySet[Animal]) -> Iterator[list[object]]:
    """One row per (animal, condition report, sample), as the original export.

    Samples are paired with the condition report taken on the same date.
    Unlike the original, samples with no same-day report are still exported.
    """
    blank_condition = [""] * 13
    blank_sample = [""] * 13
    for animal in animals:
        animal_cols: list[object] = [
            animal.animal_id, animal.tribe, animal.intake_date, animal.get_gender_display(),
            animal.year_born, animal.original_location, animal.mother,
            "Deceased" if animal.is_deceased else "Alive",
            animal.date_of_death, animal.manner_of_death,
            *_tracked_cols(animal), animal.comments,
        ]  # fmt: skip
        samples_by_date: defaultdict[date, list[Sample]] = defaultdict(list)
        for sample in animal.samples.all():
            samples_by_date[sample.sample_date].append(sample)

        def sample_cols(sample: Sample) -> list[object]:
            return [
                sample.sample_date, sample.sample_type, sample.location, sample.lab,
                sample.result_value, sample.result_date, *_coords(sample.point),
                *_tracked_cols(sample), sample.comments,
            ]  # fmt: skip

        reports = list(animal.condition_reports.all())
        if not reports and not samples_by_date:
            yield [*animal_cols, *blank_condition, *blank_sample]
        for report in reports:
            condition_cols: list[object] = [
                report.visit_date, report.body_score, report.weight, report.height,
                "Yes" if report.injury else "No", report.injury_location,
                *_coords(report.point), *_tracked_cols(report), report.comments,
            ]  # fmt: skip
            same_day = samples_by_date.pop(report.visit_date, [])
            if not same_day:
                yield [*animal_cols, *condition_cols, *blank_sample]
            for sample in same_day:
                yield [*animal_cols, *condition_cols, *sample_cols(sample)]
        for sample_date in sorted(samples_by_date, reverse=True):
            for sample in samples_by_date[sample_date]:
                yield [*animal_cols, *blank_condition, *sample_cols(sample)]


@require_http_methods(["GET"])
@member_required
def export_csv(request: HttpRequest) -> StreamingHttpResponse:
    access = access_for(request)
    tribe = get_object_or_404(access.readable_tribes(), pk=request.GET.get("tribe"))
    if not access.can_export(tribe.pk):
        raise PermissionDenied("You do not have permission to export this tribe's data.")

    user_fields = ("created_by", "updated_by")
    animals = (
        Animal.objects.filter(tribe=tribe)
        .select_related("tribe", "original_location", "mother", "manner_of_death", *user_fields)
        .prefetch_related(
            Prefetch(
                "condition_reports",
                queryset=ConditionReport.objects.select_related(*user_fields),
            ),
            Prefetch(
                "samples",
                queryset=Sample.objects.select_related(
                    "sample_type", "location", "lab", *user_fields
                ),
            ),
        )
    )
    writer = csv.writer(_Echo())
    rows = (
        writer.writerow([_cell(v) for v in row]) for row in [EXPORT_HEADERS, *_export_rows(animals)]
    )
    filename = f"buffalo-export-{tribe.name}-{timezone.localdate():%Y-%m-%d}.csv"
    return StreamingHttpResponse(
        rows,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
