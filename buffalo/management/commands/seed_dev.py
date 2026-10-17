"""Create demo users and a handful of records for local development."""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from buffalo.models import (
    Animal,
    ConditionReport,
    Gender,
    Lab,
    Location,
    Sample,
    SampleType,
    Tribe,
    TribeMembership,
)

DEMO_PASSWORD = "buffalo-dev"  # noqa: S105

# username: (tribe, can_edit, can_export)
DEMO_USERS: dict[str, tuple[str, bool, bool]] = {
    "shoshone-editor": ("Eastern Shoshone", True, True),
    "shoshone-reader": ("Eastern Shoshone", False, False),
    "arapahoe-editor": ("Northern Arapahoe", True, False),
}


class Command(BaseCommand):
    help = "Create demo users (password: buffalo-dev) and sample records. DEBUG only."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Also create an 'admin' superuser with the demo password.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_dev only runs with DJANGO_DEBUG=true.")

        if options["superuser"] and not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.org", DEMO_PASSWORD)
            self.stdout.write("Created superuser admin")

        for username, (tribe_name, can_edit, can_export) in DEMO_USERS.items():
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": f"{username}@example.org"}
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            TribeMembership.objects.update_or_create(
                user=user,
                tribe=Tribe.objects.get(name=tribe_name),
                defaults={"can_edit": can_edit, "can_export": can_export},
            )
            self.stdout.write(f"User {username}: {tribe_name} edit={can_edit} export={can_export}")

        editor = User.objects.get(username="shoshone-editor")
        tribe = Tribe.objects.get(name="Eastern Shoshone")
        pasture, _ = Location.objects.get_or_create(
            name="Red Creek pasture", defaults={"point": Point(-108.95, 42.92, srid=4326)}
        )
        today = timezone.localdate()

        mother, _ = Animal.objects.get_or_create(
            animal_id="840003000000001",
            defaults={
                "tribe": tribe,
                "intake_date": today - timedelta(days=400),
                "gender": Gender.FEMALE,
                "year_born": today.year - 6,
                "original_location": pasture,
                "created_by": editor,
                "updated_by": editor,
            },
        )
        calf, _ = Animal.objects.get_or_create(
            animal_id="840003000000002",
            defaults={
                "tribe": tribe,
                "intake_date": today - timedelta(days=90),
                "gender": Gender.MALE,
                "year_born": today.year,
                "original_location": pasture,
                "mother": mother,
                "created_by": editor,
                "updated_by": editor,
            },
        )
        visit_date = today - timedelta(days=7)
        ConditionReport.objects.get_or_create(
            animal=mother,
            visit_date=visit_date,
            defaults={
                "body_score": 4,
                "weight": 1050,
                "height": 62,
                "point": Point(-108.9512, 42.9204, srid=4326),
                "created_by": editor,
                "updated_by": editor,
            },
        )
        Sample.objects.get_or_create(
            animal=mother,
            sample_date=visit_date,
            sample_type=SampleType.objects.get(name="Blood"),
            defaults={
                "location": pasture,
                "lab": Lab.objects.first(),
                "created_by": editor,
                "updated_by": editor,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded animals {mother} and {calf}."))
