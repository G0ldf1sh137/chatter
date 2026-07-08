from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from .tokens import generate_verification_token


def send_verification_email(request, user):
    token = generate_verification_token(user)
    verify_url = request.build_absolute_uri(reverse("verify-email", args=[token]))
    body = render_to_string(
        "accounts/emails/verification_email.txt",
        {"user": user, "verify_url": verify_url},
    )
    send_mail(
        subject="Verify your Chatter account",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
