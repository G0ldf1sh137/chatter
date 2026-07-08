from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


class RegistrationTests(TestCase):
    def test_valid_signup_creates_user_and_profile(self):
        response = self.client.post(
            reverse("register"),
            {"username": "bob", "password1": "correct-horse-battery-staple", "password2": "correct-horse-battery-staple"},
        )
        self.assertRedirects(response, reverse("feed"))
        user = User.objects.get(username="bob")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_signup_logs_the_user_in(self):
        self.client.post(
            reverse("register"),
            {"username": "bob", "password1": "correct-horse-battery-staple", "password2": "correct-horse-battery-staple"},
        )
        response = self.client.get(reverse("feed"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="bob", password="correct-horse-battery-staple")
        response = self.client.post(
            reverse("register"),
            {"username": "bob", "password1": "correct-horse-battery-staple", "password2": "correct-horse-battery-staple"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="bob").count(), 1)
        self.assertFormError(response.context["form"], "username", "A user with that username already exists.")


class ProfileViewTests(TestCase):
    def test_profile_shows_bio_and_posts(self):
        user = User.objects.create_user(username="carol", password="correct-horse-battery-staple")
        Profile.objects.filter(user=user).update(bio="Hello, I'm Carol.")
        response = self.client.get(reverse("profile", args=["carol"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hello, I&#x27;m Carol.")
