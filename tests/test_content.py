"""Content integrity: the JSON file and what the data migration put in the database."""

import re

import pytest

from study.content_loader import SLUGS
from study.models import (
    Choice,
    DecisionRule,
    Domain,
    Flashcard,
    Question,
    Scenario,
    TaskStatement,
)

WORD_NUMBERS = {"TWO": 2, "THREE": 3, "FOUR": 4}
SELECT_N = re.compile(r"\(Select (\w+)\.?\)", re.IGNORECASE)


def test_json_has_five_domains_weighted_to_100(content):
    assert len(content["domains"]) == 5
    assert sum(d["weight"] for d in content["domains"]) == 100


def test_json_counts(content):
    assert sum(len(d["tasks"]) for d in content["domains"]) == 30
    assert len(content["rules"]) == 36
    assert len(content["scenarios"]) == 6
    assert len(content["flashcards"]) == 53
    assert len(content["questions"]) == 63


def test_question_orders_are_unique(content):
    orders = [q["order"] for q in content["questions"]]
    assert len(orders) == len(set(orders))


@pytest.mark.parametrize("domain_number", [1, 2, 3, 4, 5])
def test_task_codes_match_their_domain(content, domain_number):
    domain = content["domains"][domain_number - 1]
    for task in domain["tasks"]:
        assert task["code"].startswith(f"{domain_number}.")


def test_every_question_has_a_correct_choice(content):
    for q in content["questions"]:
        assert any(c["is_correct"] for c in q["choices"]), q["prompt"]


def test_select_n_prompts_match_correct_count(content):
    for q in content["questions"]:
        n_correct = sum(c["is_correct"] for c in q["choices"])
        match = SELECT_N.search(q["prompt"])
        if n_correct > 1:
            assert match, f"multi-select question doesn't say how many: {q['prompt']}"
        if match:
            word = match.group(1).upper()
            expected = WORD_NUMBERS.get(word) or int(word)
            assert expected == n_correct, q["prompt"]


def test_choice_texts_are_unique_within_a_question(content):
    for q in content["questions"]:
        texts = [c["text"] for c in q["choices"]]
        assert len(texts) == len(set(texts)), q["prompt"]


@pytest.mark.django_db
def test_migration_loaded_everything():
    assert Domain.objects.count() == 5
    assert TaskStatement.objects.count() == 30
    assert DecisionRule.objects.count() == 36
    assert Scenario.objects.count() == 6
    assert Flashcard.objects.count() == 53
    assert Question.objects.count() == 63
    assert sum(Domain.objects.values_list("weight", flat=True)) == 100


@pytest.mark.django_db
def test_slugs_are_cli_style():
    assert list(Domain.objects.values_list("slug", flat=True)) == list(SLUGS.values())


@pytest.mark.django_db
def test_db_questions_have_correct_choices_and_multi_counts():
    for q in Question.objects.prefetch_related("choices"):
        assert q.select_count >= 1
        if q.is_multi:
            assert f"Select {'TWO' if q.select_count == 2 else q.select_count}" in q.prompt


@pytest.mark.django_db
def test_scenarios_link_domains():
    for s in Scenario.objects.prefetch_related("domains"):
        assert s.domains.exists()


@pytest.mark.django_db
def test_seven_multi_select_questions():
    multi = [q for q in Question.objects.prefetch_related("choices") if q.is_multi]
    assert len(multi) == 7
    assert Choice.objects.filter(question__in=multi).count() == 35
