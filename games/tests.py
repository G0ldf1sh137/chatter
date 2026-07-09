from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .logic import tic_tac_toe
from .logic.exceptions import InvalidMove
from .models import Match


def make_user(username):
    return User.objects.create_user(username=username, password="correct-horse-battery-staple")


class TicTacToeLogicTests(TestCase):
    def test_initial_state_is_empty_board(self):
        state = tic_tac_toe.initial_state()
        self.assertEqual(state["board"], [None] * 9)

    def test_apply_move_places_symbol(self):
        state = tic_tac_toe.apply_move(tic_tac_toe.initial_state(), 4, "X")
        self.assertEqual(state["board"][4], "X")

    def test_apply_move_rejects_out_of_range_cell(self):
        with self.assertRaises(InvalidMove):
            tic_tac_toe.apply_move(tic_tac_toe.initial_state(), 9, "X")

    def test_apply_move_rejects_occupied_cell(self):
        state = tic_tac_toe.apply_move(tic_tac_toe.initial_state(), 0, "X")
        with self.assertRaises(InvalidMove):
            tic_tac_toe.apply_move(state, 0, "O")

    def test_check_winner_detects_row(self):
        state = {"board": ["X", "X", "X", None, None, None, None, None, None]}
        self.assertEqual(tic_tac_toe.check_winner(state), "X")

    def test_check_winner_detects_column(self):
        state = {"board": ["O", None, None, "O", None, None, "O", None, None]}
        self.assertEqual(tic_tac_toe.check_winner(state), "O")

    def test_check_winner_detects_diagonal(self):
        state = {"board": ["X", None, None, None, "X", None, None, None, "X"]}
        self.assertEqual(tic_tac_toe.check_winner(state), "X")

    def test_check_winner_detects_draw(self):
        state = {"board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"]}
        self.assertEqual(tic_tac_toe.check_winner(state), "draw")

    def test_check_winner_returns_none_mid_game(self):
        state = {"board": ["X", None, None, None, None, None, None, None, None]}
        self.assertIsNone(tic_tac_toe.check_winner(state))


class TicTacToeMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("ttt-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("ttt-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.TIC_TAC_TOE)
        self.assertEqual(match.player1, self.alice)
        self.assertEqual(match.player2, self.bob)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("ttt-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_anonymous_cannot_challenge(self):
        response = self.client.post(reverse("ttt-challenge", args=["bob"]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("ttt-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_move_by_wrong_player_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("ttt-move", args=[match.pk]), {"cell": 0})
        match.refresh_from_db()
        self.assertEqual(match.state["board"], [None] * 9)
        self.assertEqual(match.turn, self.alice)

    def test_move_on_occupied_cell_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state={"board": ["X"] + [None] * 8},
            turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("ttt-move", args=[match.pk]), {"cell": 0})
        match.refresh_from_db()
        self.assertEqual(match.state["board"][0], "X")
        self.assertEqual(match.turn, self.bob)

    def test_valid_move_switches_turn(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("ttt-move", args=[match.pk]), {"cell": 4})
        match.refresh_from_db()
        self.assertEqual(match.state["board"][4], "X")
        self.assertEqual(match.turn, self.bob)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_winning_move_finishes_match(self):
        # Alice (X) one move from winning the top row.
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state={"board": ["X", "X", None, "O", "O", None, None, None, None]},
            turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("ttt-move", args=[match.pk]), {"cell": 2})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.alice)
        self.assertIsNone(match.turn)

    def test_draw_finishes_match_with_no_winner(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state={"board": ["X", "O", "X", "X", "O", "O", "O", "X", None]},
            turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("ttt-move", args=[match.pk]), {"cell": 8})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertIsNone(match.winner)
