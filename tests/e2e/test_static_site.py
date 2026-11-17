"""The GitHub Pages build, served from a sub-path like a project page, in a real browser."""

import functools
import http.server
import re
import threading

import pytest
from playwright.sync_api import Page, expect

from study.static_site import build

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]

BASE = "/claude-cert-prep/"


@pytest.fixture
def static_site(tmp_path):
    build(tmp_path / BASE.strip("/"), BASE)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}{BASE}"
    server.shutdown()


def wait_ready(page: Page) -> None:
    page.wait_for_selector("body[data-ready]")


def test_static_practice_flow_updates_readiness(static_site, page: Page):
    page.goto(static_site)
    wait_ready(page)
    expect(page.locator("#status")).to_contain_text("mastered 0/63")
    expect(page.locator("#status")).to_contain_text('"tool_use"')

    page.get_by_role("link", name="practice", exact=True).click()
    wait_ready(page)
    page.get_by_label("Domain").select_option("context")
    page.get_by_role("button", name="ccarf practice").click()
    expect(page).to_have_url(re.compile(r"/claude-cert-prep/practice/run/$"))
    expect(page.get_by_text("domain: context")).to_be_visible()

    # Pick exactly the correct choices, read from the page's own content.json.
    correct = page.evaluate(
        """async () => {
            const data = await (await fetch(document.body.dataset.base + 'content.json')).json();
            const run = JSON.parse(localStorage.getItem('ccarf-prep:v1')).run;
            const q = data.questions.find(q => q.id === run.question_ids[0]);
            return q.choices.filter(c => c.correct).map(c => String(c.id));
        }"""
    )
    for value in correct:
        page.locator(f'input[name=choice][value="{value}"]').check(force=True)
    page.get_by_role("button", name="Check answer").click()
    expect(page.locator(".result")).to_contain_text("✓ correct")
    expect(page.locator(".opt.right")).to_have_count(len(correct))

    page.get_by_role("button", name="Next question").click()
    expect(page.locator(".prog .count")).to_have_text("2/13")
    page.locator("label.opt").first.click()
    page.get_by_role("button", name="Check answer").click()
    expect(page.locator(".result")).to_be_visible()

    page.get_by_role("link", name="End session").first.click()
    expect(page.get_by_role("heading", name="Session results")).to_be_visible()
    expect(page.locator(".score")).to_contain_text("of 2 correct")

    page.get_by_role("link", name="Back to overview").click()
    wait_ready(page)
    expect(page.locator("#status")).to_contain_text("mastered 1/63")
    expect(page.locator("[data-runs]")).to_have_text("1")


def test_static_reset_clears_progress(static_site, page: Page):
    page.goto(static_site)
    wait_ready(page)
    page.evaluate(
        "localStorage.setItem('ccarf-prep:v1', JSON.stringify({latest: {}, attempts: 3, runs: 2}))"
    )
    page.goto(static_site + "practice/reset/")
    wait_ready(page)
    expect(page.locator("[data-attempts]")).to_have_text("3 answers")
    page.get_by_role("button", name="Yes, reset progress").click()
    wait_ready(page)
    expect(page.get_by_text("Progress reset.")).to_be_visible()
    expect(page.locator("[data-runs]")).to_have_text("0")


def test_static_flashcards_and_offline(static_site, page: Page, context):
    page.goto(static_site + "flashcards/tools_mcp/")
    expect(page.locator(".deck .pos")).to_contain_text("1/11")
    page.goto(static_site)
    wait_ready(page)
    page.evaluate("navigator.serviceWorker.ready")
    page.reload()  # let the service worker control the page
    page.evaluate("navigator.serviceWorker.ready")
    context.set_offline(True)
    page.goto(static_site + "rules/")
    expect(page.get_by_role("heading", name="Decision rules")).to_be_visible()
    context.set_offline(False)
