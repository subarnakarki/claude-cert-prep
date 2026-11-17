from django.template import Context, Template
from django.utils.safestring import SafeString

from study.templatetags.study_tags import bar, codeify


def test_wraps_snake_case_identifiers():
    assert codeify("call process_refund then escalate_to_human") == (
        "call <code>process_refund</code> then <code>escalate_to_human</code>"
    )


def test_wraps_quoted_stop_reasons():
    assert codeify('when stop_reason is "tool_use"') == (
        "when <code>stop_reason</code> is &quot;<code>tool_use</code>&quot;"
    )


def test_wraps_screaming_snake_env_vars():
    assert codeify("set GITHUB_TOKEN") == "set <code>GITHUB_TOKEN</code>"


def test_leaves_plain_words_alone():
    for text in ["plain words", "snake", "a well-known file.md", "_private", "trailing_", "3_5"]:
        assert codeify(text) == text.replace("'", "&#x27;")


def test_escapes_before_wrapping():
    out = codeify('<script>alert("x")</script> tool_use')
    assert "<script>" not in out
    assert out.startswith("&lt;script&gt;")
    assert out.endswith("<code>tool_use</code>")


def test_does_not_wrap_inside_entities_or_html_in_input():
    out = codeify("<b class=a_b>")
    assert out == "&lt;b class=<code>a_b</code>&gt;"
    assert "<b" not in out


def test_output_is_safe_and_works_in_templates():
    assert isinstance(codeify("tool_use"), SafeString)
    rendered = Template("{% load study_tags %}{{ text|codeify }}").render(
        Context({"text": "<i>max_tokens</i>"})
    )
    assert rendered == "&lt;i&gt;<code>max_tokens</code>&lt;/i&gt;"


def test_each_identifier_wrapped_once():
    out = codeify("tool_use and tool_use")
    assert out.count("<code>") == 2
    assert "<code><code>" not in out


def test_none_is_empty():
    assert codeify(None) == ""


def test_bar_filter():
    assert bar(0.5, 4) == "██░░"
    assert bar("bad", 4) == "░░░░"
