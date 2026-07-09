from django import forms

from .models import Comment, Message, Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6, "placeholder": "Markdown supported"}),
        }


class CommentForm(forms.ModelForm):
    parent = forms.UUIDField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Markdown supported"}),
        }


class CommentEditForm(forms.ModelForm):
    # No parent field - unlike CommentForm, editing never changes which
    # comment/post a reply is nested under, only its body.
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Markdown supported"}),
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 2, "placeholder": "Write a message... Markdown supported"}),
        }
