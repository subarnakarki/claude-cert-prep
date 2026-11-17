from django.contrib import admin

from .models import (
    Attempt,
    Choice,
    DecisionRule,
    Domain,
    Flashcard,
    Question,
    Scenario,
    TaskStatement,
)


class TaskStatementInline(admin.TabularInline):
    model = TaskStatement
    extra = 0
    fields = ["code", "title", "order"]
    show_change_link = True


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "slug", "weight"]
    prepopulated_fields = {"slug": ["short_name"]}
    inlines = [TaskStatementInline]


@admin.register(TaskStatement)
class TaskStatementAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "domain"]
    list_filter = ["domain"]
    search_fields = ["title", "body_html"]


@admin.register(DecisionRule)
class DecisionRuleAdmin(admin.ModelAdmin):
    list_display = ["order", "trigger", "action"]
    search_fields = ["trigger", "action"]


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ["number", "title"]
    filter_horizontal = ["domains"]


@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ["order", "front", "domain"]
    list_filter = ["domain"]
    search_fields = ["front", "back_html"]


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ["order", "text", "is_correct"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["order", "short_prompt", "domain", "select_count"]
    list_filter = ["domain"]
    search_fields = ["prompt", "explanation"]
    inlines = [ChoiceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("choices")

    @admin.display(description="Prompt")
    def short_prompt(self, obj):
        return str(obj)


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ["question", "order", "short_text", "is_correct"]
    list_filter = ["is_correct", "question__domain"]

    @admin.display(description="Text")
    def short_text(self, obj):
        return str(obj)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ["created_at", "short_session", "question", "is_correct"]
    list_filter = ["is_correct", "question__domain", "created_at"]
    search_fields = ["session_key"]
    readonly_fields = ["created_at"]
    list_select_related = ["question"]

    @admin.display(description="Session")
    def short_session(self, obj):
        return obj.session_key[:8]
