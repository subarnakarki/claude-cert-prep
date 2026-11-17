"""Readiness math for the `ccarf status` panel.

A question is *mastered* when its most recent attempt in this browser session was
correct. Domain readiness is mastered / total, and the projected score weights each
domain's readiness by its share of the exam.
"""

import math
from collections import Counter
from dataclasses import dataclass

from django.db.models import Count, OuterRef, Subquery

from .models import Attempt, Domain, Question

PASS_LINE = 72  # ≈ 720 on the 100–1,000 scaled score
WARN_LINE = 50
READY_LINE = 85  # every domain at or above this → "end_turn", go book the exam
BAR_WIDTH = 16


def latest_results(session_key: str | None) -> dict[int, bool]:
    """Map question id → whether its latest attempt in this session was correct."""
    if not session_key:
        return {}
    latest = Attempt.objects.filter(session_key=session_key, question=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    rows = (
        Question.objects.annotate(last_correct=Subquery(latest.values("is_correct")[:1]))
        .filter(last_correct__isnull=False)
        .values_list("pk", "last_correct")
    )
    return dict(rows)


def status_for(ratio: float) -> str:
    """CSS status class for a readiness ratio: ok ≥ 72%, warn 50–71%, err < 50%."""
    percent = ratio * 100
    if percent >= PASS_LINE:
        return "ok"
    if percent >= WARN_LINE:
        return "warn"
    return "err"


def text_bar(ratio: float, width: int = BAR_WIDTH) -> str:
    # Round half up (not Python's banker's rounding) so app.js draws identical bars.
    filled = min(width, max(0, math.floor(ratio * width + 0.5)))
    return "█" * filled + "░" * (width - filled)


@dataclass(frozen=True)
class DomainReadiness:
    domain: Domain
    mastered: int
    total: int

    @property
    def ratio(self) -> float:
        return self.mastered / self.total if self.total else 0.0

    @property
    def percent(self) -> int:
        # Floor, so the number shown never claims a threshold the status hasn't reached.
        return math.floor(self.ratio * 100)

    @property
    def status(self) -> str:
        return status_for(self.ratio)

    @property
    def bar(self) -> str:
        return text_bar(self.ratio)


def readiness(session_key: str | None) -> list[DomainReadiness]:
    results = latest_results(session_key)
    mastered_ids = [qid for qid, correct in results.items() if correct]
    mastered_by_domain = Counter(
        Question.objects.filter(pk__in=mastered_ids).values_list("domain_id", flat=True)
    )
    domains = Domain.objects.annotate(total=Count("questions"))
    return [DomainReadiness(d, mastered_by_domain[d.pk], d.total) for d in domains]


def projected_score(rows: list[DomainReadiness]) -> float:
    """Σ(weight × mastered/total), as a percentage of the exam."""
    total_weight = sum(r.domain.weight for r in rows)
    if not total_weight:
        return 0.0
    return sum(r.domain.weight * r.ratio for r in rows) * 100 / total_weight


def weakest(rows: list[DomainReadiness]) -> DomainReadiness | None:
    """Lowest readiness; ties go to the heavier domain (more points at stake)."""
    if not rows:
        return None
    return min(rows, key=lambda r: (r.ratio, -r.domain.weight, r.domain.number))


def stop_reason(rows: list[DomainReadiness]) -> str:
    """Borrow the agentic-loop signal: keep going until every domain is ≥ 85%."""
    if rows and all(r.ratio * 100 >= READY_LINE for r in rows):
        return "end_turn"
    return "tool_use"
