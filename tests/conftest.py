import pytest
from django.apps import apps

from study.content_loader import load, read_content
from study.models import Attempt, Domain, Question


@pytest.fixture(scope="session")
def content() -> dict:
    """The raw JSON content file."""
    return read_content()


@pytest.fixture
def domains(db) -> dict[str, Domain]:
    """Content is loaded by the 0002 data migration, so it's already in the test DB."""
    return {d.slug: d for d in Domain.objects.all()}


@pytest.fixture
def make_attempt(db):
    """Record an attempt for `question` with the given correctness."""

    def _make(session_key: str, question: Question, correct: bool) -> Attempt:
        choices = list(question.choices.all())
        picked = [c.id for c in choices if c.is_correct == correct][:1] or [choices[0].id]
        return Attempt.objects.create(
            session_key=session_key, question=question, selected=picked, is_correct=correct
        )

    return _make


@pytest.fixture
def reload_content(db):
    """Load content again (used where a test flushes the DB, e.g. transactional tests)."""
    return lambda data=None: load(apps.get_model, data)


def session_key_of(client) -> str:
    return client.session.session_key


def start_practice(client, domain: str = "", mode: str = "all"):
    return client.post("/practice/start/", {"domain": domain, "mode": mode})


def current_question(client) -> Question:
    run = client.session["practice"]
    return Question.objects.get(pk=run["question_ids"][run["pos"]])


def answer(client, choice_ids):
    return client.post("/practice/question/", {"choice": [str(i) for i in choice_ids]})


def correct_ids(question: Question) -> list[int]:
    return sorted(question.correct_ids)


def wrong_ids(question: Question) -> list[int]:
    return [c.id for c in question.choices.all() if not c.is_correct][:1]
