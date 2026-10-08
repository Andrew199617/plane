# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira wiki markup -> rich-text-editor HTML (Jira-parity importer).

`jira_wiki_to_html(text)` turns a Jira (Server/Cloud CSV export) wiki-markup description into the
HTML the work item description editor (Tiptap) loads from `description_html`:

Blocks
    h1. .. h6.                          <h1>..<h6>
    {code[:lang]} .. {code}             <pre><code class="language-lang">..</code></pre> (raw, escaped)
    {noformat} .. {noformat}            <pre><code>..</code></pre>
    {quote} .. {quote}, bq. text        <blockquote>..</blockquote>
    {panel[:title=T]} / {info} / {note} / {tip} / {warning} .. -> editor callout block
    * / ** / # / ## / #* lists, "- " and indented "   - " bullets -> nested <ul>/<ol>
    ||h||h|| and |c|c| rows             <table><tbody><tr><th>/<td> (cells hold <p>)
    ----                                <hr>
    blank line                          paragraph break; single newline -> <br>
Inline
    *bold* **bold** _italic_ ??citation?? +underline+ -strike- {{monospace}}
    [text|url] [url] [text|url|smart-link] [text](url) bare URLs   -> <a target="_blank">
    [~accountid:ID] / [~name]           <mention-component> (when a resolver maps it) else "@name"
    \\ line break, \\X escapes, {color:x}..{color} (text kept), emoticons (/) (x) (!) (?) (y) ...
    !image.png|..!                      "[image: image.png]" (attachments are not exported)

Anything that is not recognised stays literal text (e.g. "Press [Enter] to continue", snake_case words,
hyphenated-words, a lone "*"). All text is HTML-escaped and the final HTML goes through the same
sanitizer as API writes (plane.utils.content_validator.validate_html_content).

