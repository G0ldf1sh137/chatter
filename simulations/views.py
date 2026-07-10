from django.http import Http404
from django.views.generic import TemplateView

from .registry import SIMULATIONS, get_simulation


class SimulationHubView(TemplateView):
    template_name = "simulations/hub.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["simulations"] = SIMULATIONS
        return context


class SimulationDetailView(TemplateView):
    template_name = "simulations/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        simulation = get_simulation(kwargs["slug"])
        if simulation is None:
            raise Http404
        context["simulation"] = simulation
        return context
