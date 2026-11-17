from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from study.content_loader import load


class Command(BaseCommand):
    help = "Load or refresh exam content from study/content/ccarf.json (safe to re-run)."

    def handle(self, *args, **options):
        with transaction.atomic():
            counts = load(apps.get_model)
        summary = ", ".join(f"{n} {name}" for name, n in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Loaded {summary}."))
