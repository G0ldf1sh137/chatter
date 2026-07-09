from django.views.generic import TemplateView


class GamesHubView(TemplateView):
    template_name = "games/games_hub.html"
