import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)  # normalized lowercase, no leading '#'

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"#{self.name}"


class Post(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts")
    body = models.TextField(max_length=5000)
    image = models.ImageField(upload_to="post_images/", blank=True)
    tags = models.ManyToManyField(Tag, related_name="posts", blank=True)
    edited = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"])]

    def __str__(self):
        return f"Post({self.pk}) by {self.author}"

    def get_absolute_url(self):
        return reverse("post-detail", kwargs={"pk": self.pk})

    def first_line(self):
        lines = self.body.strip().splitlines()
        return lines[0] if lines else ""


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    body = models.TextField()
    edited = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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


class Reaction(models.Model):
    class Emoji(models.TextChoices):
        THUMBSUP = "thumbsup", "👍"
        HEART = "heart", "❤️"
        LAUGH = "laugh", "😂"
        PARTY = "party", "🎉"
        WOW = "wow", "😮"
        SAD = "sad", "😢"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10, choices=Emoji.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class PostReaction(Reaction):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_post_reaction")]

    def __str__(self):
        return f"{self.user} reacted {self.emoji} to Post({self.post_id})"


class CommentReaction(Reaction):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="reactions")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "comment"], name="unique_comment_reaction")]

    def __str__(self):
        return f"{self.user} reacted {self.emoji} to Comment({self.comment_id})"


class Poll(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name="poll")
    question = models.CharField(max_length=300)

    def __str__(self):
        return f"Poll({self.pk}) on Post({self.post_id})"


class PollOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text


class PollVote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Denormalized from option.poll so uniqueness can be enforced per-poll
    # rather than per-option - a per-option constraint would let one user
    # vote for two different options in the same poll.
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "poll"], name="unique_poll_vote")]

    def __str__(self):
        return f"{self.user} voted {self.option} in Poll({self.poll_id})"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Always stored with user1_id < user2_id (see views.get_or_create_conversation)
    # so a conversation between two users is a single row no matter who
    # started it - a plain UniqueConstraint on an unordered pair can't
    # enforce that on its own.
    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user1")
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_user2")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user1", "user2"], name="unique_conversation"),
            models.CheckConstraint(check=~models.Q(user1=models.F("user2")), name="no_self_conversation"),
        ]

    def __str__(self):
        return f"Conversation({self.pk}): {self.user1} & {self.user2}"

    def other_participant(self, user):
        return self.user2 if user.id == self.user1_id else self.user1


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    # blank=True since a message can be image-only - see MessageForm.clean()
    # for the "at least one of body/image" requirement.
    body = models.TextField(max_length=5000, blank=True)
    image = models.ImageField(upload_to="message_images/", blank=True)
    # Whether the *other* participant has read it - a conversation only ever
    # has two people, so there's no need for a per-recipient read-receipt
    # table the way a group chat would need.
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"Message({self.pk}) from {self.sender} in Conversation({self.conversation_id})"


class SavedPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_posts")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_saved_post")]

    def __str__(self):
        return f"{self.user} saved {self.post_id}"


class Repost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reposts")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reposts")
    # Optional quote commentary - see PostQuoteView. Blank for a plain repost.
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_repost")]

    def __str__(self):
        return f"{self.user} reposted {self.post_id}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        MENTION = "mention", "Mention"
        REPLY = "reply", "Reply"
        UPVOTE = "upvote", "Upvote"
        REPOST = "repost", "Repost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MENTION)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    # Set only when the notification is about a comment (a mention or reply
    # inside one, or an upvote on one) rather than the post itself - `post`
    # is always set either way, since it's the natural landing page for both.
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    read = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read"])]

    def __str__(self):
        return f"Notification({self.pk}): {self.actor} -> {self.recipient} ({self.kind})"


class Report(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_filed")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reports")
    # Set only when the report is about a comment rather than the post itself -
    # `post` is always set either way, the same convention Notification.comment uses.
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report({self.pk}) by {self.reporter} on Post({self.post_id})"
