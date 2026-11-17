"""Capture screenshots of every page at desktop and mobile widths.

Usage (with the dev server running on the same database):

    uv run python manage.py runserver &
    uv run python scripts/screenshots.py                    # → docs/
    uv run python scripts/screenshots.py --full-page --out /tmp/shots

The script drives a real browser session, then seeds that session with a realistic
mix of answers (through the ORM) so the overview shows coloured rows, and sets up the
practice run so the feedback screenshot mirrors the approved design.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "true")
# Playwright's sync API runs an event loop in this thread; the ORM calls here are
# ordinary blocking calls in a one-off script, so Django's async guard can stand down.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

import django  # noqa: E402

django.setup()

from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from study.models import Attempt, Domain, Question  # noqa: E402

WIDTHS = {"desktop": (1400, 900), "mobile": (390, 844)}
# Mastered / attempted-but-missed per domain, chosen to show all three row colours.
SEED = {
    "agentic": (9, 2),
    "tools_mcp": (4, 3),
    "claude_code": (11, 1),
    "prompting": (8, 2),
    "context": (7, 3),
}
DESIGN_QUESTION = "refunds over $500"


def seed_progress(session_key: str) -> None:
    Attempt.objects.filter(session_key=session_key).delete()
    for slug, (right, wrong) in SEED.items():
        questions = list(Domain.objects.get(slug=slug).questions.prefetch_related("choices"))
        for i, q in enumerate(questions[: right + wrong]):
            correct = i < right
            picked = (
                sorted(q.correct_ids)
                if correct
                else [next(c.id for c in q.choices.all() if not c.is_correct)]
            )
            Attempt.objects.create(
                session_key=session_key, question=q, selected=picked, is_correct=correct
            )


def stage_design_question(session_key: str, answered: int = 4) -> None:
    """Put the design's sample question at position 5, with a red miss at position 3."""
    store = SessionStore(session_key=session_key)
    run = store["practice"]
    target = Question.objects.get(prompt__contains=DESIGN_QUESTION)
    ids = [i for i in run["question_ids"] if i != target.pk]
    run["question_ids"] = [*ids[:answered], target.pk, *ids[answered:]][:12]
    run["pos"] = answered
    run["answers"] = {
        str(qid): {"selected": [], "correct": i != 2} for i, qid in enumerate(ids[:answered])
    }
    # Order the choices like the mock-up: the "capital letters" distractor first, answer second.
    choices = list(target.choices.all())
    first = next(c for c in choices if "capital letters" in c.text)
    right = next(c for c in choices if c.is_correct)
    rest = [c.id for c in choices if c not in (first, right)]
    run["choice_order"][str(target.pk)] = [first.id, right.id, *rest]
    store["practice"] = run
    store.save()


def shot(page: Page, out: Path, name: str, full_page: bool) -> None:
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(out / f"{name}.png"), full_page=full_page)
    print("  ", out / f"{name}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    parser.add_argument("--full-page", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (width, height) in WIDTHS.items():
            print(f"{label} ({width}px)")
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            # Start a run so the browser has a session, then seed progress into it.
            page.goto(base + "/practice/")
            page.get_by_label("Domain").select_option("agentic")
            page.get_by_role("button", name="ccarf practice").click()
            session_key = next(c["value"] for c in context.cookies() if c["name"] == "sessionid")
            seed_progress(session_key)

            def capture(path: str, name: str, page=page, label=label) -> None:
                page.goto(base + path)
                shot(page, args.out, f"{name}-{label}", args.full_page)

            capture("/", "overview")
            capture("/domains/", "domains")
            capture("/domains/agentic/", "domain-detail")
            capture("/rules/", "rules")
            capture("/scenarios/", "scenarios")
            capture("/flashcards/?domain=agentic", "flashcards")
            capture("/plan/", "plan")
            capture("/practice/", "practice-setup")

            stage_design_question(session_key)
            capture("/practice/question/", "practice-question")
            page.locator("label.opt").first.click()
            page.get_by_role("button", name="Check answer").click()
            shot(page, args.out, f"practice-feedback-{label}", args.full_page)

            capture("/practice/results/", "practice-results")
            capture("/practice/reset/", "reset")
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
