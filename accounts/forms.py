from django import forms
from django.conf import settings

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["bio", "avatar"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size") and avatar.size > settings.MAX_AVATAR_UPLOAD_SIZE:
            max_mb = settings.MAX_AVATAR_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"Image must be smaller than {max_mb}MB.")
        return avatar
