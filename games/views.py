from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, TemplateView

from .logic import tic_tac_toe
from .logic.exceptions import InvalidMove
from .models import Match


class GamesHubView(LoginRequiredMixin, TemplateView):
    template_name = "games/games_hub.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        matches = list(
            Match.objects.filter(status=Match.Status.ACTIVE)
            .filter(Q(player1=user) | Q(player2=user))
            .select_related("player1", "player2")
        )
        for match in matches:
            match.opponent = match.opponent_of(user)
        context["your_turn_matches"] = [m for m in matches if m.turn_id == user.id]
        context["waiting_matches"] = [m for m in matches if m.turn_id != user.id]
        return context


class TicTacToeChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=request.user,
            player2=opponent,
            state=tic_tac_toe.initial_state(),
            turn=request.user,
        )
        return redirect("ttt-match", pk=match.pk)


class TicTacToeMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/tic_tac_toe_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.TIC_TAC_TOE).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        context["board"] = match.state["board"]
        context["your_symbol"] = "X" if self.request.user.id == match.player1_id else "O"
        context["is_your_turn"] = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
        context["opponent"] = match.opponent_of(self.request.user)
        return context


class TicTacToeMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            cell = int(request.POST.get("cell"))
        except (TypeError, ValueError):
            return redirect("ttt-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_for_update(), pk=pk, game=Match.Game.TIC_TAC_TOE
            )
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.turn_id != request.user.id:
                return redirect("ttt-match", pk=pk)

            symbol = "X" if request.user.id == match.player1_id else "O"
            try:
                match.state = tic_tac_toe.apply_move(match.state, cell, symbol)
            except InvalidMove:
                return redirect("ttt-match", pk=pk)

            result = tic_tac_toe.check_winner(match.state)
            if result is None:
                match.turn = match.opponent_of(request.user)
            else:
                match.status = Match.Status.FINISHED
                match.turn = None
                # Only the player who just moved could have completed a new
                # winning line, so no symbol -> user lookup is needed here.
                match.winner = request.user if result != "draw" else None
            match.save()
        return redirect("ttt-match", pk=pk)
