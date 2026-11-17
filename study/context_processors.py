from django.conf import settings
from django.urls import reverse

# (label, url name, url-name prefix that marks the section as current)
NAV = [
    ("overview", "study:overview", "overview"),
    ("guide", "study:guide", "guide"),
    ("domains", "study:domain_list", "domain_"),
    ("rules", "study:rules", "rules"),
    ("scenarios", "study:scenarios", "scenarios"),
    ("flashcards", "study:flashcards", "flashcards"),
    ("practice", "study:practice_setup", "practice_"),
    ("plan", "study:plan", "plan"),
]


def nav(request):
    match = getattr(request, "resolver_match", None)
    current = match.url_name if match and match.app_name == "study" else ""
    items = [
        {"label": label, "url": reverse(name), "current": current.startswith(prefix)}
        for label, name, prefix in NAV
    ]
    return {"nav_items": items, "static_site": settings.STATIC_SITE}
