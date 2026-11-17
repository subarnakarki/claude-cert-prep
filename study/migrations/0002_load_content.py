"""Load the study content so a plain `migrate` gives a working app."""

from django.db import migrations

from study.content_loader import load


def load_content(apps, schema_editor):
    load(apps.get_model)


class Migration(migrations.Migration):
    dependencies = [("study", "0001_initial")]

    operations = [migrations.RunPython(load_content, migrations.RunPython.noop)]
