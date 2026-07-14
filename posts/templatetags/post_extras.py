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


@register.filter(name="poll_results")
def poll_results(poll, viewer):
    # Reads only poll.options.all() / option.votes.all() - both populated by
    # the "poll__options__votes" prefetch chain, so this is zero extra
    # queries per post, same as group_reactions above.
    options = list(poll.options.all())
    total = sum(len(o.votes.all()) for o in options)
    mine = next(
        (o.id for o in options if viewer.is_authenticated and any(v.user_id == viewer.id for v in o.votes.all())),
        None,
    )
    return {
        "total": total,
        "options": [
            {
                "id": o.id,
                "text": o.text,
                "count": len(o.votes.all()),
                "pct": round(100 * len(o.votes.all()) / total) if total else 0,
                "mine": o.id == mine,
            }
            for o in options
        ],
    }


@register.filter(name="poll_vote_count")
def poll_vote_count(poll):
    return sum(len(o.votes.all()) for o in poll.options.all())


@register.filter(name="repost_count")
def repost_count(post):
    return len(post.reposts.all())
