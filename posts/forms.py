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


class PollForm(forms.Form):
    # Plain Form, not a ModelForm/formset - a poll has a fixed 2-4 option
    # shape for v1, so four explicit fields keep the create page a single
    # POST without formset management-form plumbing. Leaving every field
    # blank means "no poll" rather than a validation error.
    question = forms.CharField(max_length=300, required=False)
    option_1 = forms.CharField(max_length=120, required=False)
    option_2 = forms.CharField(max_length=120, required=False)
    option_3 = forms.CharField(max_length=120, required=False)
    option_4 = forms.CharField(max_length=120, required=False)

    def clean(self):
        cleaned = super().clean()
        question = (cleaned.get("question") or "").strip()
        options = [(cleaned.get(f"option_{i}") or "").strip() for i in range(1, 5)]
        options = [o for o in options if o]
        if not question and not options:
            return cleaned
        if not question:
            raise forms.ValidationError("Poll question is required.")
        if len(set(options)) < len(options):
            raise forms.ValidationError("Poll options must be unique.")
        if len(options) < 2:
            raise forms.ValidationError("A poll needs at least 2 options.")
        cleaned["poll_options"] = options
        cleaned["has_poll"] = True
        return cleaned


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
