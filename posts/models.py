from django.conf import settings
from django.db import models
from django.urls import reverse


class Post(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts")
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"])]

    def __str__(self):
        return f"Post({self.pk}) by {self.author}"

    def get_absolute_url(self):
        return reverse("post-detail", kwargs={"pk": self.pk})


class Comment(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["post", "created_at"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"Comment({self.pk}) by {self.author} on Post({self.post_id})"


class Vote(models.Model):
    UP = 1
    DOWN = -1
    VALUE_CHOICES = [(UP, "Upvote"), (DOWN, "Downvote")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    value = models.SmallIntegerField(choices=VALUE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class PostVote(Vote):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_post_vote")]

    def __str__(self):
        return f"{self.user} {self.get_value_display()}d Post({self.post_id})"


class CommentVote(Vote):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "comment"], name="unique_comment_vote")]

    def __str__(self):
        return f"{self.user} {self.get_value_display()}d Comment({self.comment_id})"
