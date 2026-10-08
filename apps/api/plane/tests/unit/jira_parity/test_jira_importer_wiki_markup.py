# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity importer: Jira wiki markup -> editor HTML (plane.utils.jira_parity.wiki_markup)."""

import pytest

from plane.utils.content_validator import validate_html_content
from plane.utils.jira_parity.wiki_markup import EMPTY_PARAGRAPH, description_fields, jira_wiki_to_html


def html(text, **kwargs):
    """Converter output before the sanitizer (exact structure assertions)."""
    return jira_wiki_to_html(text, sanitize=False, **kwargs)


@pytest.mark.unit
class TestBlocks:
    @pytest.mark.parametrize("value", [None, "", "   ", "\n\n"])
    def test_blank_is_empty_paragraph(self, value):
        assert jira_wiki_to_html(value) == EMPTY_PARAGRAPH

    def test_headings(self):
        assert html("h1. Title\nh3. Sub *bold*\nh6. Six") == (
            "<h1>Title</h1><h3>Sub <strong>bold</strong></h3><h6>Six</h6>"
        )

    def test_h7_is_not_a_heading(self):
        assert html("h7. nope") == "<p>h7. nope</p>"

    def test_paragraphs_and_line_breaks(self):
        assert html("line1\nline2\n\npara2") == "<p>line1<br>line2</p><p>para2</p>"
        assert html("a\r\nb") == "<p>a<br>b</p>"
        assert html("a\\\\b") == "<p>a<br>b</p>"

    def test_horizontal_rule(self):
        assert html("a\n----\nb") == "<p>a</p><hr><p>b</p>"

    def test_code_block_is_raw_and_escaped(self):
        source = "{code:python}\nif a < b:\n    print('*x*')\n{code}"
        assert html(source) == "<pre><code class=\"language-python\">if a &lt; b:\n    print('*x*')</code></pre>"

    def test_code_block_language_parameter(self):
        assert html("{code:title=x.js|language=javascript}let a;{code}") == (
            '<pre><code class="language-javascript">let a;</code></pre>'
        )

    def test_code_block_without_language(self):
        assert html("{code}x{code}") == "<pre><code>x</code></pre>"

    def test_noformat(self):
        assert html("{noformat}\n*raw* _text_\n{noformat}") == "<pre><code>*raw* _text_</code></pre>"

    def test_quote_macro_and_bq(self):
        assert html("{quote}\nquoted *text*\n{quote}") == "<blockquote><p>quoted <strong>text</strong></p></blockquote>"
        assert html("bq. short quote") == "<blockquote><p>short quote</p></blockquote>"

    def test_panel_becomes_callout(self):
        result = html("{panel:title=Heads up}\nbody text\n{panel}")
        assert result.startswith('<div data-block-type="callout-component" data-logo-in-use="emoji"')
        assert "<p><strong>Heads up</strong></p><p>body text</p></div>" in result

    def test_code_inside_panel(self):
        result = html("{info}\n{code}x = 1{code}\n{info}")
        assert '<div data-block-type="callout-component"' in result
        assert "<pre><code>x = 1</code></pre></div>" in result

    def test_table(self):
        source = "||h1||h2||\n|a|[link|https://x.y]|\n|only|"
        assert html(source) == (
            "<table><tbody>"
            "<tr><th><p>h1</p></th><th><p>h2</p></th></tr>"
            '<tr><td><p>a</p></td><td><p><a href="https://x.y" target="_blank">link</a></p></td></tr>'
            "<tr><td><p>only</p></td><td><p></p></td></tr>"
            "</tbody></table>"
        )


@pytest.mark.unit
class TestLists:
    def test_nested_bullets(self):
        assert html("* a\n** b\n* c") == "<ul><li><p>a</p><ul><li><p>b</p></li></ul></li><li><p>c</p></li></ul>"

    def test_ordered_list_not_headings(self):
        assert html("# one\n# two") == "<ol><li><p>one</p></li><li><p>two</p></li></ol>"

    def test_mixed_ordered_and_bullets(self):
        assert html("# one\n#* sub\n# two") == (
            "<ol><li><p>one</p><ul><li><p>sub</p></li></ul></li><li><p>two</p></li></ol>"
        )

    def test_markdown_indented_dash_bullets(self):
        # Jira descriptions pasted from Markdown
        source = "- **Alpha**: First item.\n   - **Beta/Gamma**: Nested item."
        assert html(source) == (
            "<ul><li><p><strong>Alpha</strong>: First item.</p>"
            "<ul><li><p><strong>Beta/Gamma</strong>: Nested item.</p></li></ul></li></ul>"
        )

    def test_list_cannot_skip_levels(self):
        assert html("*** deep") == "<ul><li><p>deep</p></li></ul>"

    def test_bold_at_line_start_is_not_a_bullet(self):
        assert html("*bold* rest") == "<p><strong>bold</strong> rest</p>"

    def test_paragraph_after_list(self):
        assert html("* a\ntext") == "<ul><li><p>a</p></li></ul><p>text</p>"


