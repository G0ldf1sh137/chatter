from django.contrib import admin

from .models import Comment, CommentVote, Post, PostVote, Report

admin.site.register(Post)
admin.site.register(Comment)
admin.site.register(PostVote)
admin.site.register(CommentVote)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "reporter", "post", "comment", "status", "reason")
    list_filter = ("status",)
    list_editable = ("status",)
    ordering = ("-created_at",)
