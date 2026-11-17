from django.urls import path

from . import views

app_name = "study"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("guide/", views.guide, name="guide"),
    path("domains/", views.domain_list, name="domain_list"),
    path("domains/<slug:slug>/", views.domain_detail, name="domain_detail"),
    path("rules/", views.rules, name="rules"),
    path("scenarios/", views.scenarios, name="scenarios"),
    path("flashcards/", views.flashcards, name="flashcards"),
    path("plan/", views.plan, name="plan"),
    path("practice/", views.practice_setup, name="practice_setup"),
    path("practice/start/", views.practice_start, name="practice_start"),
    path("practice/start/<slug:slug>/", views.practice_quick_start, name="practice_quick_start"),
    path("practice/question/", views.practice_question, name="practice_question"),
    path("practice/run/", views.practice_run, name="practice_run"),
    path("practice/next/", views.practice_next, name="practice_next"),
    path("practice/results/", views.practice_results, name="practice_results"),
    path("practice/retry/", views.practice_retry, name="practice_retry"),
    path("practice/reset/", views.practice_reset, name="practice_reset"),
]
