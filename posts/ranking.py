from django.db.models import Sum
from django.utils import timezone

from .models import CommentVote, PostVote

# Weights are tunable knobs, not derived from a formal model. Post karma is the
# strongest signal since it's a direct vote on the content itself; comment karma is
# weaker since it reflects on the discussion more than the post; poster karma is
# weakest since it's only a mild prior favoring generally well-regarded authors - a
# single post shouldn't rank mostly on its author's reputation.
POST_KARMA_WEIGHT = 1.0
COMMENT_KARMA_WEIGHT = 0.5
POSTER_KARMA_WEIGHT = 0.1

# Hacker News-style decay: dividing by (age_hours + 2) ** GRAVITY means a post's rank
# fades over time even if its karma never changes, so a recent post can outrank an
# older, higher-karma one once the old one has aged enough - "hot", not just
# "most upvoted ever".
GRAVITY = 1.8


def rank_posts(queryset):
    """Ranks an annotate_votes()'d Post queryset by a weighted, time-decayed blend of
    the post's own karma (post.score), the karma earned by its comment thread, and
    the poster's overall karma (across all of their posts and comments).

    Runs in Python after a single fetch rather than as one big annotate() because
    summing two different reverse relations (PostVote and CommentVote, joined via two
    different paths from Post) in the same query causes a join fan-out that silently
    inflates both sums. Keeping them as separate grouped-aggregate queries sidesteps
    that without sacrificing correctness - proportionate for this app's scale, though
    it does mean ranking is recomputed over every post on each feed load rather than
    pre-sorted at the database level.
    """
    posts = list(queryset)
    if not posts:
        return posts

    post_ids = [post.pk for post in posts]
    author_ids = {post.author_id for post in posts}

    comment_karma_by_post = dict(
        CommentVote.objects.filter(comment__post_id__in=post_ids)
        .values("comment__post_id")
        .annotate(total=Sum("value"))
        .values_list("comment__post_id", "total")
    )
    post_karma_by_author = dict(
        PostVote.objects.filter(post__author_id__in=author_ids)
        .values("post__author_id")
        .annotate(total=Sum("value"))
        .values_list("post__author_id", "total")
    )
    comment_karma_by_author = dict(
        CommentVote.objects.filter(comment__author_id__in=author_ids)
        .values("comment__author_id")
        .annotate(total=Sum("value"))
        .values_list("comment__author_id", "total")
    )

    now = timezone.now()
    for post in posts:
        comment_karma = comment_karma_by_post.get(post.pk, 0)
        poster_karma = post_karma_by_author.get(post.author_id, 0) + comment_karma_by_author.get(post.author_id, 0)
        age_hours = max((now - post.created_at).total_seconds() / 3600, 0)
        weighted_karma = (
            POST_KARMA_WEIGHT * post.score
            + COMMENT_KARMA_WEIGHT * comment_karma
            + POSTER_KARMA_WEIGHT * poster_karma
        )
        post.rank_score = weighted_karma / (age_hours + 2) ** GRAVITY

    posts.sort(key=lambda post: (post.rank_score, post.created_at), reverse=True)
    return posts
