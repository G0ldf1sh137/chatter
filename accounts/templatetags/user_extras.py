from django import template

register = template.Library()


@register.filter
def at_username(username):
    return f"@{username}" if username else username
