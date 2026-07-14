from django import forms
from django.conf import settings

from .models import Comment, Message, Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["body", "image"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6, "placeholder": "Markdown supported"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size") and image.size > settings.MAX_POST_IMAGE_UPLOAD_SIZE:
            max_mb = settings.MAX_POST_IMAGE_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"Image must be smaller than {max_mb}MB.")
        return image


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
        fields = ["body", "image"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 2, "placeholder": "Write a message... Markdown supported"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size") and image.size > settings.MAX_MESSAGE_IMAGE_UPLOAD_SIZE:
            max_mb = settings.MAX_MESSAGE_IMAGE_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"Image must be smaller than {max_mb}MB.")
        return image

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("body") and not cleaned_data.get("image"):
            raise forms.ValidationError("Message can't be empty.")
        return cleaned_data
