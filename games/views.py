import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, TemplateView

from . import stats
from .logic import (
    battleship,
    checkers,
    connect_four,
    hangman,
    mastermind,
    nim,
    othello,
    rock_paper_scissors,
    stratego,
    tic_tac_toe,
    wordle,
)
from .logic.exceptions import InvalidMove
from .models import Match, SinglePlayerResult

SESSION_KEY_HANGMAN = "hangman_game"

# Generous ceiling well above any realistic 2048 game - just a sanity bound,
# not an attempt at full move-replay anti-cheat (proportionate to a casual
# game's stakes: leaderboard vanity, not real value).
MAX_2048_SCORE = 10_000_000
MAX_2048_TILE = 131072

# A 20x20 grid has 400 cells; you can never eat more food than that.
SNAKE_GRID_SIZE = 20
MAX_SNAKE_SCORE = SNAKE_GRID_SIZE * SNAKE_GRID_SIZE

# No principled ceiling like 2048's power-of-two check (height is unbounded
# in principle) - just a generous sanity bound, same anti-cheat proportionality.
MAX_DOODLE_SCORE = 1_000_000


class LeaderboardView(TemplateView):
    template_name = "games/leaderboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ttt_leaders"] = stats.match_win_leaders(Match.Game.TIC_TAC_TOE)
        context["rps_leaders"] = stats.match_win_leaders(Match.Game.ROCK_PAPER_SCISSORS)
        context["connect4_leaders"] = stats.match_win_leaders(Match.Game.CONNECT_FOUR)
        context["checkers_leaders"] = stats.match_win_leaders(Match.Game.CHECKERS)
        context["othello_leaders"] = stats.match_win_leaders(Match.Game.OTHELLO)
        context["nim_leaders"] = stats.match_win_leaders(Match.Game.NIM)
        context["battleship_leaders"] = stats.match_win_leaders(Match.Game.BATTLESHIP)
        context["stratego_leaders"] = stats.match_win_leaders(Match.Game.STRATEGO)
        context["hangman_leaders"] = stats.hangman_leaders()
        context["game2048_leaders"] = stats.game_2048_leaders()
        context["snake_leaders"] = stats.snake_leaders()
        context["doodle_leaders"] = stats.doodle_leaders()
        context["wordle_leaders"] = stats.wordle_leaders()
        context["mastermind_leaders"] = stats.mastermind_leaders()
        return context


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
        context["your_turn_matches"] = [m for m in matches if stats.is_users_turn(m, user)]
        context["waiting_matches"] = [m for m in matches if not stats.is_users_turn(m, user)]
        return context


class MatchStatusView(LoginRequiredMixin, View):
    # One endpoint for all 5 multiplayer games' poll-for-updates JS (see
    # match_poll.js) - the client only needs to know "has anything changed
    # since I loaded this page", which is game-agnostic, so this avoids a
    # near-identical status view per game.
    def get(self, request, pk):
        match = get_object_or_404(Match, pk=pk)
        if request.user.id not in (match.player1_id, match.player2_id):
            raise Http404
        return JsonResponse({"updated_at": match.updated_at.isoformat(), "status": match.status})


class YourTurnCountView(LoginRequiredMixin, View):
    def get(self, request):
        return JsonResponse({"count": stats.your_turn_count(request.user)})


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


class RockPaperScissorsChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS,
            player1=request.user,
            player2=opponent,
            state={"choices": {}},
        )
        return redirect("rps-match", pk=match.pk)


class RockPaperScissorsMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/rock_paper_scissors_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.ROCK_PAPER_SCISSORS).select_related(
            "player1", "player2", "winner"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        choices = match.state.get("choices", {})
        context["opponent"] = match.opponent_of(self.request.user)
        context["your_choice"] = choices.get(str(self.request.user.id))
        if match.status == Match.Status.FINISHED:
            context["player1_choice"] = choices.get(str(match.player1_id))
            context["player2_choice"] = choices.get(str(match.player2_id))
        return context


class RockPaperScissorsMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        choice = request.POST.get("choice")
        if choice not in rock_paper_scissors.CHOICES:
            return redirect("rps-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_for_update(), pk=pk, game=Match.Game.ROCK_PAPER_SCISSORS
            )
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE:
                return redirect("rps-match", pk=pk)

            choices = dict(match.state.get("choices", {}))
            if str(request.user.id) in choices:
                # Already chosen - no changing your mind mid-match.
                return redirect("rps-match", pk=pk)
            choices[str(request.user.id)] = choice
            match.state = {"choices": choices}

            if len(choices) == 2:
                result = rock_paper_scissors.determine_winner(
                    choices[str(match.player1_id)], choices[str(match.player2_id)]
                )
                match.status = Match.Status.FINISHED
                if result == "draw":
                    match.winner = None
                else:
                    match.winner = match.player1 if result == "a" else match.player2
            match.save()
        return redirect("rps-match", pk=pk)


class ConnectFourChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR,
            player1=request.user,
            player2=opponent,
            state=connect_four.initial_state(),
            turn=request.user,
        )
        return redirect("connect4-match", pk=match.pk)


class ConnectFourMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/connect_four_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.CONNECT_FOUR).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        context["board"] = match.state["board"]
        context["your_symbol"] = "X" if self.request.user.id == match.player1_id else "O"
        context["is_your_turn"] = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
        context["opponent"] = match.opponent_of(self.request.user)
        return context


class ConnectFourMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            column = int(request.POST.get("column"))
        except (TypeError, ValueError):
            return redirect("connect4-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_for_update(), pk=pk, game=Match.Game.CONNECT_FOUR
            )
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.turn_id != request.user.id:
                return redirect("connect4-match", pk=pk)

            symbol = "X" if request.user.id == match.player1_id else "O"
            try:
                match.state = connect_four.apply_move(match.state, column, symbol)
            except InvalidMove:
                return redirect("connect4-match", pk=pk)

            result = connect_four.check_winner(match.state)
            if result is None:
                match.turn = match.opponent_of(request.user)
            else:
                match.status = Match.Status.FINISHED
                match.turn = None
                match.winner = request.user if result != "draw" else None
            match.save()
        return redirect("connect4-match", pk=pk)


class CheckersChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.CHECKERS,
            player1=request.user,
            player2=opponent,
            state=checkers.initial_state(),
            turn=request.user,
        )
        return redirect("checkers-match", pk=match.pk)


class CheckersMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/checkers_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.CHECKERS).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        context["board"] = match.state["board"]
        # player1 is always "r" (red), starts at the bottom of the board.
        context["your_color"] = "r" if self.request.user.id == match.player1_id else "b"
        context["is_your_turn"] = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
        context["opponent"] = match.opponent_of(self.request.user)
        return context


class CheckersMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            from_pos = (int(request.POST["from_row"]), int(request.POST["from_col"]))
            to_pos = (int(request.POST["to_row"]), int(request.POST["to_col"]))
        except (KeyError, TypeError, ValueError):
            return redirect("checkers-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_for_update(), pk=pk, game=Match.Game.CHECKERS
            )
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.turn_id != request.user.id:
                return redirect("checkers-match", pk=pk)

            player = "r" if request.user.id == match.player1_id else "b"
            try:
                match.state = checkers.apply_move(match.state, from_pos, to_pos, player)
            except InvalidMove:
                return redirect("checkers-match", pk=pk)

            opponent_color = "b" if player == "r" else "r"
            winner_color = checkers.check_winner(match.state, opponent_color)
            if winner_color is None:
                match.turn = match.opponent_of(request.user)
            else:
                match.status = Match.Status.FINISHED
                match.turn = None
                # winner_color always equals player here (the mover just
                # captured the opponent's last piece or stalemated them),
                # so no color -> user lookup is needed.
                match.winner = request.user
            match.save()
        return redirect("checkers-match", pk=pk)


class OthelloChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.OTHELLO,
            player1=request.user,
            player2=opponent,
            state=othello.initial_state(),
            turn=request.user,  # player1 is always Black, who moves first
        )
        return redirect("othello-match", pk=match.pk)


class OthelloMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/othello_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.OTHELLO).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        board = match.state["board"]
        your_color = "B" if self.request.user.id == match.player1_id else "W"
        is_your_turn = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id

        legal = set(othello.legal_moves(match.state, your_color)) if is_your_turn else set()
        context["board_cells"] = [
            [{"piece": cell, "legal": (r, c) in legal, "r": r, "c": c} for c, cell in enumerate(row)]
            for r, row in enumerate(board)
        ]
        context["your_color"] = your_color
        context["is_your_turn"] = is_your_turn
        context["opponent"] = match.opponent_of(self.request.user)

        opponent_color = "W" if your_color == "B" else "B"
        context["just_passed"] = is_your_turn and not othello.legal_moves(match.state, opponent_color)

        if match.status == Match.Status.FINISHED:
            context["black_count"], context["white_count"] = othello.piece_counts(match.state)
        return context


class OthelloMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            row, col = int(request.POST.get("row")), int(request.POST.get("col"))
        except (TypeError, ValueError):
            return redirect("othello-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_for_update(), pk=pk, game=Match.Game.OTHELLO
            )
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.turn_id != request.user.id:
                return redirect("othello-match", pk=pk)

            color = "B" if request.user.id == match.player1_id else "W"
            try:
                match.state = othello.apply_move(match.state, row, col, color)
            except InvalidMove:
                return redirect("othello-match", pk=pk)

            opponent_color = "W" if color == "B" else "B"
            outcome, value = othello.next_turn_state(match.state, color, opponent_color)
            color_to_user = {"B": match.player1, "W": match.player2}
            if outcome in ("continue", "pass"):
                match.turn = color_to_user[value]
            else:
                match.status = Match.Status.FINISHED
                match.turn = None
                match.winner = color_to_user[value] if value else None
            match.save()
        return redirect("othello-match", pk=pk)


class NimChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.NIM,
            player1=request.user,
            player2=opponent,
            state=nim.initial_state(),
            turn=request.user,
        )
        return redirect("nim-match", pk=match.pk)


class NimMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/nim_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.NIM).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        is_your_turn = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
        # Flattened per-stick data (index/remove-count) computed here rather
        # than in the template - same fix as Othello's board_cells, since
        # templates can't cleanly do the arithmetic for "clicking the nth
        # stick removes it and everything to its right" on their own.
        context["piles"] = [
            {
                "index": i,
                "sticks": [{"remove_count": count - position + 1} for position in range(1, count + 1)],
            }
            for i, count in enumerate(match.state["piles"])
        ]
        context["is_your_turn"] = is_your_turn
        context["opponent"] = match.opponent_of(self.request.user)
        return context


class NimMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            pile_index = int(request.POST.get("pile"))
            count = int(request.POST.get("count"))
        except (TypeError, ValueError):
            return redirect("nim-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), pk=pk, game=Match.Game.NIM)
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.turn_id != request.user.id:
                return redirect("nim-match", pk=pk)

            try:
                match.state = nim.apply_move(match.state, pile_index, count)
            except InvalidMove:
                return redirect("nim-match", pk=pk)

            if nim.is_game_over(match.state):
                match.status = Match.Status.FINISHED
                match.turn = None
                match.winner = request.user
            else:
                match.turn = match.opponent_of(request.user)
            match.save()
        return redirect("nim-match", pk=pk)


class BattleshipChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.BATTLESHIP,
            player1=request.user,
            player2=opponent,
            state=battleship.initial_state(),
            # No turn yet - both players place ships independently before
            # battle starts, same as Rock-Paper-Scissors' simultaneous phase.
            turn=None,
        )
        return redirect("battleship-match", pk=match.pk)


class BattleshipMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/battleship_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.BATTLESHIP).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        my_id = str(self.request.user.id)
        opponent = match.opponent_of(self.request.user)
        opponent_id = str(opponent.id)
        size_range = range(battleship.BOARD_SIZE)
        context["opponent"] = opponent
        context["phase"] = match.state["phase"]

        if match.state["phase"] == "placement":
            my_ships = battleship.ships_for(match.state, my_id)
            fully_placed = len(my_ships) >= len(battleship.FLEET)
            context["fully_placed"] = fully_placed
            if not fully_placed:
                context["next_ship_length"] = battleship.FLEET[len(my_ships)]
            my_ship_cells = {(r, c) for ship in my_ships for r, c in ship}
            context["my_board_cells"] = [
                [{"ship": (r, c) in my_ship_cells, "r": r, "c": c} for c in size_range] for r in size_range
            ]
        else:
            viewer = battleship.viewer_state(match.state, my_id, opponent_id)
            your_ship_cells = {(r, c) for ship in viewer["your_ships"] for r, c in ship}
            shots_against_you = {tuple(cell) for cell in viewer["shots_against_you"]}
            context["your_board_cells"] = [
                [
                    {
                        "ship": (r, c) in your_ship_cells,
                        "hit": (r, c) in your_ship_cells and (r, c) in shots_against_you,
                        "miss": (r, c) not in your_ship_cells and (r, c) in shots_against_you,
                    }
                    for c in size_range
                ]
                for r in size_range
            ]

            your_shots = {(shot["row"], shot["col"]): shot["hit"] for shot in viewer["your_shots"]}
            is_your_turn = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
            context["is_your_turn"] = is_your_turn
            context["opponent_board_cells"] = [
                [
                    {
                        "shot": (r, c) in your_shots,
                        "hit": your_shots.get((r, c), False),
                        "clickable": is_your_turn and (r, c) not in your_shots,
                        "r": r,
                        "c": c,
                    }
                    for c in size_range
                ]
                for r in size_range
            ]
        return context


class BattleshipPlaceView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            row, col = (int(n) for n in request.POST.get("cell", "").split(","))
        except (TypeError, ValueError):
            return redirect("battleship-match", pk=pk)
        orientation = request.POST.get("orientation")

        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), pk=pk, game=Match.Game.BATTLESHIP)
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.state["phase"] != "placement":
                return redirect("battleship-match", pk=pk)

            try:
                match.state = battleship.apply_placement(match.state, str(request.user.id), row, col, orientation)
            except InvalidMove as e:
                messages.error(request, str(e))
                return redirect("battleship-match", pk=pk)

            p1_id, p2_id = str(match.player1_id), str(match.player2_id)
            if battleship.both_players_placed(match.state, p1_id, p2_id):
                match.state = {**match.state, "phase": "battle"}
                match.turn = match.player1
            match.save()
        return redirect("battleship-match", pk=pk)


class BattleshipMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            row, col = int(request.POST.get("row")), int(request.POST.get("col"))
        except (TypeError, ValueError):
            return redirect("battleship-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), pk=pk, game=Match.Game.BATTLESHIP)
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if (
                match.status != Match.Status.ACTIVE
                or match.state.get("phase") != "battle"
                or match.turn_id != request.user.id
            ):
                return redirect("battleship-match", pk=pk)

            opponent = match.opponent_of(request.user)
            target_id = str(opponent.id)
            try:
                match.state = battleship.apply_shot(match.state, target_id, row, col)
            except InvalidMove:
                return redirect("battleship-match", pk=pk)

            if battleship.all_ships_sunk(match.state, target_id):
                match.status = Match.Status.FINISHED
                match.turn = None
                match.winner = request.user
            else:
                match.turn = opponent
            match.save()
        return redirect("battleship-match", pk=pk)


class StrategoChallengeView(LoginRequiredMixin, View):
    def post(self, request, username):
        opponent = get_object_or_404(User, username=username)
        if opponent == request.user:
            messages.error(request, "You can't challenge yourself.")
            return redirect("profile", username=username)
        match = Match.objects.create(
            game=Match.Game.STRATEGO,
            player1=request.user,
            player2=opponent,
            state=stratego.initial_state(),
            turn=None,
        )
        return redirect("stratego-match", pk=match.pk)


class StrategoMatchView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    template_name = "games/stratego_match.html"
    context_object_name = "match"

    def test_func(self):
        match = self.get_object()
        return self.request.user.id in (match.player1_id, match.player2_id)

    def get_queryset(self):
        return Match.objects.filter(game=Match.Game.STRATEGO).select_related("player1", "player2", "winner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context["match"]
        my_id = str(self.request.user.id)
        is_player1 = self.request.user.id == match.player1_id
        opponent = match.opponent_of(self.request.user)
        opponent_id = str(opponent.id)
        size_range = range(stratego.BOARD_SIZE)
        context["opponent"] = opponent
        context["phase"] = match.state["phase"]

        if match.state["phase"] == "placement":
            my_pieces = stratego.pieces_for(match.state, my_id)
            fully_placed = stratego.is_fully_placed(match.state, my_id)
            context["fully_placed"] = fully_placed
            if not fully_placed:
                context["next_rank"] = stratego.FLEET[len(my_pieces)]
            valid_rows = stratego.deployment_rows(is_player1)
            my_piece_at = {(p["row"], p["col"]): p["rank"] for p in my_pieces}
            context["board_cells"] = [
                [
                    {"rank": my_piece_at.get((r, c)), "in_zone": r in valid_rows, "r": r, "c": c}
                    for c in size_range
                ]
                for r in size_range
            ]
        else:
            viewer = stratego.viewer_state(match.state, my_id, opponent_id)
            your_piece_at = {(p["row"], p["col"]): p for p in viewer["your_pieces"]}
            opponent_piece_at = {(p["row"], p["col"]): p for p in viewer["opponent_pieces"]}
            is_your_turn = match.status == Match.Status.ACTIVE and match.turn_id == self.request.user.id
            context["is_your_turn"] = is_your_turn
            context["last_combat"] = viewer["last_combat"]
            context["board_cells"] = [
                [
                    {
                        "your_rank": your_piece_at.get((r, c), {}).get("rank"),
                        "opponent_present": (r, c) in opponent_piece_at,
                        "opponent_rank": opponent_piece_at.get((r, c), {}).get("rank"),
                        "r": r,
                        "c": c,
                    }
                    for c in size_range
                ]
                for r in size_range
            ]
        return context


class StrategoPlaceView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            row, col = (int(n) for n in request.POST.get("cell", "").split(","))
        except (TypeError, ValueError):
            return redirect("stratego-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), pk=pk, game=Match.Game.STRATEGO)
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if match.status != Match.Status.ACTIVE or match.state["phase"] != "placement":
                return redirect("stratego-match", pk=pk)

            is_player1 = request.user.id == match.player1_id
            valid_rows = stratego.deployment_rows(is_player1)
            try:
                match.state = stratego.apply_placement(match.state, str(request.user.id), row, col, valid_rows)
            except InvalidMove as e:
                messages.error(request, str(e))
                return redirect("stratego-match", pk=pk)

            p1_id, p2_id = str(match.player1_id), str(match.player2_id)
            if stratego.both_players_placed(match.state, p1_id, p2_id):
                match.state = {**match.state, "phase": "battle"}
                match.turn = match.player1
            match.save()
        return redirect("stratego-match", pk=pk)


class StrategoMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            from_row, from_col = int(request.POST.get("from_row")), int(request.POST.get("from_col"))
            to_row, to_col = int(request.POST.get("to_row")), int(request.POST.get("to_col"))
        except (TypeError, ValueError):
            return redirect("stratego-match", pk=pk)

        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), pk=pk, game=Match.Game.STRATEGO)
            if request.user.id not in (match.player1_id, match.player2_id):
                raise Http404
            if (
                match.status != Match.Status.ACTIVE
                or match.state.get("phase") != "battle"
                or match.turn_id != request.user.id
            ):
                return redirect("stratego-match", pk=pk)

            opponent = match.opponent_of(request.user)
            mover_id, opponent_id = str(request.user.id), str(opponent.id)
            try:
                match.state = stratego.apply_move(
                    match.state, mover_id, opponent_id, from_row, from_col, to_row, to_col
                )
            except InvalidMove as e:
                messages.error(request, str(e))
                return redirect("stratego-match", pk=pk)

            if stratego.flag_captured(match.state, opponent_id):
                match.status = Match.Status.FINISHED
                match.turn = None
                match.winner = request.user
            else:
                match.turn = opponent
            match.save()
        return redirect("stratego-match", pk=pk)


class HangmanNewView(LoginRequiredMixin, View):
    def post(self, request):
        request.session[SESSION_KEY_HANGMAN] = hangman.initial_state()
        return redirect("hangman-play")


class HangmanPlayView(LoginRequiredMixin, TemplateView):
    template_name = "games/hangman_play.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self.request.session.get(SESSION_KEY_HANGMAN)
        context["state"] = state
        if state:
            context["display"] = hangman.display_word(state)
            context["status"] = hangman.game_status(state)
            context["remaining_guesses"] = hangman.MAX_WRONG_GUESSES - state["wrong"]
            context["alphabet"] = "abcdefghijklmnopqrstuvwxyz"
        return context


class HangmanGuessView(LoginRequiredMixin, View):
    def post(self, request):
        state = request.session.get(SESSION_KEY_HANGMAN)
        letter = request.POST.get("letter", "")
        if state and len(letter) == 1 and letter.isalpha() and hangman.game_status(state) == "playing":
            state = hangman.apply_guess(state, letter)
            request.session[SESSION_KEY_HANGMAN] = state
            status = hangman.game_status(state)
            if status in ("won", "lost"):
                SinglePlayerResult.objects.create(
                    player=request.user,
                    game=SinglePlayerResult.Game.HANGMAN,
                    won=status == "won",
                    score=1 if status == "won" else 0,
                )
        return redirect("hangman-play")


class Game2048View(LoginRequiredMixin, TemplateView):
    template_name = "games/game_2048.html"


class Game2048FinishView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            score = int(data["score"])
            highest_tile = int(data["highest_tile"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "invalid payload"}, status=400)

        if not (0 <= score <= MAX_2048_SCORE):
            return JsonResponse({"error": "invalid score"}, status=400)
        if not (2 <= highest_tile <= MAX_2048_TILE) or (highest_tile & (highest_tile - 1)) != 0:
            return JsonResponse({"error": "invalid highest tile"}, status=400)
        # The minimum possible score to have legitimately produced a tile of
        # value N through repeated merges is N - 2 (every other merge in the
        # game only adds to the score, never subtracts).
        if score < highest_tile - 2:
            return JsonResponse({"error": "score inconsistent with highest tile"}, status=400)

        SinglePlayerResult.objects.create(
            player=request.user,
            game=SinglePlayerResult.Game.GAME_2048,
            won=highest_tile >= 2048,
            score=score,
        )
        return JsonResponse({"ok": True})


class SnakeView(LoginRequiredMixin, TemplateView):
    template_name = "games/snake.html"


class SnakeFinishView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            score = int(data["score"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "invalid payload"}, status=400)

        if not (0 <= score <= MAX_SNAKE_SCORE):
            return JsonResponse({"error": "invalid score"}, status=400)

        SinglePlayerResult.objects.create(
            player=request.user, game=SinglePlayerResult.Game.SNAKE, won=False, score=score
        )
        return JsonResponse({"ok": True})


class DoodleJumpView(LoginRequiredMixin, TemplateView):
    template_name = "games/doodle_jump.html"


class DoodleJumpFinishView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            score = int(data["score"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "invalid payload"}, status=400)

        if not (0 <= score <= MAX_DOODLE_SCORE):
            return JsonResponse({"error": "invalid score"}, status=400)

        SinglePlayerResult.objects.create(
            player=request.user, game=SinglePlayerResult.Game.DOODLE_JUMP, won=False, score=score
        )
        return JsonResponse({"ok": True})


SESSION_KEY_WORDLE = "wordle_game"


class WordleNewView(LoginRequiredMixin, View):
    def post(self, request):
        request.session[SESSION_KEY_WORDLE] = wordle.initial_state()
        return redirect("wordle-play")


class WordlePlayView(LoginRequiredMixin, TemplateView):
    template_name = "games/wordle_play.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self.request.session.get(SESSION_KEY_WORDLE)
        context["state"] = state
        if state:
            context["status"] = wordle.game_status(state)
            context["guesses_left"] = wordle.MAX_GUESSES - len(state["guesses"])
        return context


class WordleGuessView(LoginRequiredMixin, View):
    def post(self, request):
        state = request.session.get(SESSION_KEY_WORDLE)
        guess = request.POST.get("guess", "")
        if state and wordle.game_status(state) == "playing":
            try:
                state = wordle.apply_guess(state, guess)
            except InvalidMove:
                return redirect("wordle-play")
            request.session[SESSION_KEY_WORDLE] = state
            status = wordle.game_status(state)
            if status in ("won", "lost"):
                SinglePlayerResult.objects.create(
                    player=request.user,
                    game=SinglePlayerResult.Game.WORDLE,
                    won=status == "won",
                    score=(wordle.MAX_GUESSES - len(state["guesses"]) + 1) if status == "won" else 0,
                )
        return redirect("wordle-play")


SESSION_KEY_MASTERMIND = "mastermind_game"


class MastermindNewView(LoginRequiredMixin, View):
    def post(self, request):
        request.session[SESSION_KEY_MASTERMIND] = mastermind.initial_state()
        return redirect("mastermind-play")


class MastermindPlayView(LoginRequiredMixin, TemplateView):
    template_name = "games/mastermind_play.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self.request.session.get(SESSION_KEY_MASTERMIND)
        context["state"] = state
        context["colors"] = mastermind.COLORS
        if state:
            context["status"] = mastermind.game_status(state)
            context["guesses_left"] = mastermind.MAX_GUESSES - len(state["guesses"])
            # Django templates can't call range() themselves, so the
            # black/white peg counts are turned into actual iterable ranges
            # here rather than in the template - same fix as Othello's
            # board_cells/Nim's per-stick data.
            context["guesses_display"] = [
                {"pegs": row["pegs"], "black_dots": range(row["black"]), "white_dots": range(row["white"])}
                for row in state["guesses"]
            ]
        return context


class MastermindGuessView(LoginRequiredMixin, View):
    def post(self, request):
        state = request.session.get(SESSION_KEY_MASTERMIND)
        guess = request.POST.getlist("peg")
        if state and mastermind.game_status(state) == "playing":
            try:
                state = mastermind.apply_guess(state, guess)
            except InvalidMove:
                return redirect("mastermind-play")
            request.session[SESSION_KEY_MASTERMIND] = state
            status = mastermind.game_status(state)
            if status in ("won", "lost"):
                SinglePlayerResult.objects.create(
                    player=request.user,
                    game=SinglePlayerResult.Game.MASTERMIND,
                    won=status == "won",
                    score=(mastermind.MAX_GUESSES - len(state["guesses"]) + 1) if status == "won" else 0,
                )
        return redirect("mastermind-play")
