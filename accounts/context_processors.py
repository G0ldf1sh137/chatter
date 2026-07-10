from django.contrib.auth.models import User


def site_admin(request):
    if not request.user.is_authenticated:
        return {}
    return {"site_admin": User.objects.filter(is_superuser=True).order_by("date_joined").first()}
