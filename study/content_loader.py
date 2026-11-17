"""Load exam content from study/content/ccarf.json.

Written against a model registry (`get_model(app_label, model_name)`) so the same code
runs from the data migration (historical models) and from the `load_content` management
command (live models).

Loading is idempotent: rows are matched on natural keys and updated in place, so
re-running after editing the JSON keeps existing progress (Attempts) intact. Rows whose
natural key has disappeared from the JSON are pruned, so the database mirrors the file.
"""

import json
from collections.abc import Callable
from pathlib import Path

CONTENT_PATH = Path(__file__).resolve().parent / "content" / "ccarf.json"

# Snake_case slugs double as the CLI-style identifiers shown in the UI
# (`ccarf practice --domain tools_mcp`).
SLUGS = {1: "agentic", 2: "tools_mcp", 3: "claude_code", 4: "prompting", 5: "context"}

GetModel = Callable[[str, str], type]


def read_content(path: Path = CONTENT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load(get_model: GetModel, data: dict | None = None) -> dict[str, int]:
    """Create or update every content row. Call inside a transaction."""
    data = data if data is not None else read_content()
    Domain = get_model("study", "Domain")
    TaskStatement = get_model("study", "TaskStatement")
    DecisionRule = get_model("study", "DecisionRule")
    Scenario = get_model("study", "Scenario")
    Flashcard = get_model("study", "Flashcard")
    Question = get_model("study", "Question")
    Choice = get_model("study", "Choice")

    domains = {}
    for d in data["domains"]:
        domain, _ = Domain.objects.update_or_create(
            number=d["number"],
            defaults={
                "slug": SLUGS[d["number"]],
                "name": d["name"],
                "short_name": d["short_name"],
                "weight": d["weight"],
            },
        )
        domains[d["number"]] = domain
        codes = []
        for t in d["tasks"]:
            TaskStatement.objects.update_or_create(
                domain=domain,
                code=t["code"],
                defaults={"title": t["title"], "body_html": t["body_html"], "order": t["order"]},
            )
            codes.append(t["code"])
        TaskStatement.objects.filter(domain=domain).exclude(code__in=codes).delete()
    Domain.objects.exclude(number__in=domains).delete()

    for r in data["rules"]:
        DecisionRule.objects.update_or_create(
            order=r["order"], defaults={"trigger": r["trigger"], "action": r["action"]}
        )
    DecisionRule.objects.exclude(order__in=[r["order"] for r in data["rules"]]).delete()

    for s in data["scenarios"]:
        scenario, _ = Scenario.objects.update_or_create(
            number=s["number"],
            defaults={"title": s["title"], "summary": s["summary"], "focus": s["focus"]},
        )
        scenario.domains.set([domains[n] for n in s["domains"]])
    Scenario.objects.exclude(number__in=[s["number"] for s in data["scenarios"]]).delete()

    # Flashcards carry no id in the JSON, so their position is the natural key.
    for i, f in enumerate(data["flashcards"]):
        Flashcard.objects.update_or_create(
            order=i,
            defaults={
                "domain": domains[f["domain"]],
                "front": f["front"],
                "back_html": f["back_html"],
            },
        )
    Flashcard.objects.filter(order__gte=len(data["flashcards"])).delete()

    scenarios = {s.number: s for s in Scenario.objects.all()}
    # The 0002 data migration runs this with historical models from before
    # Question.scenario existed, so only set the field when the model has it.
    has_scenario = any(f.name == "scenario" for f in Question._meta.get_fields())
    for q in data["questions"]:
        defaults = {
            "domain": domains[q["domain"]],
            "prompt": q["prompt"],
            "explanation": q["explanation"],
        }
        if has_scenario:
            defaults["scenario"] = scenarios.get(q.get("scenario"))
        question, _ = Question.objects.update_or_create(order=q["order"], defaults=defaults)
        for j, c in enumerate(q["choices"]):
            Choice.objects.update_or_create(
                question=question,
                order=j,
                defaults={"text": c["text"], "is_correct": c["is_correct"]},
            )
        Choice.objects.filter(question=question, order__gte=len(q["choices"])).delete()
    # Removing a question also removes its attempts: there is nothing left to master.
    Question.objects.exclude(order__in=[q["order"] for q in data["questions"]]).delete()

    return {
        "domains": len(domains),
        "tasks": sum(len(d["tasks"]) for d in data["domains"]),
        "rules": len(data["rules"]),
        "scenarios": len(data["scenarios"]),
        "flashcards": len(data["flashcards"]),
        "questions": len(data["questions"]),
    }
