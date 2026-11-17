"""Reload the study content after Question.scenario was added.

Fills in scenario tags and adds the new questions and flashcards on existing databases
(the Docker entrypoint only runs `migrate`). The loader is idempotent and keeps Attempts.
"""

from django.db import migrations

from study.content_loader import load


def reload_content(apps, schema_editor):
    load(apps.get_model)


class Migration(migrations.Migration):
    dependencies = [("study", "0003_question_scenario")]

    operations = [migrations.RunPython(reload_content, migrations.RunPython.noop)]