Work item descriptions in CE are not collaborative documents: the editor renders `description_html`
and regenerates `description_json` / `description_binary` on the first edit, so the importer stores
only `description_html` (see `description_fields`).
"""

# Python imports
import html
import re
import uuid

EMPTY_PARAGRAPH = "<p></p>"

# Private-use characters used as placeholder delimiters (never present in Jira text after cleanup).
_BLOCK_OPEN, _BLOCK_CLOSE = "\ue002", "\ue003"
_INLINE_OPEN, _INLINE_CLOSE = "\ue000", "\ue001"
_PRIVATE_USE_RE = re.compile("[\ue000-\ue003]")
_BLOCK_LINE_RE = re.compile(_BLOCK_OPEN + r"(\d+)" + _BLOCK_CLOSE)
_INLINE_TOKEN_RE = re.compile(_INLINE_OPEN + r"(\d+)" + _INLINE_CLOSE)

# ---------------------------------------------------------------- block patterns

_CODE_BLOCK_RE = re.compile(r"\{(code|noformat)((?::[^}\n]*)?)\}(.*?)\{\1\}", re.DOTALL | re.IGNORECASE)
_CONTAINER_RE = re.compile(
    r"\{(quote|panel|info|note|tip|warning)((?::[^}\n]*)?)\}(.*?)\{\1\}", re.DOTALL | re.IGNORECASE
)
_HEADING_RE = re.compile(r"^\s*h([1-6])\.(?:\s+(.*))?$")
_BQ_RE = re.compile(r"^\s*bq\.\s+(.*)$")
_HR_RE = re.compile(r"^\s*-{4,}\s*$")
_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[*#]+|-)[ \t]+(?P<text>\S.*)$")
_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_+#.-]{1,32}$")

# Callout emoji (decimal code point) per Jira panel macro; the editor default is the light bulb.
_CALLOUT_EMOJI = {
    "panel": ("128161", "1f4a1"),
    "info": ("128161", "1f4a1"),
    "tip": ("128161", "1f4a1"),
    "note": ("128221", "1f4dd"),
    "warning": ("128680", "1f6a8"),
}
_EMOJI_URL = "https://cdn.jsdelivr.net/npm/emoji-datasource-apple/img/apple/64/{}.png"

# ---------------------------------------------------------------- inline patterns

_ESCAPE_RE = re.compile(r"\\([*_+\-?^~{}\[\]!|#\\])")
_MONOSPACE_RE = re.compile(r"\{\{(.+?)\}\}")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\[\]\n]+)\]\(((?:https?://|mailto:)[^\s()]+)\)")
_BRACKET_RE = re.compile(r"\[([^\[\]\n]+)\]")
_IMAGE_RE = re.compile(r"(?<![\w!])!([^\s!|][^!\n|]*?\.[A-Za-z0-9]{2,5}|https?://[^\s!|]+)(?:\|[^!\n]*)?!")
_BARE_URL_RE = re.compile(r"(?<![\w/@\"'=])((?:https?|ftp)://[^\s<>\[\]|\"-]+[^\s<>\[\]|\".,;:!?)'*_-])")
_COLOR_RE = re.compile(r"\{color(?::[^}\n]*)?\}", re.IGNORECASE)
_DROP_MACRO_RE = re.compile(r"\{(?:anchor(?::[^}\n]*)?|toc(?::[^}\n]*)?)\}", re.IGNORECASE)
_URL_PREFIX_RE = re.compile(r"^(?:https?://|mailto:|ftp://)", re.IGNORECASE)

_EMOTICONS = {
    "(/)": "\u2705",
    "(x)": "\u274c",
    "(!)": "\u26a0\ufe0f",
    "(?)": "\u2753",
    "(y)": "\U0001f44d",
    "(n)": "\U0001f44e",
    "(i)": "\u2139\ufe0f",
    "(on)": "\U0001f4a1",
    "(off)": "\U0001f4a1",
    "(*)": "\u2b50",
    "(+)": "\u2795",
    "(-)": "\u2796",
}
_EMOTICON_RE = re.compile(
    r"(?<!\S)(" + "|".join(re.escape(k) for k in sorted(_EMOTICONS, key=len, reverse=True)) + r")(?=$|[\s.,;:!?])"
)

# Emphasis, applied to already-escaped text. Openers must not follow a word character and closers
# must not precede one, so snake_case, hyphenated-words, 2*3*4 and "- bullets" stay literal.
_EMPHASIS_RULES = (
    (re.compile(r"(?<![\w*])\*\*(?=[^\s*])(.+?)(?<=[^\s*])\*\*(?![\w*])"), "strong"),
    (re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])"), "strong"),
    (re.compile(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])"), "em"),
    (re.compile(r"(?<![\w?])\?\?(?=[^\s?])(.+?)(?<=[^\s?])\?\?(?![\w?])"), "em"),
    (re.compile(r"(?<![\w+])\+(?=[^\s+])(.+?)(?<=[^\s+])\+(?![\w+])"), "u"),
    (re.compile(r"(?<![\w-])-(?=[^\s-])(.+?)(?<=[^\s-])-(?![\w-])"), "s"),
)
_EM_DASH_RE = re.compile(r"(?<=\s)---(?=\s)")
_EN_DASH_RE = re.compile(r"(?<=\s)--(?=\s)")


def _escape(text):
    return html.escape(text, quote=False)


def _escape_attr(value):
    return html.escape(str(value), quote=True)


def _normalize_url(url):
    url = url.strip()
    if url.lower().startswith("www."):
        url = "https://" + url
    if not _URL_PREFIX_RE.match(url):
        return None
    if any(ch in url for ch in '\n\r\t <>"'):
        return None
    return url


class _Converter:
    def __init__(self, mention_resolver=None):
        self.mention_resolver = mention_resolver
        self.blocks = []

    # ------------------------------------------------------------ entry point

    def convert(self, text):
        text = _PRIVATE_USE_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
        text = self._extract_code_blocks(text)
        body = self._convert_fragment(text)
        return self._restore_blocks(body)

    def _convert_fragment(self, text):
        text = self._extract_containers(text)
        return self._convert_lines(text.split("\n"))

    # ------------------------------------------------------------ placeholders

    def _block_placeholder(self, block_html):
        self.blocks.append(block_html)
        return "\n" + _BLOCK_OPEN + str(len(self.blocks) - 1) + _BLOCK_CLOSE + "\n"

    def _restore_blocks(self, body):
        # Containers may hold other placeholders (e.g. a {code} inside a {panel}); loop until stable.
        for _ in range(10):
            restored = _BLOCK_LINE_RE.sub(lambda m: self.blocks[int(m.group(1))], body)
            if restored == body:
                break
            body = restored
        return body

    # ------------------------------------------------------------ block macros

    def _extract_code_blocks(self, text):
        def replace(match):
            macro = match.group(1).lower()
            params = match.group(2)[1:] if match.group(2) else ""
            content = match.group(3)
            if content.startswith("\n"):
                content = content[1:]
            if content.endswith("\n"):
                content = content[:-1]
            language = ""
            if macro == "code":
                for index, param in enumerate(p.strip() for p in params.split("|") if p.strip()):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        if key.strip().lower() in ("language", "lang"):
                            language = value.strip()
                    elif index == 0:
                        language = param
            language = language if _LANGUAGE_RE.match(language or "") else ""
            code_attr = f' class="language-{_escape_attr(language.lower())}"' if language else ""
            return self._block_placeholder(f"<pre><code{code_attr}>{_escape(content)}</code></pre>")

        return _CODE_BLOCK_RE.sub(replace, text)

    def _extract_containers(self, text):
        def replace(match):
            macro = match.group(1).lower()
            params = match.group(2)[1:] if match.group(2) else ""
            inner_html = self._convert_fragment(match.group(3).strip("\n")) or EMPTY_PARAGRAPH
            if macro == "quote":
                return self._block_placeholder(f"<blockquote>{inner_html}</blockquote>")
            title = ""
            for param in params.split("|"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    if key.strip().lower() == "title" and value.strip():
                        title = value.strip()
            unicode_value, hex_value = _CALLOUT_EMOJI.get(macro, _CALLOUT_EMOJI["panel"])
            title_html = f"<p><strong>{self._inline(title)}</strong></p>" if title else ""
            return self._block_placeholder(
                '<div data-block-type="callout-component" data-logo-in-use="emoji" '
                f'data-emoji-unicode="{unicode_value}" data-emoji-url="{_EMOJI_URL.format(hex_value)}">'
                f"{title_html}{inner_html}</div>"
            )

        return _CONTAINER_RE.sub(replace, text)

    # ------------------------------------------------------------ line blocks

    def _convert_lines(self, lines):
        out = []
        paragraph, list_items, table_rows = [], [], []
        indent_stack = []

        def flush_paragraph():
            if paragraph:
                out.append("<p>" + "<br>".join(self._inline(line) for line in paragraph) + "</p>")
                paragraph.clear()

        def flush_list():
            if list_items:
                out.append(self._render_list(list_items))
                list_items.clear()
            indent_stack.clear()

        def flush_table():
            if table_rows:
                out.append(self._render_table(table_rows))
                table_rows.clear()

        def flush_all():
            flush_paragraph()
            flush_list()
            flush_table()

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped:
                flush_all()
                continue

            block = _BLOCK_LINE_RE.fullmatch(stripped)
            if block:
                flush_all()
                out.append(stripped)
                continue

            heading = _HEADING_RE.match(line)
            if heading:
                flush_all()
                heading_text = (heading.group(2) or "").strip()
                if heading_text:
                    level = heading.group(1)
                    out.append(f"<h{level}>{self._inline(heading_text)}</h{level}>")
                continue

            quote = _BQ_RE.match(line)
            if quote:
                flush_all()
                out.append(f"<blockquote><p>{self._inline(quote.group(1).strip())}</p></blockquote>")
                continue

            if _HR_RE.match(line):
                flush_all()
                out.append("<hr>")
                continue

            if stripped.startswith("|"):
                flush_paragraph()
                flush_list()
                table_rows.append(self._parse_table_row(stripped))
                continue

            list_match = _LIST_RE.match(line)
            if list_match:
                flush_paragraph()
                flush_table()
                list_items.append(self._list_item(list_match, list_items, indent_stack))
                continue

            flush_list()
            flush_table()
            paragraph.append(stripped)

        flush_all()
        return "".join(out)

    # ------------------------------------------------------------ lists

    @staticmethod
    def _list_item(match, previous_items, indent_stack):
        marker = match.group("marker")
        text = match.group("text").strip()
        if len(marker) > 1:
            depth = len(marker)
            types = ["ol" if ch == "#" else "ul" for ch in marker]
        else:
            # Single marker: nesting comes from indentation (Markdown-style "   - item").
            indent = len(match.group("indent").expandtabs(4))
            while indent_stack and indent < indent_stack[-1][0]:
                indent_stack.pop()
            if indent_stack and indent == indent_stack[-1][0]:
                depth = indent_stack[-1][1]
            elif indent_stack:
                depth = indent_stack[-1][1] + 1
                indent_stack.append((indent, depth))
            else:
                depth = 1
                indent_stack.append((indent, depth))
            types = ["ol" if marker == "#" else "ul"] * depth
        # A list cannot skip levels: clamp to one deeper than the previous item.
        previous_depth = previous_items[-1][0] if previous_items else 0
        if depth > previous_depth + 1:
            depth = previous_depth + 1
            types = types[:depth]
        return depth, types[depth - 1], text

    def _render_list(self, items):
        out, stack = [], []
        for depth, list_type, text in items:
            while len(stack) > depth:
                out.append(f"</li></{stack.pop()}>")
            if len(stack) == depth:
                if stack[-1] == list_type:
                    out.append("</li><li>")
                else:
                    out.append(f"</li></{stack.pop()}>")
                    out.append(f"<{list_type}><li>")
                    stack.append(list_type)
            while len(stack) < depth:
                out.append(f"<{list_type}><li>")
                stack.append(list_type)
            out.append(f"<p>{self._inline(text)}</p>")
        while stack:
            out.append(f"</li></{stack.pop()}>")
        return "".join(out)

    # ------------------------------------------------------------ tables

    @staticmethod
    def _parse_table_row(line):
        cells = []
        index, length = 0, len(line)
        while index < length:
            if line.startswith("||", index):
                is_header, index = True, index + 2
            elif line[index] == "|":
                is_header, index = False, index + 1
            else:
                is_header = False
            start, depth_link, depth_mono = index, 0, 0
            while index < length:
                if line.startswith("{{", index):
                    depth_mono += 1
                    index += 2
                    continue
                if line.startswith("}}", index) and depth_mono:
                    depth_mono -= 1
                    index += 2
                    continue
                char = line[index]
                if char == "\\" and index + 1 < length:
                    index += 2
                    continue
                if char == "[":
                    depth_link += 1
                elif char == "]" and depth_link:
                    depth_link -= 1
                elif char == "|" and not depth_link and not depth_mono:
                    break
                index += 1
            content = line[start:index]
            if index >= length and not content.strip():
                break
            cells.append((is_header, content.strip()))
        return cells

    def _render_table(self, rows):
        width = max((len(row) for row in rows), default=0)
        if not width:
            return ""
        out = ["<table><tbody>"]
        for row in rows:
            out.append("<tr>")
            for is_header, content in row + [(False, "")] * (width - len(row)):
                tag = "th" if is_header else "td"
                out.append(f"<{tag}><p>{self._inline(content)}</p></{tag}>")
            out.append("</tr>")
        out.append("</tbody></table>")
        return "".join(out)

    # ------------------------------------------------------------ inline

    def _inline(self, text, allow_links=True):
        tokens = []

        def protect(fragment_html):
            tokens.append(fragment_html)
            return _INLINE_OPEN + str(len(tokens) - 1) + _INLINE_CLOSE

        text = text.replace("\\\\", protect("<br>"))
        text = _ESCAPE_RE.sub(lambda m: protect(_escape(m.group(1))), text)
        text = _MONOSPACE_RE.sub(lambda m: protect(f"<code>{_escape(m.group(1))}</code>"), text)
        text = _COLOR_RE.sub("", text)
        text = _DROP_MACRO_RE.sub("", text)

        if allow_links:
            text = _MARKDOWN_LINK_RE.sub(
                lambda m: protect(self._link_html(m.group(2), m.group(1)))
                if _normalize_url(m.group(2))
                else m.group(0),
                text,
            )
            text = _BRACKET_RE.sub(lambda m: self._bracket(m, protect), text)
            text = _IMAGE_RE.sub(lambda m: protect(self._image_html(m.group(1))), text)
            text = _BARE_URL_RE.sub(lambda m: protect(self._link_html(m.group(1), None)), text)

        text = _EMOTICON_RE.sub(lambda m: protect(_EMOTICONS[m.group(1)]), text)

        text = _escape(text)
        text = _EM_DASH_RE.sub("\u2014", text)
        text = _EN_DASH_RE.sub("\u2013", text)
        for pattern, tag in _EMPHASIS_RULES:
            text = pattern.sub(lambda m, tag=tag: f"<{tag}>{m.group(1)}</{tag}>", text)

        return _INLINE_TOKEN_RE.sub(lambda m: tokens[int(m.group(1))], text)

    def _link_html(self, url, label):
        href = _normalize_url(url)
        if href is None:
            return _escape(label or url)
        label = (label or "").strip()
        label_html = self._inline(label, allow_links=False) if label and label != url.strip() else _escape(url)
        return f'<a href="{_escape_attr(href)}" target="_blank">{label_html}</a>'

    def _bracket(self, match, protect):
        content = match.group(1)
        stripped = content.strip()
        if stripped.startswith("~"):
            return protect(self._mention_html(stripped[1:]))
        if stripped.startswith("^"):
            return protect(_escape(stripped[1:]))
        if stripped.startswith("#"):
            return protect(_escape(stripped[1:]))
        if "|" in stripped:
            parts = stripped.split("|")
            label, target = parts[0].strip(), parts[1].strip()
            if target.startswith("~"):
                return protect(self._mention_html(target[1:], label))
            if target.startswith(("^", "#")):
                return protect(_escape(label or target[1:]))
            if _normalize_url(target):
                return protect(self._link_html(target, label or None))
            return match.group(0)
        if _normalize_url(stripped):
            return protect(self._link_html(stripped, None))
        return match.group(0)

    def _mention_html(self, identifier, label=None):
        identifier = identifier.strip()
        resolved = self.mention_resolver(identifier) if self.mention_resolver else None
        user_id, display_name = (resolved or (None, None))[:2]
        if user_id:
            return (
                f'<mention-component id="{uuid.uuid4()}" entity_identifier="{_escape_attr(user_id)}" '
                'entity_name="user_mention"></mention-component>'
            )
        name = display_name or label or identifier.split(":", 1)[-1]
        return _escape("@" + name)

    def _image_html(self, source):
        if _normalize_url(source):
            return self._link_html(source, None)
        return _escape(f"[image: {source}]")


def jira_wiki_to_html(text, mention_resolver=None, sanitize=True):
    """Convert Jira wiki markup to editor HTML.

    Args:
        text: the Jira wiki markup (None/blank -> "<p></p>").
        mention_resolver: optional callable(identifier) -> (user_id | None, display_name | None) | None,
            called with "accountid:XXXX" or "username" for [~...] mentions.
        sanitize: run the result through validate_html_content (the API's HTML sanitizer).

    Returns:
        HTML string; never empty ("<p></p>" for blank input).
    """
    if text is None or not str(text).strip():
        return EMPTY_PARAGRAPH
    body = _Converter(mention_resolver).convert(str(text))
    if not body.strip():
        return EMPTY_PARAGRAPH
    if sanitize:
        from plane.utils.content_validator import validate_html_content

        is_valid, _, clean_html = validate_html_content(body)
        if not is_valid or clean_html is None:
            return "<p>" + _escape(str(text).strip()) + "</p>"
        body = clean_html
    return body or EMPTY_PARAGRAPH


def description_fields(text, mention_resolver=None):
    """Issue model kwargs for an imported description.

    The CE work item editor loads `description_html`; `description_json` / `description_binary` are
    regenerated by the editor on the first edit, so they are left empty (NULL binary) on import.
    `description_stripped` is filled by Issue.save().
    """
    return {
        "description_html": jira_wiki_to_html(text, mention_resolver=mention_resolver),
        "description_json": {},
        "description_binary": None,
    }
