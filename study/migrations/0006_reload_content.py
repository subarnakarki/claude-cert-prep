"""Reload the study content after the question bank was rewritten in exam style.

Longer scenario stems, plausible distractors and a per-choice `why`. Question orders are
unchanged, so existing Attempts (progress) are kept.
"""

from django.db import migrations

from study.content_loader import load


def reload_content(apps, schema_editor):
    load(apps.get_model)


class Migration(migrations.Migration):
    dependencies = [("study", "0005_choice_why")]

    operations = [migrations.RunPython(reload_content, migrations.RunPython.noop)]