@pytest.mark.unit
class TestInline:
    def test_emphasis(self):
        assert html("*bold* _italic_ +under+ -strike- {{mono}} ??cite??") == (
            "<p><strong>bold</strong> <em>italic</em> <u>under</u> <s>strike</s> <code>mono</code> <em>cite</em></p>"
        )

    def test_markdown_double_star_bold(self):
        assert html("**bold** text") == "<p><strong>bold</strong> text</p>"

    def test_word_internal_markers_stay_literal(self):
        text = "snake_case_word, well-known-thing, 2*3*4, a+b+c and x - y"
        assert html(text) == f"<p>{text}</p>"

    def test_italic_title(self):
        assert html("a book like _The Example_, chapters") == "<p>a book like <em>The Example</em>, chapters</p>"

    def test_literal_brackets_are_not_links(self):
        assert html("Press [Enter] to continue") == "<p>Press [Enter] to continue</p>"

    def test_monospace_content_is_not_formatted(self):
        assert html("{{*not bold*}}") == "<p><code>*not bold*</code></p>"

    def test_backslash_escapes(self):
        assert html("\\*not bold\\*") == "<p>*not bold*</p>"

    def test_html_is_escaped(self):
        assert html("<script>alert(1)</script> & co") == "<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; co</p>"

    def test_color_macro_keeps_text(self):
        assert html("{color:red}warning{color}") == "<p>warning</p>"

    def test_emoticons(self):
        assert html("done (/) failed (x)") == "<p>done \u2705 failed \u274c</p>"

    def test_attachment_image_becomes_text(self):
        assert html("!screenshot.png|thumbnail!") == "<p>[image: screenshot.png]</p>"


@pytest.mark.unit
class TestLinks:
    def test_labelled_link(self):
        assert html("[docs|https://example.com/a?b=1&c=2]") == (
            '<p><a href="https://example.com/a?b=1&amp;c=2" target="_blank">docs</a></p>'
        )

    def test_url_only_and_smart_link(self):
        assert (
            html("[https://example.com]")
            == '<p><a href="https://example.com" target="_blank">https://example.com</a></p>'
        )
        assert html("[https://youtu.be/x|https://youtu.be/x|smart-link]") == (
            '<p><a href="https://youtu.be/x" target="_blank">https://youtu.be/x</a></p>'
        )

    def test_markdown_link(self):
        assert html("[text](https://x.y/z)") == '<p><a href="https://x.y/z" target="_blank">text</a></p>'

    def test_bare_url_without_trailing_punctuation(self):
        assert html("see https://example.com/path.") == (
            '<p>see <a href="https://example.com/path" target="_blank">https://example.com/path</a>.</p>'
        )

    def test_unsafe_scheme_is_not_linked(self):
        assert html("[x|javascript:alert(1)]") == "<p>[x|javascript:alert(1)]</p>"

    def test_mention_with_resolver(self):
        result = html("hi [~accountid:abc123]", mention_resolver=lambda ident: ("user-uuid", "Jane Doe"))
        assert 'entity_identifier="user-uuid"' in result
        assert 'entity_name="user_mention"' in result
        assert result.startswith("<p>hi <mention-component ")

    def test_mention_without_resolver(self):
        assert html("hi [~accountid:abc123]") == "<p>hi @abc123</p>"
        assert html("hi [~jdoe]", mention_resolver=lambda ident: None) == "<p>hi @jdoe</p>"


@pytest.mark.unit
class TestSanitizedOutput:
    SAMPLE = (
        "h2. Plan\n"
        "Intro with *bold*, _italic_ and a [link|https://example.com].\n\n"
        "* first\n** nested\n# ordered\n\n"
        "||a||b||\n|1|2|\n\n"
        "{code:js}const x = '<b>';{code}\n"
        "{panel:title=T}inside{panel}\n"
        "<img src=x onerror=alert(1)>"
    )

    def test_sanitizer_keeps_everything(self):
        result = jira_wiki_to_html(self.SAMPLE)
        ok, _, clean = validate_html_content(result)
        assert ok
        assert clean == result

    def test_links_open_in_new_tab_and_script_is_text(self):
        result = jira_wiki_to_html(self.SAMPLE)
        assert 'target="_blank"' in result
        assert "<img" not in result
        assert "&lt;img src=x onerror=alert(1)&gt;" in result

    def test_description_fields(self):
        fields = description_fields("*x*")
        assert fields == {
            "description_html": "<p><strong>x</strong></p>",
            "description_json": {},
            "description_binary": None,
        }
