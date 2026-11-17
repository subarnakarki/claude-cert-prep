"""Browser smoke test: one full trip through a practice session.

Run with `pytest -m e2e` (needs `playwright install chromium`).
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect

# Playwright's sync API runs an event loop; Django's ORM guard would otherwise refuse
# the live server's database calls made from the test thread.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

pytestmark = pytest.mark.e2e


@pytest.fixture
def site(live_server, reload_content):
    # live_server uses a transactional DB that is flushed between tests, which wipes
    # the content the data migration loaded. Load it again for this test.
    reload_content()
    return live_server.url


def test_practice_session_end_to_end(site, page: Page):
    page.goto(site + "/")
    expect(page.get_by_text("$ ccarf status")).to_be_visible()

    page.get_by_role("link", name="practice", exact=True).click()
    page.get_by_label("Domain").select_option("context")
    page.get_by_role("button", name="ccarf practice").click()

    expect(page.get_by_text("domain: context")).to_be_visible()
    page.locator("label.opt").first.click()
    page.get_by_role("button", name="Check answer").click()

    result = page.locator(".result")
    expect(result).to_be_visible()
    expect(result).to_contain_text(re.compile(r"[✓✗] (correct|incorrect)"))
    expect(result).to_contain_text("answer [")
    expect(page.locator(".opt.right")).to_have_count(1)

    page.get_by_role("link", name="End session").first.click()
    expect(page.get_by_role("heading", name="Session results")).to_be_visible()
    expect(page.locator(".score")).to_contain_text("of 1 correct")


def test_flashcards_flip(site, page: Page):
    page.goto(site + "/flashcards/?domain=agentic")
    stage = page.locator(".deck .stage")
    expect(stage).to_be_visible()
    expect(page.locator("#cards")).to_be_hidden()
    expect(stage).to_have_attribute("aria-pressed", "false")
    stage.click()
    expect(stage).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".side")).to_have_text("back")
    page.get_by_role("button", name="next →").click()
    expect(page.locator(".pos")).to_contain_text("2/12")
