from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email", "first_name", "last_name"]


class ResendVerificationForm(forms.Form):
    email = forms.EmailField()


class EmailVerifiedAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        profile = getattr(user, "profile", None)
        if profile is not None and not profile.email_verified:
            raise forms.ValidationError(
                "Please verify your email before logging in. Check your inbox, or "
                "request a new verification link.",
                code="email_not_verified",
            )


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name"]


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
