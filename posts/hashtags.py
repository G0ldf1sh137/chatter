import re

from .models import Tag

# Requires a word char immediately after '#' (no space) - this is exactly
# why it can never match an ATX heading, which requires a space after '#'
# per the CommonMark spec. (?<!\w) stops "C#" or "word#tag" from matching -
# a hashtag has to start at a word boundary.
HASHTAG_RE = re.compile(r"(?<!\w)#(\w+)")

# Strips raw Markdown code syntax (fenced blocks, inline spans) before
# extraction - render_markdown's _linkify_hashtags protects code at the
# rendered-HTML level, but extraction runs on the raw source, so a literal
# "#include" in `inline code` or a fenced block needs its own guard here or
# it'd create a real (bogus) Tag even though it never renders as a link.
_CODE_RE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)


def extract_hashtag_names(body):
    body = _CODE_RE.sub("", body or "")
    return {name.lower() for name in HASHTAG_RE.findall(body)}


def sync_post_tags(post, body):
    names = extract_hashtag_names(body)
    tags = [Tag.objects.get_or_create(name=name)[0] for name in names]
    post.tags.set(tags)
