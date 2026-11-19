"""The GitHub Pages export: every page is written, links respect the base path, and the
practice flow has no server dependencies left."""

import json
import re

import pytest
from django.core.management import call_command
from django.urls import get_script_prefix

from study.static_site import build, normalize_base

pytestmark = pytest.mark.django_db

BASE = "/prep/"


@pytest.fixture
def site(tmp_path):
    out = tmp_path / "site"
    written = build(out, BASE)
    return out, written


@pytest.mark.parametrize(
    ("given", "expected"),
    [("", "/"), ("/", "/"), ("/prep", "/prep/"), ("prep/", "/prep/"), (" /a/b/ ", "/a/b/")],
)
def test_normalize_base(given, expected):
    assert normalize_base(given) == expected


def test_every_page_is_written(site):
    out, _ = site
    for rel in [
        "index.html",
        "domains/index.html",
        "domains/agentic/index.html",
        "domains/tools_mcp/index.html",
        "guide/index.html",
        "rules/index.html",
        "scenarios/index.html",
        "flashcards/index.html",
        "flashcards/context/index.html",
        "plan/index.html",
        "practice/index.html",
        "practice/run/index.html",
        "practice/reset/index.html",
        "404.html",
        "content.json",
        "sw.js",
        ".nojekyll",
        "static/study/css/trace.css",
        "static/study/js/app.js",
        "static/study/manifest.webmanifest",
        "static/study/icons/icon-512.png",
        "static/study/fonts/Archivo.woff2",
    ]:
        assert (out / rel).is_file(), rel


def test_links_respect_the_base_path(site):
    out, _ = site
    for page in out.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        for url in re.findall(r'(?:href|src)="(/[^"]*)"', html):
            assert url.startswith(BASE), f"{page}: {url}"
        assert 'data-static="1"' in html
        assert f'data-base="{BASE}"' in html


def test_no_server_only_features_remain(site):
    out, _ = site
    for page in out.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert 'method="post"' not in html, page
        assert "csrfmiddlewaretoken" not in html, page
        assert "?domain=" not in re.sub(r'href="[^"]*practice/\?domain=[^"]*"', "", html), page


def test_flashcard_filters_become_pages(site, expected):
    out, _ = site
    html = (out / "flashcards" / "agentic" / "index.html").read_text(encoding="utf-8")
    assert html.count('<li class="card">') == expected.cards["agentic"]
    assert f'href="{BASE}flashcards/agentic/" aria-current="true"' in html


def test_content_json_is_codeified_and_complete(site, expected):
    out, _ = site
    data = json.loads((out / "content.json").read_text(encoding="utf-8"))
    assert [d["slug"] for d in data["domains"]] == [
        "agentic",
        "tools_mcp",
        "claude_code",
        "prompting",
        "context",
    ]
    assert sum(d["weight"] for d in data["domains"]) == 100
    assert len(data["questions"]) == expected.questions
    assert [s["number"] for s in data["scenarios"]] == [1, 2, 3, 4, 5, 6]
    assert any(q["scenario"] == 1 for q in data["questions"])
    for q in data["questions"]:
        assert any(c["correct"] for c in q["choices"])
        assert all(c["why"] for c in q["choices"])
        assert "<script" not in q["prompt"]
    assert any(
        "<code>process_refund</code>" in c["html"] for q in data["questions"] for c in q["choices"]
    )


def test_service_worker_precaches_existing_files(site):
    out, _ = site
    sw = (out / "sw.js").read_text(encoding="utf-8")
    files = json.loads(re.search(r"const FILES = (\[.*?\]);", sw).group(1))
    assert f'const BASE = "{BASE}";' in sw
    for required in ["", "practice/run/", "content.json"]:
        assert required in files
    for rel in files:
        target = out / rel / "index.html" if rel.endswith("/") or rel == "" else out / rel
        assert target.is_file(), rel


def test_service_worker_version_changes_with_content(tmp_path):
    first = build(tmp_path / "a", BASE) and (tmp_path / "a" / "sw.js").read_text()
    second = build(tmp_path / "b", "/other/") and (tmp_path / "b" / "sw.js").read_text()
    version = re.compile(r'const VERSION = "(\w+)"')
    assert version.search(first).group(1) != version.search(second).group(1)


def test_build_restores_script_prefix(tmp_path, client):
    before = get_script_prefix()
    build(tmp_path / "site", BASE)
    assert get_script_prefix() == before
    assert 'href="/domains/"' in client.get("/").content.decode()


def test_root_base(tmp_path):
    build(tmp_path / "site", "/")
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="/domains/"' in html
    assert 'data-base="/"' in html


def test_command(tmp_path, capsys):
    call_command("build_site", out=str(tmp_path / "site"), base_url="prep")
    assert "for /prep/" in capsys.readouterr().out
    assert (tmp_path / "site" / "index.html").is_file()


def test_run_page_redirects_in_server_mode(client):
    assert client.get("/practice/run/").url == "/practice/question/"


def test_server_pages_have_manifest_and_no_app_js(client):
    html = client.get("/").content.decode()
    assert "manifest.webmanifest" in html
    assert "apple-touch-icon" in html
    assert "app.js" not in html
    assert "data-static" not in html
