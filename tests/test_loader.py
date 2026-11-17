"""The loader is idempotent, keeps progress, and mirrors edits to the JSON."""

import copy
from io import StringIO

import pytest
from django.core.management import call_command

from study.models import (
    Attempt,
    Choice,
    DecisionRule,
    Domain,
    Flashcard,
    Question,
    Scenario,
    TaskStatement,
)

pytestmark = pytest.mark.django_db

MODELS = [Domain, TaskStatement, DecisionRule, Scenario, Flashcard, Question, Choice]


def counts():
    return {m.__name__: m.objects.count() for m in MODELS}


def test_reload_is_idempotent(reload_content):
    before = counts()
    ids_before = sorted(Question.objects.values_list("pk", flat=True))
    reload_content()
    reload_content()
    assert counts() == before
    assert sorted(Question.objects.values_list("pk", flat=True)) == ids_before


def test_reload_keeps_attempts(reload_content, make_attempt):
    question = Question.objects.first()
    make_attempt("abc", question, True)
    make_attempt("abc", question, False)
    reload_content()
    assert Attempt.objects.filter(question=question).count() == 2


def test_edits_update_in_place(reload_content, content, make_attempt):
    question = Question.objects.get(order=0)
    make_attempt("abc", question, True)
    data = copy.deepcopy(content)
    data["questions"][0]["prompt"] = "Edited prompt"
    data["domains"][0]["weight"] = 30
    reload_content(data)
    question.refresh_from_db()
    assert question.prompt == "Edited prompt"
    assert Domain.objects.get(number=1).weight == 30
    assert Attempt.objects.filter(question=question).count() == 1


def test_removed_items_are_pruned(reload_content, content, expected):
    data = copy.deepcopy(content)
    data["rules"].pop()
    data["flashcards"].pop()
    data["questions"][0]["choices"].pop()
    data["domains"][0]["tasks"].pop()
    reload_content(data)
    assert DecisionRule.objects.count() == 35
    assert Flashcard.objects.count() == expected.flashcards - 1
    assert TaskStatement.objects.count() == 29
    assert Question.objects.get(order=0).choices.count() == 3


def test_removed_question_takes_its_attempts(reload_content, content, make_attempt):
    last = Question.objects.order_by("-order").first()
    make_attempt("abc", last, True)
    data = copy.deepcopy(content)
    data["questions"] = [q for q in data["questions"] if q["order"] != last.order]
    reload_content(data)
    assert not Question.objects.filter(pk=last.pk).exists()
    assert not Attempt.objects.exists()


def test_management_command_reports_counts(make_attempt, expected):
    make_attempt("abc", Question.objects.first(), True)
    out = StringIO()
    call_command("load_content", stdout=out)
    call_command("load_content", stdout=out)
    assert "5 domains" in out.getvalue()
    assert f"{expected.questions} questions" in out.getvalue()
    assert Attempt.objects.count() == 1
    assert Question.objects.count() == expected.questions
