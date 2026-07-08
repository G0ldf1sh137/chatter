from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Comment, CommentVote, Post, PostVote


@receiver(post_save, sender=Post)
def auto_upvote_own_post(sender, instance, created, **kwargs):
    if created:
        PostVote.objects.get_or_create(user=instance.author, post=instance, defaults={"value": PostVote.UP})


@receiver(post_save, sender=Comment)
def auto_upvote_own_comment(sender, instance, created, **kwargs):
    if created:
        CommentVote.objects.get_or_create(
            user=instance.author, comment=instance, defaults={"value": CommentVote.UP}
        )
