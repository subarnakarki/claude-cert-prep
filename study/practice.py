"""Practice sessions: question selection, per-session state, and server-side grading.

A run lives in the Django session as plain JSON, so it survives reloads and needs no
extra tables. Grading never trusts the client: the browser only sends choice ids, and
the server checks them against the question and the stored shuffle.
"""

import random
from dataclasses import asdict, dataclass, field

from .models import Attempt, Domain, Question
from .progress import latest_results

SESSION_KEY = "practice"
RUNS_KEY = "runs_started"

MODES = {
    "all": "All questions",
    "missed": "Only ones I missed",
    "unanswered": "Only unanswered",
}
LETTERS = "abcdefghij"


class InvalidAnswer(ValueError):
    """The submitted choice ids don't belong to the current question."""


@dataclass
class PracticeRun:
    question_ids: list[int]
    choice_order: dict[str, list[int]]  # JSON object keys are strings
    domain: str = ""  # slug, "" for all domains
    mode: str = "all"
    pos: int = 0
    answers: dict[str, dict] = field(default_factory=dict)

    # -- persistence -------------------------------------------------------------
    @classmethod
    def load(cls, session) -> "PracticeRun | None":
        data = session.get(SESSION_KEY)
        if not data:
            return None
        try:
            return cls(**data)
        except TypeError:  # stale shape from an older version: start fresh
            session.pop(SESSION_KEY, None)
            return None

    def save(self, session) -> None:
        session[SESSION_KEY] = asdict(self)

    # -- state -------------------------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.question_ids)

    @property
    def finished(self) -> bool:
        return self.pos >= self.total

    @property
    def current_id(self) -> int | None:
        return None if self.finished else self.question_ids[self.pos]

    def answer_for(self, question_id: int) -> dict | None:
        return self.answers.get(str(question_id))

    @property
    def answered_count(self) -> int:
        return len(self.answers)

    @property
    def correct_count(self) -> int:
        return sum(1 for a in self.answers.values() if a["correct"])

    @property
    def missed_ids(self) -> list[int]:
        return [
            qid
            for qid in self.question_ids
            if (answer := self.answer_for(qid)) is not None and not answer["correct"]
        ]

    def marks(self) -> list[str]:
        """One mark per question for the ●●◉○○ progress line."""
        out = []
        for i, qid in enumerate(self.question_ids):
            answer = self.answer_for(qid)
            if answer is not None:
                out.append("ok" if answer["correct"] else "err")
            elif i == self.pos:
                out.append("cur")
            else:
                out.append("todo")
        return out

    def ordered_choices(self, question: Question) -> list:
        """The question's choices in this run's shuffled order."""
        by_id = {c.id: c for c in question.choices.all()}
        order = self.choice_order.get(str(question.id), [])
        ordered = [by_id.pop(cid) for cid in order if cid in by_id]
        return ordered + list(by_id.values())  # choices added since the run began

    def letter_for(self, question: Question, choice_id: int) -> str:
        ids = [c.id for c in self.ordered_choices(question)]
        return LETTERS[ids.index(choice_id)]


def select_pool(session_key: str | None, domain: Domain | None, mode: str) -> list[int]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    qs = Question.objects.all()
    if domain is not None:
        qs = qs.filter(domain=domain)
    ids = list(qs.values_list("pk", flat=True))
    if mode == "all":
        return ids
    results = latest_results(session_key)
    if mode == "missed":
        return [qid for qid in ids if results.get(qid) is False]
    return [qid for qid in ids if qid not in results]


def build_run(
    question_ids: list[int],
    *,
    domain: str = "",
    mode: str = "all",
    rng: random.Random | None = None,
) -> PracticeRun:
    """Shuffle the questions and each question's choices once, up front."""
    rng = rng or random.Random()
    ids = list(question_ids)
    rng.shuffle(ids)
    choice_order: dict[str, list[int]] = {}
    for question in Question.objects.filter(pk__in=ids).prefetch_related("choices"):
        choice_ids = [c.id for c in question.choices.all()]
        rng.shuffle(choice_ids)
        choice_order[str(question.id)] = choice_ids
    return PracticeRun(question_ids=ids, choice_order=choice_order, domain=domain, mode=mode)


def start_run(session, run: PracticeRun) -> None:
    run.save(session)
    session[RUNS_KEY] = session.get(RUNS_KEY, 0) + 1


def record_answer(
    run: PracticeRun, question: Question, selected: list[str], session_key: str
) -> Attempt:
    """Grade `selected` (raw POST values), store it on the run, and log an Attempt."""
    valid_ids = {c.id for c in question.choices.all()}
    try:
        selected_ids = sorted({int(s) for s in selected})
    except (TypeError, ValueError) as exc:
        raise InvalidAnswer("choice ids must be integers") from exc
    if not selected_ids or not set(selected_ids) <= valid_ids:
        raise InvalidAnswer("choices do not belong to this question")

    is_correct = question.grade(selected_ids)
    run.answers[str(question.id)] = {"selected": selected_ids, "correct": is_correct}
    return Attempt.objects.create(
        session_key=session_key, question=question, selected=selected_ids, is_correct=is_correct
    )
