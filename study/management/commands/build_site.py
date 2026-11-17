from pathlib import Path

from django.core.management.base import BaseCommand

from study.static_site import build, normalize_base


class Command(BaseCommand):
    help = "Export the site as static files for GitHub Pages (or any static host)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="_site", help="Output directory (replaced).")
        parser.add_argument(
            "--base-url",
            default="/",
            help="Path the site is served from, e.g. /claude-cert-prep/ for a project page.",
        )

    def handle(self, *args, **options):
        out = Path(options["out"])
        written = build(out, options["base_url"])
        pages = sum(1 for f in written if f.endswith(".html"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Built {pages} pages ({len(written)} files) into {out} "
                f"for {normalize_base(options['base_url'])}"
            )
        )
