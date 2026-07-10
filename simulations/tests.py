from django.test import TestCase
from django.urls import reverse

from .registry import SIMULATIONS


class SimulationHubViewTests(TestCase):
    def test_hub_lists_every_simulation(self):
        response = self.client.get(reverse("simulations-hub"))
        self.assertEqual(response.status_code, 200)
        for simulation in SIMULATIONS:
            self.assertContains(response, simulation["title"])


class SimulationDetailViewTests(TestCase):
    def test_valid_slug_renders_its_sketch(self):
        for simulation in SIMULATIONS:
            response = self.client.get(reverse("simulation-detail", args=[simulation["slug"]]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, simulation["js_file"])

    def test_unknown_slug_is_404(self):
        response = self.client.get(reverse("simulation-detail", args=["not-a-real-simulation"]))
        self.assertEqual(response.status_code, 404)
