from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .logic import hangman, rock_paper_scissors, tic_tac_toe
from .logic.exceptions import InvalidMove
from .models import Match, SinglePlayerResult


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


class RockPaperScissorsLogicTests(TestCase):
    def test_same_choice_is_draw(self):
        self.assertEqual(rock_paper_scissors.determine_winner("rock", "rock"), "draw")

    def test_rock_beats_scissors(self):
        self.assertEqual(rock_paper_scissors.determine_winner("rock", "scissors"), "a")
        self.assertEqual(rock_paper_scissors.determine_winner("scissors", "rock"), "b")

    def test_paper_beats_rock(self):
        self.assertEqual(rock_paper_scissors.determine_winner("paper", "rock"), "a")
        self.assertEqual(rock_paper_scissors.determine_winner("rock", "paper"), "b")

    def test_scissors_beats_paper(self):
        self.assertEqual(rock_paper_scissors.determine_winner("scissors", "paper"), "a")
        self.assertEqual(rock_paper_scissors.determine_winner("paper", "scissors"), "b")


class RockPaperScissorsMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match_with_no_turn(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("rps-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("rps-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.ROCK_PAPER_SCISSORS)
        self.assertIsNone(match.turn)
        self.assertEqual(match.state, {"choices": {}})

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("rps-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_first_choice_does_not_finish_match(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "rock"})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.ACTIVE)
        self.assertEqual(match.state["choices"], {str(self.alice.id): "rock"})

    def test_cannot_choose_twice(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "rock"})
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "paper"})
        match.refresh_from_db()
        self.assertEqual(match.state["choices"], {str(self.alice.id): "rock"})

    def test_second_choice_resolves_match(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS,
            player1=self.alice,
            player2=self.bob,
            state={"choices": {str(self.alice.id): "rock"}},
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "scissors"})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.alice)

    def test_draw_resolves_with_no_winner(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS,
            player1=self.alice,
            player2=self.bob,
            state={"choices": {str(self.alice.id): "rock"}},
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "rock"})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertIsNone(match.winner)

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("rps-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_invalid_choice_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("rps-move", args=[match.pk]), {"choice": "lizard"})
        match.refresh_from_db()
        self.assertEqual(match.state["choices"], {})


class HangmanLogicTests(TestCase):
    def test_initial_state_has_no_guesses(self):
        state = hangman.initial_state()
        self.assertIn(state["word"], hangman.WORD_LIST)
        self.assertEqual(state["guessed"], [])
        self.assertEqual(state["wrong"], 0)

    def test_correct_guess_does_not_increment_wrong(self):
        state = {"word": "python", "guessed": [], "wrong": 0}
        state = hangman.apply_guess(state, "p")
        self.assertEqual(state["wrong"], 0)
        self.assertIn("p", state["guessed"])

    def test_incorrect_guess_increments_wrong(self):
        state = {"word": "python", "guessed": [], "wrong": 0}
        state = hangman.apply_guess(state, "z")
        self.assertEqual(state["wrong"], 1)

    def test_repeated_guess_is_a_no_op(self):
        state = {"word": "python", "guessed": ["z"], "wrong": 1}
        state = hangman.apply_guess(state, "z")
        self.assertEqual(state["wrong"], 1)
        self.assertEqual(state["guessed"], ["z"])

    def test_display_word_hides_unguessed_letters(self):
        state = {"word": "cat", "guessed": ["c"], "wrong": 0}
        self.assertEqual(hangman.display_word(state), ["c", None, None])

    def test_status_won_when_all_letters_guessed(self):
        state = {"word": "cat", "guessed": ["c", "a", "t"], "wrong": 0}
        self.assertEqual(hangman.game_status(state), "won")

    def test_status_lost_at_max_wrong_guesses(self):
        state = {"word": "cat", "guessed": [], "wrong": hangman.MAX_WRONG_GUESSES}
        self.assertEqual(hangman.game_status(state), "lost")

    def test_status_playing_mid_game(self):
        state = {"word": "cat", "guessed": ["c"], "wrong": 1}
        self.assertEqual(hangman.game_status(state), "playing")


class HangmanSessionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def test_new_game_stores_state_in_session(self):
        self.client.post(reverse("hangman-new"))
        self.assertIn("hangman_game", self.client.session)

    def test_correct_guesses_win_and_record_result(self):
        self.client.post(reverse("hangman-new"))
        word = self.client.session["hangman_game"]["word"]
        for letter in set(word):
            self.client.post(reverse("hangman-guess"), {"letter": letter})
        result = SinglePlayerResult.objects.get()
        self.assertTrue(result.won)
        self.assertEqual(result.player, self.alice)
        self.assertEqual(result.game, SinglePlayerResult.Game.HANGMAN)

    def test_six_wrong_guesses_lose_and_record_result(self):
        self.client.post(reverse("hangman-new"))
        word = set(self.client.session["hangman_game"]["word"])
        wrong_letters = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in word][:6]
        for letter in wrong_letters:
            self.client.post(reverse("hangman-guess"), {"letter": letter})
        result = SinglePlayerResult.objects.get()
        self.assertFalse(result.won)

    def test_guessing_after_game_over_does_not_record_twice(self):
        self.client.post(reverse("hangman-new"))
        word = set(self.client.session["hangman_game"]["word"])
        wrong_letters = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in word][:6]
        for letter in wrong_letters:
            self.client.post(reverse("hangman-guess"), {"letter": letter})
        # One more guess after the game is already lost.
        self.client.post(reverse("hangman-guess"), {"letter": "a"})
        self.assertEqual(SinglePlayerResult.objects.count(), 1)

    def test_anonymous_cannot_play(self):
        self.client.logout()
        response = self.client.post(reverse("hangman-new"))
        self.assertEqual(response.status_code, 302)


