from django.urls import path

from . import views
from .models import CommentVote, PostVote

urlpatterns = [
    path("", views.FeedView.as_view(), name="feed"),
    path("following/", views.FollowingFeedView.as_view(), name="following-feed"),
    path("posts/new/", views.PostCreateView.as_view(), name="post-create"),
    path("posts/<uuid:pk>/", views.PostDetailView.as_view(), name="post-detail"),
    path("posts/<uuid:pk>/edit/", views.PostEditView.as_view(), name="post-edit"),
    path("posts/<uuid:pk>/comment/", views.CommentCreateView.as_view(), name="comment-create"),
    path("comments/<uuid:pk>/edit/", views.CommentEditView.as_view(), name="comment-edit"),
    path(
        "posts/<uuid:pk>/upvote/",
        views.PostVoteView.as_view(value=PostVote.UP),
        name="post-upvote",
    ),
    path(
        "posts/<uuid:pk>/downvote/",
        views.PostVoteView.as_view(value=PostVote.DOWN),
        name="post-downvote",
    ),
    path(
        "comments/<uuid:pk>/upvote/",
        views.CommentVoteView.as_view(value=CommentVote.UP),
        name="comment-upvote",
    ),
    path(
        "comments/<uuid:pk>/downvote/",
        views.CommentVoteView.as_view(value=CommentVote.DOWN),
        name="comment-downvote",
    ),
]
