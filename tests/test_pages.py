"""Every page renders, and unknown slugs 404."""

import pytest

from study.content_loader import SLUGS

pytestmark = pytest.mark.django_db

PAGES = [
    "/",
    "/domains/",
    "/rules/",
    "/scenarios/",
    "/flashcards/",
    "/plan/",
    "/practice/",
    "/practice/reset/",
]


@pytest.mark.parametrize("url", PAGES)
def test_page_returns_200(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert b"ccarf<span>-prep</span>" in response.content


@pytest.mark.parametrize("slug", SLUGS.values())
def test_domain_detail_returns_200(client, slug):
    response = client.get(f"/domains/{slug}/")
    assert response.status_code == 200
    assert b'class="task"' in response.content


@pytest.mark.parametrize("slug", SLUGS.values())
def test_flashcards_filter_returns_200(client, slug):
    response = client.get(f"/flashcards/?domain={slug}")
    assert response.status_code == 200
    assert response.context["cards"]
    assert all(card.domain.slug == slug for card in response.context["cards"])


def test_unknown_domain_slug_404s(client):
    assert client.get("/domains/nope/").status_code == 404


def test_unknown_flashcard_domain_404s(client):
    assert client.get("/flashcards/?domain=nope").status_code == 404


def test_custom_404_page(client):
    response = client.get("/domains/nope/")
    assert b"Nothing here" in response.content


def test_nav_marks_current_page(client):
    response = client.get("/rules/")
    assert b'href="/rules/" aria-current="page"' in response.content
    detail = client.get("/domains/agentic/")
    assert b'href="/domains/" aria-current="page"' in detail.content


def test_overview_terminal(client):
    html = client.get("/").content.decode()
    assert "$</span> ccarf status" in html
    assert "pass line ≈ 72%" in html
    assert '"tool_use"' in html
    assert "ccarf practice --domain agentic" in html  # all at 0%: heaviest domain wins
    for fact in ["120 minutes", "720 on a 100–1,000 scale", "4 drawn from 6", "$125"]:
        assert fact in html


def test_domain_detail_renders_trusted_html(client):
    html = client.get("/domains/agentic/").content.decode()
    assert '<div class="trap">' in html
    assert '<div class="code">1.1</div>' in html


def test_flashcards_without_js_show_every_card(client):
    html = client.get("/flashcards/").content.decode()
    assert html.count('<li class="card">') == 53
    assert 'id="deck" hidden' in html


def test_rules_and_scenarios_codeify(client):
    html = client.get("/scenarios/").content.decode()
    assert "<code>process_refund</code>" in html


def test_admin_registers_models(admin_client):
    for model in ["domain", "taskstatement", "decisionrule", "scenario", "flashcard", "question"]:
        assert admin_client.get(f"/admin/study/{model}/").status_code == 200
    from study.models import Question

    q = Question.objects.first()
    response = admin_client.get(f"/admin/study/question/{q.pk}/change/")
    assert response.status_code == 200
    assert b"choices-TOTAL_FORMS" in response.content
