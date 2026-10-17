from typing import Any, ClassVar

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.contrib.gis.admin import GISModelAdmin
from django.db.models import Model
from django.http import HttpRequest
from simple_history.admin import SimpleHistoryAdmin

from buffalo.models import (
    Animal,
    Attachment,
    ConditionReport,
    Lab,
    Location,
    MannerOfDeath,
    Sample,
    SampleType,
    Tracked,
    Tribe,
    TribeMembership,
)

# ── Users and tribe access ────────────────────────────────────────────────────


class TribeMembershipInline(admin.TabularInline):
    model = TribeMembership
    extra = 1
    verbose_name = "tribe access"
    verbose_name_plural = "tribe access (membership grants read access)"


admin.site.unregister(User)


@admin.register(User)
class BuffaloUserAdmin(UserAdmin):
    inlines: ClassVar = [TribeMembershipInline]
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff")


# ── Lookups ───────────────────────────────────────────────────────────────────


@admin.register(Tribe, Lab, SampleType, MannerOfDeath)
class LookupAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Location)
class LocationAdmin(GISModelAdmin):
    list_display = ("name", "point")
    search_fields = ("name",)


# ── Records ───────────────────────────────────────────────────────────────────

TRACKED_FIELDS = ("created_by", "created_at", "updated_by", "updated_at")


class TrackedAdmin(SimpleHistoryAdmin, GISModelAdmin):
    readonly_fields = TRACKED_FIELDS

    def save_model(self, request: HttpRequest, obj: Tracked, form: Any, change: bool) -> None:
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = (
        "original_filename",
        "file",
        "condition_report",
        "sample",
        "uploaded_by",
        "uploaded_at",
    )
    readonly_fields = ("original_filename", "file", "uploaded_by", "uploaded_at")
    can_delete = True

    def has_add_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        # Uploads go through the app so thumbnails and metadata are filled in.
        return False


@admin.register(Animal)
class AnimalAdmin(TrackedAdmin):
    list_display = ("animal_id", "tribe", "gender", "year_born", "intake_date", "date_of_death")
    list_filter = ("tribe", "gender", "original_location")
    search_fields = ("animal_id", "comments")
    date_hierarchy = "intake_date"
    autocomplete_fields = ("mother",)
    inlines: ClassVar = [AttachmentInline]


@admin.register(ConditionReport)
class ConditionReportAdmin(TrackedAdmin):
    list_display = ("animal", "visit_date", "body_score", "weight", "height", "injury")
    list_filter = ("animal__tribe", "injury", "body_score")
    search_fields = ("animal__animal_id", "comments")
    date_hierarchy = "visit_date"
    autocomplete_fields = ("animal",)


@admin.register(Sample)
class SampleAdmin(TrackedAdmin):
    list_display = ("animal", "sample_date", "sample_type", "lab", "result_value", "result_date")
    list_filter = ("animal__tribe", "sample_type", "lab")
    search_fields = ("animal__animal_id", "result_value", "comments")
    date_hierarchy = "sample_date"
    autocomplete_fields = ("animal",)


@admin.register(Attachment)
class AttachmentAdmin(SimpleHistoryAdmin):
    list_display = (
        "original_filename",
        "animal",
        "content_type",
        "size",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("animal__tribe",)
    search_fields = ("original_filename", "animal__animal_id", "description")
    readonly_fields = ("thumbnail", "content_type", "size", "uploaded_by", "uploaded_at")
    autocomplete_fields = ("animal",)