class Game2048ResultTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def post_json(self, payload):
        return self.client.post(reverse("2048-finish"), data=payload, content_type="application/json")

    def test_valid_score_is_recorded(self):
        response = self.post_json({"score": 1020, "highest_tile": 128})
        self.assertEqual(response.status_code, 200)
        result = SinglePlayerResult.objects.get()
        self.assertEqual(result.player, self.alice)
        self.assertEqual(result.game, SinglePlayerResult.Game.GAME_2048)
        self.assertEqual(result.score, 1020)
        self.assertFalse(result.won)

    def test_reaching_2048_tile_marks_won(self):
        self.post_json({"score": 20000, "highest_tile": 2048})
        result = SinglePlayerResult.objects.get()
        self.assertTrue(result.won)

    def test_negative_score_is_rejected(self):
        response = self.post_json({"score": -5, "highest_tile": 128})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_absurdly_high_score_is_rejected(self):
        response = self.post_json({"score": 99_999_999, "highest_tile": 128})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_non_power_of_two_tile_is_rejected(self):
        response = self.post_json({"score": 100, "highest_tile": 100})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_score_inconsistent_with_tile_is_rejected(self):
        # A highest tile of 512 requires a score of at least 510.
        response = self.post_json({"score": 10, "highest_tile": 512})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_malformed_payload_is_rejected(self):
        response = self.client.post(reverse("2048-finish"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_submit_score(self):
        self.client.logout()
        response = self.post_json({"score": 100, "highest_tile": 128})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)


class LeaderboardTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")

    def test_ttt_leaderboard_orders_by_wins(self):
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=self.alice, player2=self.bob,
            status=Match.Status.FINISHED, winner=self.alice,
        )
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=self.alice, player2=self.carol,
            status=Match.Status.FINISHED, winner=self.alice,
        )
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE, player1=self.bob, player2=self.carol,
            status=Match.Status.FINISHED, winner=self.bob,
        )
        response = self.client.get(reverse("games-leaderboard"))
        leaders = list(response.context["ttt_leaders"])
        self.assertEqual(leaders[0]["winner__username"], "alice")
        self.assertEqual(leaders[0]["wins"], 2)

    def test_hangman_leaderboard_orders_by_win_count(self):
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.HANGMAN, won=True)
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.HANGMAN, won=True)
        SinglePlayerResult.objects.create(player=self.bob, game=SinglePlayerResult.Game.HANGMAN, won=True)
        SinglePlayerResult.objects.create(player=self.bob, game=SinglePlayerResult.Game.HANGMAN, won=False)
        response = self.client.get(reverse("games-leaderboard"))
        leaders = list(response.context["hangman_leaders"])
        self.assertEqual(leaders[0]["player__username"], "alice")
        self.assertEqual(leaders[0]["wins"], 2)

    def test_2048_leaderboard_orders_by_high_score(self):
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.GAME_2048, score=500)
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.GAME_2048, score=2000)
        SinglePlayerResult.objects.create(player=self.bob, game=SinglePlayerResult.Game.GAME_2048, score=1000)
        response = self.client.get(reverse("games-leaderboard"))
        leaders = list(response.context["game2048_leaders"])
        self.assertEqual(leaders[0]["player__username"], "alice")
        self.assertEqual(leaders[0]["high_score"], 2000)

    def test_leaderboard_is_publicly_accessible(self):
        response = self.client.get(reverse("games-leaderboard"))
        self.assertEqual(response.status_code, 200)
