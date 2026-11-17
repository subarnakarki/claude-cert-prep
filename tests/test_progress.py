"""Readiness, projected score, weakest-domain choice and the stop_reason switch."""

from types import SimpleNamespace

import pytest

from study import progress
from study.models import Question
from study.progress import DomainReadiness


def row(number, weight, mastered, total):
    domain = SimpleNamespace(number=number, weight=weight, slug=f"d{number}")
    return DomainReadiness(domain, mastered, total)


# -- pure math -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mastered", "total", "status"),
    [
        (0, 100, "err"),
        (49, 100, "err"),
        (50, 100, "warn"),
        (71, 100, "warn"),
        (72, 100, "ok"),
        (100, 100, "ok"),
        (0, 0, "err"),
    ],
)
def test_status_thresholds(mastered, total, status):
    assert row(1, 20, mastered, total).status == status


def test_percent_floors_so_it_never_overstates():
    r = row(1, 20, 5, 7)  # 71.4%
    assert r.percent == 71
    assert r.status == "warn"


def test_text_bar():
    assert progress.text_bar(0) == "░" * 16
    assert progress.text_bar(1) == "█" * 16
    assert progress.text_bar(0.5) == "█" * 8 + "░" * 8
    assert len(progress.text_bar(0.37)) == 16
    assert progress.text_bar(1.7) == "█" * 16  # clamped


def test_projected_score_is_weighted():
    rows = [
        row(1, 27, 16, 16),
        row(2, 18, 0, 11),
        row(3, 20, 6, 12),
        row(4, 20, 0, 12),
        row(5, 15, 9, 9),
    ]
    # 27*1 + 18*0 + 20*.5 + 20*0 + 15*1 = 52
    assert progress.projected_score(rows) == pytest.approx(52)


def test_projected_score_empty():
    assert progress.projected_score([]) == 0


def test_weakest_is_lowest_ratio():
    rows = [row(1, 27, 10, 12), row(2, 18, 2, 11), row(3, 20, 6, 12)]
    assert progress.weakest(rows).domain.number == 2


def test_weakest_tie_goes_to_heavier_domain_then_number():
    rows = [row(1, 15, 0, 10), row(2, 27, 0, 10), row(3, 27, 0, 10)]
    assert progress.weakest(rows).domain.number == 2
    assert progress.weakest([]) is None


def test_stop_reason_switches_at_85_percent():
    almost = [row(1, 50, 85, 100), row(2, 50, 84, 100)]
    ready = [row(1, 50, 85, 100), row(2, 50, 100, 100)]
    assert progress.stop_reason(almost) == "tool_use"
    assert progress.stop_reason(ready) == "end_turn"
    assert progress.stop_reason([]) == "tool_use"


# -- mastery from attempts -------------------------------------------------------------


@pytest.mark.django_db
def test_latest_attempt_decides_mastery(make_attempt):
    q1, q2, q3 = Question.objects.all()[:3]
    make_attempt("s1", q1, False)
    make_attempt("s1", q1, True)  # wrong then right → mastered
    make_attempt("s1", q2, True)
    make_attempt("s1", q2, False)  # right then wrong → not mastered
    make_attempt("other", q3, True)  # other sessions don't count
    assert progress.latest_results("s1") == {q1.pk: True, q2.pk: False}
    assert progress.latest_results(None) == {}


@pytest.mark.django_db
def test_readiness_counts_per_domain(make_attempt, domains):
    agentic = list(domains["agentic"].questions.all())
    total = len(agentic)
    mastered = -(-total * 3 // 4)  # 75%, rounded up
    for q in agentic[:mastered]:
        make_attempt("s1", q, True)
    make_attempt("s1", agentic[mastered], False)
    rows = {r.domain.slug: r for r in progress.readiness("s1")}
    assert rows["agentic"].mastered == mastered
    assert rows["agentic"].total == total
    assert rows["agentic"].status == "ok"
    assert rows["tools_mcp"].mastered == 0
    assert progress.weakest(list(rows.values())).domain.slug == "claude_code"  # 0%, weight 20
    assert progress.projected_score(list(rows.values())) == pytest.approx(27 * mastered / total)


@pytest.mark.django_db
def test_end_turn_when_every_domain_is_ready(make_attempt):
    for q in Question.objects.all():
        make_attempt("s1", q, True)
    rows = progress.readiness("s1")
    assert progress.stop_reason(rows) == "end_turn"
    assert progress.projected_score(rows) == pytest.approx(100)


@pytest.mark.django_db
def test_overview_shows_end_turn(client, make_attempt):
    client.get("/")
    session = client.session
    session.save()
    for q in Question.objects.all():
        make_attempt(session.session_key, q, True)
    html = client.get("/").content.decode()
    assert '"end_turn"' in html
    assert "book the exam" in html
    assert 'projected</span> <span class="ok">100%' in html
