from zoneinfo import ZoneInfo

from django.utils import timezone


class ActivateUserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = getattr(getattr(request, "user", None), "profile", None)
        if profile is not None:
            timezone.activate(ZoneInfo(profile.timezone))
        else:
            timezone.deactivate()
        return self.get_response(request)
