from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class NoAtSignInUsernameMixin:
    # '@' is reserved for referencing a username elsewhere (e.g. @mentions),
    # so it can't be part of the username itself - Django's own username
    # validator otherwise allows it alongside letters/digits/./+/-/_.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Required. 150 characters or fewer. Letters, digits and ./+/-/_ only."

    def clean_username(self):
        username = self.cleaned_data.get("username", "")
        if "@" in username:
            raise forms.ValidationError("Usernames can't contain the '@' symbol.")
        return username


class RegistrationForm(NoAtSignInUsernameMixin, UserCreationForm):
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


class UserProfileForm(NoAtSignInUsernameMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "bio",
            "avatar",
            "timezone",
            "notify_on_mentions",
            "notify_on_replies",
            "notify_on_upvotes",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size") and avatar.size > settings.MAX_AVATAR_UPLOAD_SIZE:
            max_mb = settings.MAX_AVATAR_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"Image must be smaller than {max_mb}MB.")
        return avatar
