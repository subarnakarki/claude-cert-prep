from collections.abc import Iterable

from django.db import models
from django.urls import reverse

EXAM_QUESTIONS = 60


class Domain(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=40)
    weight = models.PositiveSmallIntegerField(help_text="Percent of the exam")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number}. {self.name}"

    def get_absolute_url(self):
        return reverse("study:domain_detail", args=[self.slug])

    @property
    def exam_items(self) -> int:
        """Approximate number of the 60 exam items drawn from this domain."""
        return round(EXAM_QUESTIONS * self.weight / 100)


class TaskStatement(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="tasks")
    code = models.CharField(max_length=8)
    title = models.CharField(max_length=160)
    body_html = models.TextField(help_text="Trusted HTML from the content file")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["domain__number", "order"]
        constraints = [models.UniqueConstraint(fields=["domain", "code"], name="uniq_task_code")]

    def __str__(self):
        return f"{self.code} {self.title}"


class DecisionRule(models.Model):
    trigger = models.CharField(max_length=255)
    action = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.trigger


class Scenario(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)
    title = models.CharField(max_length=160)
    summary = models.TextField(help_text="Trusted HTML from the content file")
    focus = models.TextField(help_text="What questions in this scenario tend to test")
    domains = models.ManyToManyField(Domain, related_name="scenarios")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return self.title


class Flashcard(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="flashcards")
    front = models.CharField(max_length=255)
    back_html = models.TextField(help_text="Trusted HTML from the content file")
    order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.front


class Question(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    explanation = models.TextField()
    order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.prompt[:80]

    @property
    def correct_ids(self) -> set[int]:
        # Iterate .all() so a prefetch_related("choices") is reused instead of re-querying.
        return {c.id for c in self.choices.all() if c.is_correct}

    @property
    def select_count(self) -> int:
        return len(self.correct_ids)

    @property
    def is_multi(self) -> bool:
        return self.select_count > 1

    def grade(self, selected_ids: Iterable[int | str]) -> bool:
        """Exact-match grading: every correct choice and nothing else."""
        return {int(i) for i in selected_ids} == self.correct_ids


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["question", "order"]
        constraints = [
            models.UniqueConstraint(fields=["question", "order"], name="uniq_choice_order")
        ]

    def __str__(self):
        return self.text[:60]


class Attempt(models.Model):
    """One graded answer. Progress is tracked per browser session, no login needed."""

    session_key = models.CharField(max_length=40)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="attempts")
    selected = models.JSONField(default=list, help_text="Choice ids the learner picked")
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["session_key", "question", "-created_at"], name="attempt_latest_idx"
            )
        ]

    def __str__(self):
        mark = "✓" if self.is_correct else "✗"
        return f"{self.session_key[:6]} q{self.question_id} {mark}"
