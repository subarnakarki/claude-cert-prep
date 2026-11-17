import math
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Prefetch
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import practice, progress
from .forms import PracticeSetupForm
from .models import Attempt, DecisionRule, Domain, Flashcard, Question, Scenario

EXAM_FACTS = [
    ("Questions", "60, multiple choice and multiple response"),
    ("Time", "120 minutes"),
    ("Pass", "720 on a 100–1,000 scale"),
    ("Scenarios", "4 drawn from 6"),
    ("Fee", "$125, valid 12 months"),
]


def _session_key(request, *, create: bool = False) -> str | None:
    """The browser-session id that owns Attempts; create it on first write."""
    if create and not request.session.session_key:
        request.session.save()
    return request.session.session_key


# -- reading pages ---------------------------------------------------------------


@require_GET
def overview(request):
    rows = progress.readiness(_session_key(request))
    weakest = progress.weakest(rows)
    context = {
        "rows": rows,
        "weakest": weakest,
        "projected": progress.projected_score(rows),
        "stop_reason": progress.stop_reason(rows),
        "mastered": sum(r.mastered for r in rows),
        "total": sum(r.total for r in rows),
        "pass_line": progress.PASS_LINE,
        "runs_started": request.session.get(practice.RUNS_KEY, 0),
        "exam_facts": EXAM_FACTS,
    }
    return render(request, "study/overview.html", context)


@require_GET
def guide(request):
    domains = [(d, round(60 * d.weight / 100)) for d in Domain.objects.all()]
    return render(request, "study/guide.html", {"domains": domains})


@require_GET
def domain_list(request):
    rows = progress.readiness(_session_key(request))
    counts = {
        d.pk: d
        for d in Domain.objects.annotate(
            n_tasks=Count("tasks", distinct=True), n_cards=Count("flashcards", distinct=True)
        )
    }
    items = [(row, counts[row.domain.pk]) for row in rows]
    return render(request, "study/domain_list.html", {"items": items})


@require_GET
def domain_detail(request, slug):
    domain = get_object_or_404(Domain.objects.prefetch_related("tasks", "scenarios"), slug=slug)
    row = next(r for r in progress.readiness(_session_key(request)) if r.domain.pk == domain.pk)
    return render(request, "study/domain_detail.html", {"domain": domain, "row": row})


@require_GET
def rules(request):
    return render(request, "study/rules.html", {"rules": DecisionRule.objects.all()})


@require_GET
def scenarios(request):
    items = Scenario.objects.prefetch_related(Prefetch("domains", Domain.objects.all())).annotate(
        n_questions=Count("questions")
    )
    return render(request, "study/scenarios.html", {"scenarios": items})


@require_GET
def flashcards(request):
    domains = list(Domain.objects.all())
    slug = request.GET.get("domain", "")
    domain = get_object_or_404(Domain, slug=slug) if slug else None
    cards = Flashcard.objects.select_related("domain")
    if domain:
        cards = cards.filter(domain=domain)
    context = {"cards": cards, "domain": domain, "domains": domains}
    return render(request, "study/flashcards.html", context)


@require_GET
def plan(request):
    return render(request, "study/plan.html", {"domains": Domain.objects.all()})


# -- practice --------------------------------------------------------------------


@require_GET
def practice_setup(request):
    initial = {
        "domain": request.GET.get("domain", ""),
        "scenario": request.GET.get("scenario", ""),
        "mode": request.GET.get("mode", "all"),
    }
    return _render_setup(request, PracticeSetupForm(initial=initial))


def _render_setup(request, form, status=200):
    run = practice.PracticeRun.load(request.session)
    context = {
        "form": form,
        "run": run if run and not run.finished else None,
        "rows": progress.readiness(_session_key(request)),
    }
    return render(request, "study/practice_setup.html", context, status=status)


@require_POST
def practice_start(request):
    form = PracticeSetupForm(request.POST)
    if not form.is_valid():
        return _render_setup(request, form, status=400)
    domain, mode = form.cleaned_data["domain"], form.cleaned_data["mode"]
    scenario = form.cleaned_data["scenario"]
    pool = practice.select_pool(_session_key(request), domain, mode, scenario)
    if not pool:
        form.add_error(None, _empty_pool_message(mode))
        return _render_setup(request, form)
    run = practice.build_run(
        pool,
        domain=domain.slug if domain else "",
        mode=mode,
        scenario=scenario.number if scenario else None,
    )
    practice.start_run(request.session, run)
    return redirect("study:practice_question")


def _empty_pool_message(mode: str) -> str:
    if mode == "missed":
        return "Nothing to retry: you haven't missed any questions here yet."
    if mode == "unanswered":
        return "You've answered every question here. Try all questions or only misses."
    return "No questions match that domain and scenario."


