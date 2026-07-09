import nh3
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

# nowrap=True so this returns just the highlighted spans - the fence()
# renderer below supplies its own <pre>/<code>, and only treats a highlight
# result as pre-formatted if it already starts with "<pre".
_formatter = HtmlFormatter(nowrap=True)


def _highlight_code(code, lang, _attrs):
    # No language tag (a bare ``` fence) falls through to markdown-it's own
    # escaped, unhighlighted <pre><code> - guessing a lexer from content
    # alone is unreliable and would risk mislabeling plain text/output as
    # some unrelated language.
    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    highlighted = highlight(code, lexer, _formatter)
    return f'<pre class="highlight"><code class="language-{lang}">{highlighted}</code></pre>'


_md = MarkdownIt("commonmark", {"html": False, "linkify": True, "highlight": _highlight_code}).enable(
    ["table", "strikethrough", "linkify"]
)

_ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "del", "s",
    "ul", "ol", "li",
    "blockquote", "pre", "code", "span",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
}

_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "pre": {"class"},
    "code": {"class"},
    "span": {"class"},
}


def render_markdown(text: str) -> str:
    html = _md.render(text or "")
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        link_rel="nofollow noopener",
    )
