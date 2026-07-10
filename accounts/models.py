import uuid
import zoneinfo

from django.conf import settings
from django.db import models

TIMEZONE_CHOICES = sorted((tz, tz) for tz in zoneinfo.available_timezones())


class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    email_verified = models.BooleanField(default=False)
    timezone = models.CharField(max_length=64, choices=TIMEZONE_CHOICES, default="UTC")
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