@require_http_methods(["GET", "POST"])
def practice_question(request):
    run = practice.PracticeRun.load(request.session)
    if run is None:
        return redirect("study:practice_setup")
    if run.finished:
        return redirect("study:practice_results")

    question = (
        Question.objects.select_related("domain", "scenario")
        .prefetch_related("choices")
        .filter(pk=run.current_id)
        .first()
    )
    if question is None:  # removed from the content since the run began
        run.question_ids.pop(run.pos)
        run.save(request.session)
        return redirect("study:practice_question")

    error = None
    if request.method == "POST" and run.answer_for(question.id) is None:
        selected = request.POST.getlist("choice")
        if not selected:
            error = "Pick an answer first."
        else:
            try:
                practice.record_answer(run, question, selected, _session_key(request, create=True))
            except practice.InvalidAnswer:
                return HttpResponseBadRequest("Those choices don't belong to this question.")
            run.save(request.session)
            return redirect("study:practice_question")
    elif request.method == "POST":  # already answered: don't grade twice
        return redirect("study:practice_question")

    return render(
        request,
        "study/practice_question.html",
        _question_context(run, question, error),
        status=400 if error else 200,
    )


def _question_context(run, question, error):
    answer = run.answer_for(question.id)
    selected = set(answer["selected"]) if answer else set()
    options = []
    for letter, choice in zip(practice.LETTERS, run.ordered_choices(question), strict=False):
        state = ""
        if answer:
            if choice.is_correct:
                state = "right"
            elif choice.id in selected:
                state = "wrong"
        options.append(
            {"choice": choice, "letter": letter, "state": state, "checked": choice.id in selected}
        )
    return {
        "run": run,
        "question": question,
        "options": options,
        "answer": answer,
        "chosen_letters": [o["letter"] for o in options if o["checked"]],
        "correct_letters": [o["letter"] for o in options if o["choice"].is_correct],
        "error": error,
        "is_last": run.pos == run.total - 1,
        "domain": Domain.objects.filter(slug=run.domain).first() if run.domain else None,
        "scenario": Scenario.objects.filter(number=run.scenario).first() if run.scenario else None,
    }


@require_GET
def practice_run(request):
    """The static build's practice page: app.js runs the whole session in the browser."""
    if not settings.STATIC_SITE:
        return redirect("study:practice_question")
    return render(request, "study/practice_run.html")


@require_POST
def practice_next(request):
    run = practice.PracticeRun.load(request.session)
    if run is None:
        return redirect("study:practice_setup")
    if not run.finished and run.answer_for(run.current_id) is not None:
        run.pos += 1
        run.save(request.session)
    if run.finished:
        return redirect("study:practice_results")
    return redirect("study:practice_question")


@require_GET
def practice_results(request):
    run = practice.PracticeRun.load(request.session)
    if run is None:
        return redirect("study:practice_setup")
    answered_ids = [int(qid) for qid in run.answers]
    by_domain = defaultdict(lambda: {"answered": 0, "correct": 0})
    for q in Question.objects.filter(pk__in=answered_ids).select_related("domain"):
        stats = by_domain[q.domain]
        stats["answered"] += 1
        stats["correct"] += int(run.answers[str(q.pk)]["correct"])
    domain_rows = []
    for d, s in sorted(by_domain.items(), key=lambda item: item[0].number):
        ratio = s["correct"] / s["answered"]
        domain_rows.append(
            {
                "domain": d,
                **s,
                "percent": math.floor(ratio * 100),
                "status": progress.status_for(ratio),
                "bar": progress.text_bar(ratio),
                "ratio": ratio,
            }
        )
    score = run.correct_count / run.answered_count if run.answered_count else 0
    context = {
        "run": run,
        "domain_rows": domain_rows,
        "missed": len(run.missed_ids),
        "percent": math.floor(score * 100),
    }
    return render(request, "study/practice_results.html", context)


@require_POST
def practice_retry(request):
    run = practice.PracticeRun.load(request.session)
    if run is None or not run.missed_ids:
        return redirect("study:practice_setup")
    retry = practice.build_run(
        run.missed_ids, domain=run.domain, mode="missed", scenario=run.scenario
    )
    practice.start_run(request.session, retry)
    return redirect("study:practice_question")


@require_POST
def practice_quick_start(request, slug):
    """The overview's `ccarf practice --domain <slug>` button: all questions, one domain."""
    domain = get_object_or_404(Domain, slug=slug)
    pool = practice.select_pool(_session_key(request), domain, "all")
    practice.start_run(request.session, practice.build_run(pool, domain=slug))
    return redirect("study:practice_question")


@require_http_methods(["GET", "POST"])
def practice_reset(request):
    session_key = _session_key(request)
    if request.method == "POST":
        if session_key:
            Attempt.objects.filter(session_key=session_key).delete()
        request.session.pop(practice.SESSION_KEY, None)
        request.session.pop(practice.RUNS_KEY, None)
        messages.success(request, "Progress reset. Every domain starts from zero.")
        return redirect("study:overview")
    attempts = Attempt.objects.filter(session_key=session_key).count() if session_key else 0
    return render(request, "study/reset_confirm.html", {"attempts": attempts})
