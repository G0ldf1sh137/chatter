from django.urls import path

from . import views

urlpatterns = [
    path("", views.GamesHubView.as_view(), name="games-hub"),
]
