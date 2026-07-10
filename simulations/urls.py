from django.urls import path

from . import views

urlpatterns = [
    path("", views.SimulationHubView.as_view(), name="simulations-hub"),
    path("<slug:slug>/", views.SimulationDetailView.as_view(), name="simulation-detail"),
]
