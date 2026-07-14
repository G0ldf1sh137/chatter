import re

from .models import Tag

# Requires a word char immediately after '#' (no space) - this is exactly
# why it can never match an ATX heading, which requires a space after '#'
# per the CommonMark spec. (?<!\w) stops "C#" or "word#tag" from matching -
# a hashtag has to start at a word boundary.
HASHTAG_RE = re.compile(r"(?<!\w)#(\w+)")


def extract_hashtag_names(body):
    return {name.lower() for name in HASHTAG_RE.findall(body or "")}


def sync_post_tags(post, body):
    names = extract_hashtag_names(body)
    tags = [Tag.objects.get_or_create(name=name)[0] for name in names]
    post.tags.set(tags)
