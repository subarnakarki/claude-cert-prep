"""The practice flow: setup, shuffling, server-side grading, modes, results, reset."""

import random

import pytest

from study.models import Attempt, Question
from study.practice import PracticeRun, build_run, select_pool

from .conftest import (
    answer,
    correct_ids,
    current_question,
    session_key_of,
    start_practice,
    wrong_ids,
)

pytestmark = pytest.mark.django_db


def start_with(client, question: Question):
    """Start a run that contains only `question` (via the domain filter + session edit)."""
    start_practice(client, question.domain.slug)
    session = client.session
    run = session["practice"]
    run["question_ids"] = [question.pk]
    run["pos"] = 0
    session.save()


# -- setup -----------------------------------------------------------------------------


def test_start_redirects_to_first_question(client):
    response = start_practice(client)
    assert response.status_code == 302
    assert response.url == "/practice/question/"
    run = client.session["practice"]
    assert len(run["question_ids"]) == 63
    assert client.get("/practice/question/").status_code == 200


def test_domain_filter_restricts_pool(client, domains):
    start_practice(client, "tools_mcp")
    run = client.session["practice"]
    assert len(run["question_ids"]) == 11
    assert set(
        Question.objects.filter(pk__in=run["question_ids"]).values_list("domain__slug", flat=True)
    ) == {"tools_mcp"}


def test_invalid_setup_is_rejected(client):
    assert start_practice(client, "nope").status_code == 400
    assert start_practice(client, "", "sometimes").status_code == 400


def test_quick_start_from_overview(client):
    response = client.post("/practice/start/claude_code/")
    assert response.status_code == 302
    assert len(client.session["practice"]["question_ids"]) == 14
    assert client.post("/practice/start/nope/").status_code == 404
    assert client.get("/practice/start/agentic/").status_code == 405


def test_runs_started_counter_shows_on_overview(client):
    start_practice(client)
    start_practice(client)
    assert "session 2" in client.get("/").content.decode()


def test_questions_and_choices_are_shuffled_and_persisted():
    ids = list(Question.objects.values_list("pk", flat=True))
    run = build_run(ids, rng=random.Random(1))
    assert sorted(run.question_ids) == sorted(ids)
    assert run.question_ids != ids
    shuffled = sum(
        run.choice_order[str(q.pk)] != [c.id for c in q.choices.all()]
        for q in Question.objects.prefetch_related("choices")
    )
    assert shuffled > 30
    # Round-trips through the session as JSON-friendly data
    session = {}
    run.save(session)
    assert PracticeRun.load(session) == run


def test_question_page_uses_stored_choice_order(client):
    start_practice(client)
    question = current_question(client)
    stored = client.session["practice"]["choice_order"][str(question.pk)]
    response = client.get("/practice/question/")
    shown = [o["choice"].id for o in response.context["options"]]
    assert shown == stored
    assert client.get("/practice/question/").context["options"][0]["choice"].id == stored[0]


# -- grading ---------------------------------------------------------------------------


def single_question():
    return next(q for q in Question.objects.prefetch_related("choices") if not q.is_multi)


def multi_question():
    return next(q for q in Question.objects.prefetch_related("choices") if q.is_multi)


def test_single_correct(client):
    q = single_question()
    start_with(client, q)
    response = answer(client, correct_ids(q))
    assert response.status_code == 302
    attempt = Attempt.objects.get()
    assert attempt.is_correct
    assert attempt.selected == correct_ids(q)
    assert attempt.session_key == session_key_of(client)
    html = client.get("/practice/question/").content.decode()
    assert "✓ correct" in html
    assert 'class="opt right"' in html


def test_single_wrong_shows_feedback(client):
    q = single_question()
    start_with(client, q)
    picked = wrong_ids(q)
    answer(client, picked)
    assert not Attempt.objects.get().is_correct
    response = client.get("/practice/question/")
    html = response.content.decode()
    assert "✗ incorrect" in html
    assert 'class="opt wrong"' in html
    assert 'class="opt right"' in html
    letters = {o["choice"].id: o["letter"] for o in response.context["options"]}
    assert f"you chose [{letters[picked[0]]}]" in html
    assert f"answer [{letters[correct_ids(q)[0]]}]" in html
    assert q.explanation[:30] in html


def test_multi_select_exact_match(client):
    q = multi_question()
    assert q.select_count == 2
    start_with(client, q)
    assert "Select 2" in client.get("/practice/question/").content.decode()
    assert 'type="checkbox"' in client.get("/practice/question/").content.decode()
    answer(client, correct_ids(q))
    assert Attempt.objects.get().is_correct


@pytest.mark.parametrize("variant", ["partial", "superset"])
def test_multi_select_partial_or_extra_is_wrong(client, variant):
    q = multi_question()
    start_with(client, q)
    picked = correct_ids(q)[:1] if variant == "partial" else correct_ids(q) + wrong_ids(q)
    answer(client, picked)
    assert not Attempt.objects.get().is_correct


def test_grading_is_server_side_and_rejects_foreign_choices(client):
    q = single_question()
    other = Question.objects.exclude(pk=q.pk).first()
    start_with(client, q)
    assert answer(client, correct_ids(other)).status_code == 400
    assert client.post("/practice/question/", {"choice": "x"}).status_code == 400
    assert not Attempt.objects.exists()


def test_empty_submission_shows_error(client):
    start_practice(client)
    response = client.post("/practice/question/", {})
    assert response.status_code == 400
    assert "Pick an answer first." in response.content.decode()
    assert not Attempt.objects.exists()


