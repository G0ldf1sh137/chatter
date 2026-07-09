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
from .logic import checkers, connect_four, hangman, othello, rock_paper_scissors, tic_tac_toe, wordle
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
        context["hangman_leaders"] = stats.hangman_leaders()
        context["game2048_leaders"] = stats.game_2048_leaders()
        context["snake_leaders"] = stats.snake_leaders()
        context["doodle_leaders"] = stats.doodle_leaders()
        context["wordle_leaders"] = stats.wordle_leaders()
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
