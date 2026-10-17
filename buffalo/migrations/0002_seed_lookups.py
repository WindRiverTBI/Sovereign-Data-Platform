"""Seed lookup values carried over from the original `wygisc` database.

The original database's four locations ("Test Location1", "Test Field 2",
...) were test data and are deliberately not carried over.
"""

from django.db import migrations

LOOKUPS = {
    "Tribe": ["Eastern Shoshone", "Northern Arapahoe"],
    "SampleType": ["Blood", "Fecal Matter", "Hair", "Nasal/Oral Swab", "Observation", "Other"],
    "Lab": ["Wyoming Veterinary Clinic"],
    "MannerOfDeath": ["Disease"],
}


def seed(apps, schema_editor):
    for model_name, names in LOOKUPS.items():
        model = apps.get_model("buffalo", model_name)
        for name in names:
            model.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("buffalo", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