def test_cannot_answer_twice(client):
    q = single_question()
    start_with(client, q)
    answer(client, wrong_ids(q))
    answer(client, correct_ids(q))
    assert Attempt.objects.count() == 1
    assert not Attempt.objects.get().is_correct


# -- navigation and results ------------------------------------------------------------


def test_next_requires_an_answer_then_advances(client):
    start_practice(client, "context")
    client.post("/practice/next/")
    assert client.session["practice"]["pos"] == 0
    q = current_question(client)
    answer(client, correct_ids(q))
    client.post("/practice/next/")
    assert client.session["practice"]["pos"] == 1


def test_progress_line_marks(client):
    start_practice(client, "context")
    answer(client, correct_ids(current_question(client)))
    client.post("/practice/next/")
    answer(client, wrong_ids(current_question(client)))
    client.post("/practice/next/")
    html = client.get("/practice/question/").content.decode()
    assert '<span class="mk-ok">●</span><span class="er">●</span><span class="p">◉</span>○' in html
    assert "3/13" in html


def test_full_run_reaches_results_by_domain(client):
    start_practice(client, "context")
    n = len(client.session["practice"]["question_ids"])
    for i in range(n):
        q = current_question(client)
        answer(client, correct_ids(q) if i % 2 == 0 else wrong_ids(q))
        response = client.post("/practice/next/")
    assert response.url == "/practice/results/"
    results = client.get("/practice/results/")
    assert results.status_code == 200
    rows = results.context["domain_rows"]
    assert [r["domain"].slug for r in rows] == ["context"]
    assert rows[0]["answered"] == 13
    assert rows[0]["correct"] == 7
    assert results.context["missed"] == 6
    assert "Retry 6 missed" in results.content.decode()
    # Finished runs send the question page to results
    assert client.get("/practice/question/").url == "/practice/results/"


def test_results_score_by_domain_for_mixed_run(client):
    start_practice(client)
    for _ in range(6):
        answer(client, correct_ids(current_question(client)))
        client.post("/practice/next/")
    rows = client.get("/practice/results/").context["domain_rows"]
    assert sum(r["answered"] for r in rows) == 6
    assert [r["domain"].number for r in rows] == sorted(r["domain"].number for r in rows)


def test_retry_missed_builds_run_from_misses(client):
    start_practice(client, "context")
    missed = []
    for i in range(3):
        q = current_question(client)
        if i == 1:
            answer(client, wrong_ids(q))
            missed.append(q.pk)
        else:
            answer(client, correct_ids(q))
        client.post("/practice/next/")
    client.post("/practice/retry/")
    assert client.session["practice"]["question_ids"] == missed
    assert client.session["practice"]["mode"] == "missed"


def test_pages_without_a_run_redirect_to_setup(client):
    for url in ["/practice/question/", "/practice/results/"]:
        assert client.get(url).url == "/practice/"
    assert client.post("/practice/next/").url == "/practice/"
    assert client.post("/practice/retry/").url == "/practice/"


# -- modes -----------------------------------------------------------------------------


def test_missed_mode(client, make_attempt, domains):
    start_practice(client, "context")  # creates the session
    key = session_key_of(client)
    qs = list(domains["context"].questions.all())
    make_attempt(key, qs[0], False)
    make_attempt(key, qs[1], True)
    make_attempt(key, qs[2], True)
    make_attempt(key, qs[2], False)  # latest is wrong → counts as missed
    start_practice(client, "context", "missed")
    assert sorted(client.session["practice"]["question_ids"]) == sorted([qs[0].pk, qs[2].pk])


def test_unanswered_mode(client, make_attempt, domains):
    start_practice(client, "context")
    key = session_key_of(client)
    qs = list(domains["context"].questions.all())
    make_attempt(key, qs[0], False)
    make_attempt(key, qs[1], True)
    start_practice(client, "context", "unanswered")
    assert len(client.session["practice"]["question_ids"]) == 11
    assert qs[0].pk not in client.session["practice"]["question_ids"]


def test_empty_pool_shows_message(client):
    response = start_practice(client, "agentic", "missed")
    assert response.status_code == 200
    assert "Nothing to retry" in response.content.decode()


def test_select_pool_rejects_unknown_mode():
    with pytest.raises(ValueError, match="unknown mode"):
        select_pool(None, None, "bogus")


def test_progress_is_per_session(client):
    from django.test import Client

    q = single_question()
    start_with(client, q)
    answer(client, correct_ids(q))
    other = Client()
    start_practice(other, "agentic")
    assert other.session.session_key != client.session.session_key
    assert mastered_count(client) == 1
    assert mastered_count(other) == 0


def mastered_count(client) -> int:
    from study import progress

    return sum(r.mastered for r in progress.readiness(client.session.session_key))


# -- reset -----------------------------------------------------------------------------


def test_reset_get_confirms_without_deleting(client):
    q = single_question()
    start_with(client, q)
    answer(client, correct_ids(q))
    response = client.get("/practice/reset/")
    assert response.status_code == 200
    assert "Yes, reset progress" in response.content.decode()
    assert "deletes 1 answer" in response.content.decode()
    assert Attempt.objects.count() == 1


def test_reset_post_deletes_only_this_session(client, make_attempt):
    q = single_question()
    start_with(client, q)
    answer(client, correct_ids(q))
    make_attempt("someone-else", q, True)
    response = client.post("/practice/reset/", follow=True)
    assert response.redirect_chain[-1][0] == "/"
    assert "Progress reset." in response.content.decode()
    assert list(Attempt.objects.values_list("session_key", flat=True)) == ["someone-else"]
    assert "practice" not in client.session
    assert "session 0" in client.get("/").content.decode()
