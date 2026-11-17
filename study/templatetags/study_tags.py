import re

from django import template
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from ..progress import text_bar

register = template.Library()

# snake_case or SCREAMING_SNAKE identifiers: at least one underscore between word parts.
IDENTIFIER = re.compile(r"(?<![\w&#])([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)(?!\w)")


@register.filter(is_safe=True)
def codeify(value) -> SafeString:
    """Escape plain text, then wrap identifiers like `process_refund` in <code>.

    Escaping first means user-visible text can never inject markup; the only tags in
    the output are the <code> wrappers added here.
    """
    escaped = escape("" if value is None else str(value))
    return mark_safe(IDENTIFIER.sub(r"<code>\1</code>", escaped))


@register.filter
def bar(ratio, width: int = 16) -> str:
    """A █/░ text bar for a 0–1 ratio."""
    try:
        return text_bar(float(ratio), int(width))
    except (TypeError, ValueError):
        return text_bar(0.0, int(width))
