from django import template
from django.utils.safestring import mark_safe

from posts.markdown import render_markdown

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    return mark_safe(render_markdown(text))


@register.filter(name="markdown_preview")
def markdown_preview_filter(text):
    # For snippets wrapped in their own <a> (card previews linking to the
    # full post) - see render_markdown's linkify_hashtags docstring.
    return mark_safe(render_markdown(text, linkify_hashtags=False))
