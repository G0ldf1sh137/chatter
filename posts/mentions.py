import re
from functools import reduce
from operator import or_

from django.contrib.auth.models import User
from django.db.models import Q

# Matches the same character set Django's username validator allows minus
# '@' itself (NoAtSignInUsernameMixin, accounts/forms.py) - '@' can't appear
# inside a real username, so it unambiguously starts a mention token.
MENTION_RE = re.compile(r"@([\w.+-]+)")


def extract_mentioned_users(body, exclude=None):
    usernames = set(MENTION_RE.findall(body or ""))
    if not usernames:
        return []
    # Case-insensitive per token, same as UserSearchView's istartswith - a
    # mention typed in the wrong case should still resolve to the real user.
    query = reduce(or_, (Q(username__iexact=username) for username in usernames))
    users = User.objects.filter(query)
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    return list(users)
