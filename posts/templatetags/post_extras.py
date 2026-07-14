from collections import Counter

from django import template
from django.utils.safestring import mark_safe

from posts.markdown import render_markdown
from posts.models import PostReaction

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    return mark_safe(render_markdown(text))


@register.filter(name="markdown_preview")
def markdown_preview_filter(text):
    # For snippets wrapped in their own <a> (card previews linking to the
    # full post) - see render_markdown's linkify_hashtags docstring.
    return mark_safe(render_markdown(text, linkify_hashtags=False))


@register.filter(name="group_reactions")
def group_reactions(reactions, viewer):
    # `reactions` is a post's already-prefetched .reactions.all() - grouping
    # here (not via a queryset annotation) avoids the join fan-out
    # posts/ranking.py's own docstring warns about when combining multiple
    # reverse-relation aggregates in one query.
    counts = Counter(r.emoji for r in reactions)
    mine = next((r.emoji for r in reactions if viewer.is_authenticated and r.user_id == viewer.id), None)
    return [
        {"value": value, "glyph": glyph, "count": counts.get(value, 0), "mine": value == mine}
        for value, glyph in PostReaction.Emoji.choices
    ]
