from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User

from .models import Profile


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Already linked to a user - nothing to resolve.
        if sociallogin.is_existing:
            return

        email = sociallogin.user.email
        if not email:
            return

        # Google has already verified this email belongs to whoever is
        # signing in, so treat it as proof of ownership: connect this
        # login to the existing account instead of allauth's default
        # conflict-resolution signup form. Skip silently if more than one
        # account somehow shares the address rather than guessing which.
        try:
            existing_user = User.objects.get(email__iexact=email)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return

        sociallogin.connect(request, existing_user)
        profile, _ = Profile.objects.get_or_create(user=existing_user)
        if not profile.email_verified:
            profile.email_verified = True
            profile.save(update_fields=["email_verified"])
