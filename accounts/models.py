import uuid
import zoneinfo

from django.conf import settings
from django.db import models

from posts.models import Post

TIMEZONE_CHOICES = sorted((tz, tz) for tz in zoneinfo.available_timezones())


class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    email_verified = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, choices=TIMEZONE_CHOICES, default="UTC")
    notify_on_mentions = models.BooleanField(default=True, verbose_name="Notify me when I'm mentioned")
    notify_on_replies = models.BooleanField(default=True, verbose_name="Notify me on replies")
    notify_on_upvotes = models.BooleanField(default=True, verbose_name="Notify me on upvotes")
    notify_on_reposts = models.BooleanField(default=True, verbose_name="Notify me on reposts")
    pinned_post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"


class Follow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following")
    followed = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "followed"], name="unique_follow"),
            models.CheckConstraint(check=~models.Q(follower=models.F("followed")), name="no_self_follow"),
        ]

    def __str__(self):
        return f"{self.follower} follows {self.followed}"


class Mute(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    muter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="muting")
    muted = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="muted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["muter", "muted"], name="unique_mute"),
            models.CheckConstraint(check=~models.Q(muter=models.F("muted")), name="no_self_mute"),
        ]

    def __str__(self):
        return f"{self.muter} muted {self.muted}"


class Block(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocking")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(check=~models.Q(blocker=models.F("blocked")), name="no_self_block"),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


def is_muted_or_blocked(viewer, other):
    # Shared by feed filtering and notification suppression - Mute and Block
    # have identical effects for both of those, so this is the one place
    # that checks both tables rather than duplicating it at each call site.
    return (
        Mute.objects.filter(muter=viewer, muted=other).exists()
        or Block.objects.filter(blocker=viewer, blocked=other).exists()
    )


def is_blocked_either_way(user_a, user_b):
    return Block.objects.filter(
        models.Q(blocker=user_a, blocked=user_b) | models.Q(blocker=user_b, blocked=user_a)
    ).exists()
