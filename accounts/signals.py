from allauth.account.signals import user_signed_up
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(user_signed_up)
def mark_social_signup_verified(request, user, **kwargs):
    # Only fires via allauth's own signup flow (social login here, since
    # RegisterView is a plain Django view) - Google already verified the
    # email, so there's nothing for our own verification flow to add.
    if kwargs.get("sociallogin") is not None:
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
