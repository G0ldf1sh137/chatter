from django.contrib import admin

from .models import Comment, CommentVote, Post, PostVote

admin.site.register(Post)
admin.site.register(Comment)
admin.site.register(PostVote)
admin.site.register(CommentVote)
