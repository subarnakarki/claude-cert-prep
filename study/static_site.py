"""Export the app as a static site (for GitHub Pages or any static host).

Every page is rendered through Django's test client with `STATIC_SITE=True`, so the
static build uses the same templates, CSS and content as the server app. In that mode
templates swap their POST forms for buttons that `app.js` handles, and the practice
flow runs in the browser against `content.json`, with progress in localStorage.

The build also writes a service worker that precaches every file, so the site works
offline once it's been opened (and installed to a home screen) on a phone.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.test import Client, override_settings
from django.urls import get_script_prefix, set_script_prefix

from .models import Domain, Question, Scenario
from .templatetags.study_tags import codeify

STATIC_SOURCE = Path(__file__).resolve().parent / "static"
SW_TEMPLATE = Path(__file__).resolve().parent / "sw_template.js"

# The filter links (`flashcards/?domain=x`) become real pages, so they work without JS
# on a host that ignores query strings.
FLASHCARD_QUERY = re.compile(r'(href="[^"]*flashcards/)\?domain=([\w-]+)"')


def normalize_base(base_url: str) -> str:
    """'/claude-cert-prep' or 'claude-cert-prep/' → '/claude-cert-prep/'; '' → '/'."""
    stripped = base_url.strip().strip("/")
    return f"/{stripped}/" if stripped else "/"


def page_paths() -> list[str]:
    """Every server-rendered page, as a path relative to the site root."""
    slugs = list(Domain.objects.values_list("slug", flat=True))
    return [
        "",
        "domains/",
        *[f"domains/{slug}/" for slug in slugs],
        "rules/",
        "scenarios/",
        "flashcards/",
        "plan/",
        "practice/",
        "practice/run/",
        "practice/reset/",
    ]


def content_payload() -> dict:
    """Questions for app.js, with prompt/choice/explanation HTML already codeified."""
    domains = [
        {
            "slug": d.slug,
            "name": d.name,
            "short_name": d.short_name,
            "number": d.number,
            "weight": d.weight,
        }
        for d in Domain.objects.all()
    ]
    scenarios = [{"number": s.number, "title": s.title} for s in Scenario.objects.all()]
    questions = [
        {
            "id": q.pk,
            "domain": q.domain.slug,
            "scenario": q.scenario.number if q.scenario else None,
            "prompt": str(codeify(q.prompt)),
            "explanation": str(codeify(q.explanation)),
            "choices": [
                {"id": c.pk, "html": str(codeify(c.text)), "correct": c.is_correct}
                for c in q.choices.all()
            ],
        }
        for q in Question.objects.select_related("domain", "scenario").prefetch_related("choices")
    ]
    return {"domains": domains, "scenarios": scenarios, "questions": questions}


def build(out: Path, base_url: str = "/") -> list[str]:
    """Write the site to `out` (replacing it). Returns the site-relative paths written."""
    base = normalize_base(base_url)
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: list[str] = []

    def write(rel: str, data: str | bytes) -> None:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            target.write_text(data, encoding="utf-8")
        else:
            target.write_bytes(data)
        written.append(rel)

    overrides = {
        "STATIC_SITE": True,
        "DEBUG": False,
        "FORCE_SCRIPT_NAME": base.rstrip("/") or None,
        "ALLOWED_HOSTS": ["testserver"],
        "STORAGES": {
            **settings.STORAGES,
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    }
    # The test client (unlike the WSGI handler) doesn't set the script prefix that
    # reverse() and {% static %} use, so set it for the build and restore it after.
    previous_prefix = get_script_prefix()
    set_script_prefix(base)
    try:
        with override_settings(**overrides):
            _render_pages(write)
    finally:
        set_script_prefix(previous_prefix)

    write("content.json", json.dumps(content_payload(), ensure_ascii=False, separators=(",", ":")))
    write(".nojekyll", "")

    for source in sorted(STATIC_SOURCE.rglob("*")):
        if source.is_file():
            write(f"static/{source.relative_to(STATIC_SOURCE).as_posix()}", source.read_bytes())

    write("sw.js", _service_worker(out, base, written))
    return written


def _render_pages(write) -> None:
    client = Client()
    slugs = list(Domain.objects.values_list("slug", flat=True))
    pages = [(path, path) for path in page_paths()]
    pages += [(f"flashcards/?domain={slug}", f"flashcards/{slug}/") for slug in slugs]
    for url, rel_dir in pages:
        response = client.get("/" + url)
        if response.status_code != 200:
            raise RuntimeError(f"/{url} returned {response.status_code}")
        write(f"{rel_dir}index.html", _postprocess(response.content.decode()))
    missing = client.get("/__static-build-404__/")
    write("404.html", _postprocess(missing.content.decode()))


def _postprocess(html: str) -> str:
    return FLASHCARD_QUERY.sub(r'\1\2/"', html)


def _service_worker(out: Path, base: str, files: list[str]) -> str:
    # Pages are cached by their directory URL (how links point at them).
    precache = sorted(f.removesuffix("index.html") for f in files if f not in {".nojekyll"})
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(rel.encode())
        digest.update((out / rel).read_bytes())
    version = digest.hexdigest()[:12]
    template = SW_TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("__VERSION__", version)
        .replace("__BASE__", base)
        .replace("__FILES__", json.dumps(precache))
    )
