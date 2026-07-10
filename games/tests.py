from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import stats
from .logic import (
    battleship,
    checkers,
    connect_four,
    hangman,
    mastermind,
    nim,
    nine_mens_morris,
    othello,
    rock_paper_scissors,
    stratego,
    tic_tac_toe,
    wordle,
)
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


class MatchStatusViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )

    def test_anonymous_cannot_poll(self):
        response = self.client.get(reverse("match-status", args=[self.match.pk]))
        self.assertEqual(response.status_code, 302)

    def test_non_participant_cannot_poll(self):
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("match-status", args=[self.match.pk]))
        self.assertEqual(response.status_code, 404)

    def test_participant_gets_status_json(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("match-status", args=[self.match.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["updated_at"], self.match.updated_at.isoformat())

    def test_updated_at_changes_after_a_move(self):
        self.client.force_login(self.alice)
        before = self.client.get(reverse("match-status", args=[self.match.pk])).json()

        self.client.post(reverse("ttt-move", args=[self.match.pk]), {"cell": 0})

        after = self.client.get(reverse("match-status", args=[self.match.pk])).json()
        self.assertNotEqual(before["updated_at"], after["updated_at"])


class YourTurnStatsTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_is_users_turn_for_turn_based_game(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        self.assertTrue(stats.is_users_turn(match, self.alice))
        self.assertFalse(stats.is_users_turn(match, self.bob))

    def test_is_users_turn_for_rps_before_either_picks(self):
        # RPS has no match.turn (both choose simultaneously) - "your turn"
        # means "you haven't locked in a choice yet".
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        self.assertTrue(stats.is_users_turn(match, self.alice))
        self.assertTrue(stats.is_users_turn(match, self.bob))

    def test_is_users_turn_for_rps_after_one_picks(self):
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS,
            player1=self.alice,
            player2=self.bob,
            state={"choices": {str(self.alice.id): "rock"}},
        )
        self.assertFalse(stats.is_users_turn(match, self.alice))
        self.assertTrue(stats.is_users_turn(match, self.bob))

    def test_finished_match_is_never_your_turn(self):
        match = Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            status=Match.Status.FINISHED,
            winner=self.alice,
        )
        self.assertFalse(stats.is_users_turn(match, self.alice))

    def test_your_turn_count_across_games(self):
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        Match.objects.create(
            game=Match.Game.CONNECT_FOUR,
            player1=self.bob,
            player2=self.alice,
            state=connect_four.initial_state(),
            turn=self.bob,
        )
        self.assertEqual(stats.your_turn_count(self.alice), 2)


class YourTurnCountViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("your-turn-count"))
        self.assertEqual(response.status_code, 302)

    def test_returns_correct_count(self):
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("your-turn-count"))
        self.assertEqual(response.json(), {"count": 1})


class GamesHubViewTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_rps_match_awaiting_your_choice_is_bucketed_as_your_turn(self):
        # Regression test: turn_id is always None for RPS (see Match.turn's
        # docstring), so bucketing on turn_id alone would wrongly dump every
        # active RPS match into "waiting" even when it's actually your move.
        match = Match.objects.create(
            game=Match.Game.ROCK_PAPER_SCISSORS, player1=self.alice, player2=self.bob, state={"choices": {}}
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("games-hub"))
        self.assertIn(match, response.context["your_turn_matches"])
        self.assertNotIn(match, response.context["waiting_matches"])


class YourTurnBadgeTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_badge_hidden_with_no_active_matches(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("games-hub"))
        self.assertContains(response, 'id="your-turn-badge"')
        self.assertEqual(response.context["your_turn_count"], 0)
        self.assertContains(response, "hidden")

    def test_badge_shows_count_when_its_your_turn(self):
        Match.objects.create(
            game=Match.Game.TIC_TAC_TOE,
            player1=self.alice,
            player2=self.bob,
            state=tic_tac_toe.initial_state(),
            turn=self.alice,
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("games-hub"))
        self.assertEqual(response.context["your_turn_count"], 1)
        self.assertContains(response, ">1</span>")

    def test_anonymous_page_has_no_badge(self):
        response = self.client.get(reverse("register"))
        self.assertNotContains(response, "your-turn-badge")


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


class WordleLogicTests(TestCase):
    def test_duplicate_letter_feedback_speed_erase(self):
        self.assertEqual(
            wordle._feedback("speed", "erase"),
            ["present", "absent", "absent", "present", "present"],
        )

    def test_all_correct_guess_marks_every_letter_correct(self):
        self.assertEqual(wordle._feedback("apple", "apple"), ["correct"] * 5)

    def test_no_overlap_marks_everything_absent(self):
        self.assertEqual(wordle._feedback("night", "world"), ["absent"] * 5)

    def test_apply_guess_rejects_wrong_length(self):
        with self.assertRaises(InvalidMove):
            wordle.apply_guess({"target": "apple", "guesses": []}, "ab")

    def test_apply_guess_rejects_non_alphabetic(self):
        with self.assertRaises(InvalidMove):
            wordle.apply_guess({"target": "apple", "guesses": []}, "a1234")

    def test_apply_guess_rejects_word_not_in_list(self):
        with self.assertRaises(InvalidMove):
            wordle.apply_guess({"target": "apple", "guesses": []}, "zzzzz")

    def test_game_status_won_on_first_guess(self):
        state = wordle.apply_guess({"target": "apple", "guesses": []}, "apple")
        self.assertEqual(wordle.game_status(state), "won")

    def test_game_status_lost_after_max_guesses(self):
        state = {"target": "apple", "guesses": []}
        for _ in range(wordle.MAX_GUESSES):
            state = wordle.apply_guess(state, "beach")
        self.assertEqual(wordle.game_status(state), "lost")

    def test_game_status_playing_before_max_guesses(self):
        state = {"target": "apple", "guesses": []}
        for _ in range(wordle.MAX_GUESSES - 1):
            state = wordle.apply_guess(state, "beach")
        self.assertEqual(wordle.game_status(state), "playing")


class WordleSessionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def test_new_game_stores_state_in_session(self):
        self.client.post(reverse("wordle-new"))
        self.assertIn("wordle_game", self.client.session)

    def test_winning_guess_records_result_with_guesses_remaining_score(self):
        self.client.post(reverse("wordle-new"))
        target = self.client.session["wordle_game"]["target"]
        distractor = next(w for w in wordle.WORD_LIST if w != target)
        self.client.post(reverse("wordle-guess"), {"guess": distractor})
        self.client.post(reverse("wordle-guess"), {"guess": distractor})
        self.client.post(reverse("wordle-guess"), {"guess": target})
        result = SinglePlayerResult.objects.get()
        self.assertTrue(result.won)
        self.assertEqual(result.score, wordle.MAX_GUESSES - 3 + 1)

    def test_exhausting_guesses_records_loss(self):
        self.client.post(reverse("wordle-new"))
        target = self.client.session["wordle_game"]["target"]
        distractor = next(w for w in wordle.WORD_LIST if w != target)
        for _ in range(wordle.MAX_GUESSES):
            self.client.post(reverse("wordle-guess"), {"guess": distractor})
        result = SinglePlayerResult.objects.get()
        self.assertFalse(result.won)
        self.assertEqual(result.score, 0)

    def test_guessing_after_game_over_does_not_record_twice(self):
        self.client.post(reverse("wordle-new"))
        target = self.client.session["wordle_game"]["target"]
        self.client.post(reverse("wordle-guess"), {"guess": target})
        distractor = next(w for w in wordle.WORD_LIST if w != target)
        self.client.post(reverse("wordle-guess"), {"guess": distractor})
        self.assertEqual(SinglePlayerResult.objects.count(), 1)

    def test_invalid_guess_does_not_consume_a_turn(self):
        self.client.post(reverse("wordle-new"))
        self.client.post(reverse("wordle-guess"), {"guess": "zzzzz"})
        state = self.client.session["wordle_game"]
        self.assertEqual(state["guesses"], [])

    def test_anonymous_cannot_play(self):
        self.client.logout()
        response = self.client.post(reverse("wordle-new"))
        self.assertEqual(response.status_code, 302)


class MastermindLogicTests(TestCase):
    def test_initial_state_has_secret_of_code_length_and_no_guesses(self):
        state = mastermind.initial_state()
        self.assertEqual(len(state["secret"]), mastermind.CODE_LENGTH)
        self.assertTrue(all(c in mastermind.COLORS for c in state["secret"]))
        self.assertEqual(state["guesses"], [])

    def test_feedback_all_black_on_exact_match(self):
        secret = ["red", "green", "blue", "yellow"]
        black, white = mastermind._feedback(secret, secret)
        self.assertEqual((black, white), (4, 0))

    def test_feedback_no_overlap_is_zero_zero(self):
        black, white = mastermind._feedback(["red", "red", "red", "red"], ["blue", "blue", "blue", "blue"])
        self.assertEqual((black, white), (0, 0))

    def test_feedback_handles_duplicate_colors_correctly(self):
        # secret has two reds; guess has two reds in different spots plus a
        # third red - the third can't earn a peg since only 2 reds exist.
        secret = ["red", "red", "green", "yellow"]
        guess = ["green", "red", "red", "red"]
        black, white = mastermind._feedback(secret, guess)
        self.assertEqual((black, white), (1, 2))

    def test_apply_guess_rejects_wrong_length(self):
        state = mastermind.initial_state()
        with self.assertRaises(InvalidMove):
            mastermind.apply_guess(state, ["red", "green", "blue"])

    def test_apply_guess_rejects_unknown_color(self):
        state = mastermind.initial_state()
        with self.assertRaises(InvalidMove):
            mastermind.apply_guess(state, ["red", "green", "blue", "black"])

    def test_game_status_won_on_all_black(self):
        secret = ["red", "green", "blue", "yellow"]
        state = mastermind.apply_guess({"secret": secret, "guesses": []}, secret)
        self.assertEqual(mastermind.game_status(state), "won")

    def test_game_status_lost_after_max_guesses(self):
        secret = ["red", "red", "red", "red"]
        state = {"secret": secret, "guesses": []}
        for _ in range(mastermind.MAX_GUESSES):
            state = mastermind.apply_guess(state, ["blue", "blue", "blue", "blue"])
        self.assertEqual(mastermind.game_status(state), "lost")

    def test_game_status_playing_before_max_guesses(self):
        secret = ["red", "red", "red", "red"]
        state = {"secret": secret, "guesses": []}
        for _ in range(mastermind.MAX_GUESSES - 1):
            state = mastermind.apply_guess(state, ["blue", "blue", "blue", "blue"])
        self.assertEqual(mastermind.game_status(state), "playing")


class MastermindSessionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def test_new_game_stores_state_in_session(self):
        self.client.post(reverse("mastermind-new"))
        self.assertIn("mastermind_game", self.client.session)

    def test_winning_guess_records_result_with_guesses_remaining_score(self):
        self.client.post(reverse("mastermind-new"))
        secret = self.client.session["mastermind_game"]["secret"]
        distractor = ["red" if c != "red" else "blue" for c in secret]
        self.client.post(reverse("mastermind-guess"), {"peg": distractor})
        self.client.post(reverse("mastermind-guess"), {"peg": distractor})
        self.client.post(reverse("mastermind-guess"), {"peg": secret})
        result = SinglePlayerResult.objects.get()
        self.assertTrue(result.won)
        self.assertEqual(result.score, mastermind.MAX_GUESSES - 3 + 1)

    def test_exhausting_guesses_records_loss(self):
        self.client.post(reverse("mastermind-new"))
        secret = self.client.session["mastermind_game"]["secret"]
        distractor = ["red" if c != "red" else "blue" for c in secret]
        for _ in range(mastermind.MAX_GUESSES):
            self.client.post(reverse("mastermind-guess"), {"peg": distractor})
        result = SinglePlayerResult.objects.get()
        self.assertFalse(result.won)
        self.assertEqual(result.score, 0)

    def test_guessing_after_game_over_does_not_record_twice(self):
        self.client.post(reverse("mastermind-new"))
        secret = self.client.session["mastermind_game"]["secret"]
        self.client.post(reverse("mastermind-guess"), {"peg": secret})
        distractor = ["red" if c != "red" else "blue" for c in secret]
        self.client.post(reverse("mastermind-guess"), {"peg": distractor})
        self.assertEqual(SinglePlayerResult.objects.count(), 1)

    def test_invalid_guess_does_not_consume_a_turn(self):
        self.client.post(reverse("mastermind-new"))
        self.client.post(reverse("mastermind-guess"), {"peg": ["red", "green"]})
        state = self.client.session["mastermind_game"]
        self.assertEqual(state["guesses"], [])

    def test_anonymous_cannot_play(self):
        self.client.logout()
        response = self.client.post(reverse("mastermind-new"))
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

    def test_othello_leaderboard_orders_by_wins(self):
        Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            status=Match.Status.FINISHED, winner=self.alice,
        )
        Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.carol,
            status=Match.Status.FINISHED, winner=self.alice,
        )
        Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.bob, player2=self.carol,
            status=Match.Status.FINISHED, winner=self.bob,
        )
        response = self.client.get(reverse("games-leaderboard"))
        leaders = list(response.context["othello_leaders"])
        self.assertEqual(leaders[0]["winner__username"], "alice")
        self.assertEqual(leaders[0]["wins"], 2)

    def test_wordle_leaderboard_orders_by_high_score(self):
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.WORDLE, score=3)
        SinglePlayerResult.objects.create(player=self.alice, game=SinglePlayerResult.Game.WORDLE, score=6)
        SinglePlayerResult.objects.create(player=self.bob, game=SinglePlayerResult.Game.WORDLE, score=4)
        response = self.client.get(reverse("games-leaderboard"))
        leaders = list(response.context["wordle_leaders"])
        self.assertEqual(leaders[0]["player__username"], "alice")
        self.assertEqual(leaders[0]["high_score"], 6)

    def test_leaderboard_is_publicly_accessible(self):
        response = self.client.get(reverse("games-leaderboard"))
        self.assertEqual(response.status_code, 200)


class ConnectFourLogicTests(TestCase):
    def test_initial_state_is_empty_board(self):
        state = connect_four.initial_state()
        self.assertEqual(len(state["board"]), 6)
        self.assertTrue(all(len(row) == 7 for row in state["board"]))
        self.assertTrue(all(cell is None for row in state["board"] for cell in row))

    def test_apply_move_lands_in_bottom_row(self):
        state = connect_four.apply_move(connect_four.initial_state(), 3, "X")
        self.assertEqual(state["board"][5][3], "X")

    def test_apply_move_stacks_on_top(self):
        state = connect_four.apply_move(connect_four.initial_state(), 3, "X")
        state = connect_four.apply_move(state, 3, "O")
        self.assertEqual(state["board"][5][3], "X")
        self.assertEqual(state["board"][4][3], "O")

    def test_apply_move_rejects_out_of_range_column(self):
        with self.assertRaises(InvalidMove):
            connect_four.apply_move(connect_four.initial_state(), 7, "X")

    def test_apply_move_rejects_full_column(self):
        state = connect_four.initial_state()
        for i in range(6):
            state = connect_four.apply_move(state, 0, "X" if i % 2 == 0 else "O")
        with self.assertRaises(InvalidMove):
            connect_four.apply_move(state, 0, "X")

    def test_check_winner_detects_horizontal(self):
        board = [[None] * 7 for _ in range(6)]
        for c in range(4):
            board[5][c] = "X"
        self.assertEqual(connect_four.check_winner({"board": board}), "X")

    def test_check_winner_detects_vertical(self):
        board = [[None] * 7 for _ in range(6)]
        for r in range(2, 6):
            board[r][0] = "O"
        self.assertEqual(connect_four.check_winner({"board": board}), "O")

    def test_check_winner_detects_diagonal_down_right(self):
        board = [[None] * 7 for _ in range(6)]
        for i in range(4):
            board[i][i] = "X"
        self.assertEqual(connect_four.check_winner({"board": board}), "X")

    def test_check_winner_detects_diagonal_down_left(self):
        board = [[None] * 7 for _ in range(6)]
        for i in range(4):
            board[i][3 - i] = "O"
        self.assertEqual(connect_four.check_winner({"board": board}), "O")

    def test_check_winner_detects_full_board_draw(self):
        # No four-in-a-row anywhere: alternate columns in a striped pattern
        # that never lines up 4 in any of the 4 scanned directions.
        pattern = ["X", "X", "O", "O", "X", "X", "O"]
        board = [list(pattern) for _ in range(6)]
        for r in range(1, 6, 2):
            board[r] = [("O" if v == "X" else "X") for v in board[r]]
        self.assertIn(connect_four.check_winner({"board": board}), ("draw", None))

    def test_check_winner_returns_none_mid_game(self):
        state = connect_four.apply_move(connect_four.initial_state(), 0, "X")
        self.assertIsNone(connect_four.check_winner(state))


class ConnectFourMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("connect4-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("connect4-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.CONNECT_FOUR)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("connect4-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state=connect_four.initial_state(), turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("connect4-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_move_by_wrong_player_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state=connect_four.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("connect4-move", args=[match.pk]), {"column": 0})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertTrue(all(cell is None for row in match.state["board"] for cell in row))

    def test_move_on_full_column_is_ignored(self):
        state = connect_four.initial_state()
        for i in range(6):
            state = connect_four.apply_move(state, 0, "X" if i % 2 == 0 else "O")
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("connect4-move", args=[match.pk]), {"column": 0})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)

    def test_valid_move_switches_turn(self):
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state=connect_four.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("connect4-move", args=[match.pk]), {"column": 3})
        match.refresh_from_db()
        self.assertEqual(match.state["board"][5][3], "X")
        self.assertEqual(match.turn, self.bob)

    def test_winning_move_finishes_match(self):
        board = [[None] * 7 for _ in range(6)]
        board[5][0] = board[5][1] = board[5][2] = "X"
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state={"board": board}, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("connect4-move", args=[match.pk]), {"column": 3})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.alice)
        self.assertIsNone(match.turn)

    def test_draw_finishes_match_with_no_winner(self):
        pattern = ["X", "X", "O", "O", "X", "X", "O"]
        board = [list(pattern) for _ in range(6)]
        for r in range(1, 6, 2):
            board[r] = [("O" if v == "X" else "X") for v in board[r]]
        # Leave the last cell open for the final move.
        board[5][6] = None
        match = Match.objects.create(
            game=Match.Game.CONNECT_FOUR, player1=self.alice, player2=self.bob,
            state={"board": board}, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("connect4-move", args=[match.pk]), {"column": 6})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)


def empty_checkers_board():
    return {"board": [[None] * 8 for _ in range(8)]}


class CheckersLogicTests(TestCase):
    def test_initial_state_places_pieces_correctly(self):
        state = checkers.initial_state()
        board = state["board"]
        black_count = sum(1 for row in board for cell in row if cell == "b")
        red_count = sum(1 for row in board for cell in row if cell == "r")
        self.assertEqual(black_count, 12)
        self.assertEqual(red_count, 12)
        for r in range(3):
            for c in range(8):
                if (r + c) % 2 == 1:
                    self.assertEqual(board[r][c], "b")
        for r in range(5, 8):
            for c in range(8):
                if (r + c) % 2 == 1:
                    self.assertEqual(board[r][c], "r")
        for r in range(3, 5):
            self.assertTrue(all(cell is None for cell in board[r]))

    def test_valid_simple_move(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        new_state = checkers.apply_move(state, (2, 3), (3, 4), "b")
        self.assertEqual(new_state["board"][3][4], "b")
        self.assertIsNone(new_state["board"][2][3])

    def test_rejects_non_diagonal_move(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (2, 3), (3, 3), "b")

    def test_rejects_move_too_far(self):
        state = empty_checkers_board()
        state["board"][2][2] = "b"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (2, 2), (5, 5), "b")

    def test_rejects_occupied_destination(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        state["board"][3][4] = "r"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (2, 3), (3, 4), "b")

    def test_rejects_moving_another_players_piece(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (2, 3), (3, 4), "r")

    def test_rejects_backward_simple_move_for_non_king(self):
        state = empty_checkers_board()
        state["board"][3][3] = "b"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (3, 3), (2, 2), "b")

    def test_valid_capture_removes_piece(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        state["board"][3][4] = "r"
        new_state = checkers.apply_move(state, (2, 3), (4, 5), "b")
        self.assertEqual(new_state["board"][4][5], "b")
        self.assertIsNone(new_state["board"][3][4])
        self.assertIsNone(new_state["board"][2][3])

    def test_rejects_capture_over_own_piece(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        state["board"][3][4] = "b"
        with self.assertRaises(InvalidMove):
            checkers.apply_move(state, (2, 3), (4, 5), "b")

    def test_backward_capture_succeeds_for_non_king(self):
        state = empty_checkers_board()
        state["board"][5][3] = "b"
        state["board"][4][2] = "r"
        new_state = checkers.apply_move(state, (5, 3), (3, 1), "b")
        self.assertEqual(new_state["board"][3][1], "b")
        self.assertIsNone(new_state["board"][4][2])

    def test_king_promotion_on_reaching_far_row(self):
        state = empty_checkers_board()
        state["board"][6][3] = "b"
        new_state = checkers.apply_move(state, (6, 3), (7, 4), "b")
        self.assertEqual(new_state["board"][7][4], "B")

    def test_promoted_king_can_move_backward(self):
        state = empty_checkers_board()
        state["board"][4][3] = "B"
        new_state = checkers.apply_move(state, (4, 3), (3, 2), "b")
        self.assertEqual(new_state["board"][3][2], "B")

    def test_legal_moves_exist_is_false_when_boxed_in(self):
        state = empty_checkers_board()
        state["board"][7][7] = "b"
        self.assertFalse(checkers.legal_moves_exist(state, "b"))

    def test_legal_moves_exist_true_when_only_capture_available(self):
        state = empty_checkers_board()
        state["board"][3][3] = "b"
        state["board"][4][2] = "b"
        state["board"][4][4] = "b"
        state["board"][2][2] = "r"
        self.assertTrue(checkers.legal_moves_exist(state, "b"))

    def test_check_winner_when_opponent_has_no_pieces(self):
        state = empty_checkers_board()
        state["board"][2][3] = "b"
        self.assertEqual(checkers.check_winner(state, "r"), "b")

    def test_check_winner_when_opponent_has_no_legal_moves(self):
        state = empty_checkers_board()
        state["board"][7][7] = "b"
        state["board"][0][0] = "r"
        self.assertEqual(checkers.check_winner(state, "b"), "r")

    def test_check_winner_returns_none_mid_game(self):
        state = checkers.initial_state()
        self.assertIsNone(checkers.check_winner(state, "r"))


class CheckersMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("checkers-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("checkers-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.CHECKERS)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)
        black_count = sum(1 for row in match.state["board"] for cell in row if cell == "b")
        red_count = sum(1 for row in match.state["board"] for cell in row if cell == "r")
        self.assertEqual((black_count, red_count), (12, 12))

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.alice, player2=self.bob,
            state=checkers.initial_state(), turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("checkers-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_move_by_wrong_player_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.alice, player2=self.bob,
            state=checkers.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(
            reverse("checkers-move", args=[match.pk]),
            {"from_row": 2, "from_col": 1, "to_row": 3, "to_col": 0},
        )
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["board"], checkers.initial_state()["board"])

    def test_invalid_move_leaves_state_unchanged(self):
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.alice, player2=self.bob,
            state=checkers.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(
            reverse("checkers-move", args=[match.pk]),
            {"from_row": 3, "from_col": 3, "to_row": 4, "to_col": 4},
        )
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["board"], checkers.initial_state()["board"])

    def test_valid_simple_move_switches_turn(self):
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.alice, player2=self.bob,
            state=checkers.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        # player1 is always "r" (red), starting at the bottom, moving up.
        self.client.post(
            reverse("checkers-move", args=[match.pk]),
            {"from_row": 5, "from_col": 0, "to_row": 4, "to_col": 1},
        )
        match.refresh_from_db()
        self.assertEqual(match.state["board"][4][1], "r")
        self.assertIsNone(match.state["board"][5][0])
        self.assertEqual(match.turn, self.bob)

    def test_valid_capture_removes_piece_and_switches_turn(self):
        # player1 (bob) is always "r"; player2 (alice) is "b". A second
        # black piece survives the capture so the match isn't finished.
        state = empty_checkers_board()
        state["board"][3][3] = "r"
        state["board"][4][4] = "b"
        state["board"][0][0] = "b"
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.bob, player2=self.alice,
            state=state, turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(
            reverse("checkers-move", args=[match.pk]),
            {"from_row": 3, "from_col": 3, "to_row": 5, "to_col": 5},
        )
        match.refresh_from_db()
        self.assertEqual(match.state["board"][5][5], "r")
        self.assertIsNone(match.state["board"][4][4])
        self.assertEqual(match.turn, self.alice)

    def test_capturing_last_piece_finishes_match(self):
        state = empty_checkers_board()
        state["board"][3][3] = "r"
        state["board"][4][4] = "b"
        match = Match.objects.create(
            game=Match.Game.CHECKERS, player1=self.bob, player2=self.alice,
            state=state, turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(
            reverse("checkers-move", args=[match.pk]),
            {"from_row": 3, "from_col": 3, "to_row": 5, "to_col": 5},
        )
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.bob)
        self.assertIsNone(match.turn)


def empty_othello_board():
    return {"board": [[None] * 8 for _ in range(8)]}


class OthelloLogicTests(TestCase):
    def test_initial_state_places_center_diamond(self):
        state = othello.initial_state()
        self.assertEqual(state["board"][3][3], "W")
        self.assertEqual(state["board"][3][4], "B")
        self.assertEqual(state["board"][4][3], "B")
        self.assertEqual(state["board"][4][4], "W")

    def test_legal_moves_are_the_four_known_opening_moves_for_black(self):
        state = othello.initial_state()
        self.assertEqual(sorted(othello.legal_moves(state, "B")), [(2, 3), (3, 2), (4, 5), (5, 4)])

    def test_legal_moves_excludes_non_bracketing_empty_cell(self):
        state = othello.initial_state()
        self.assertNotIn((0, 0), othello.legal_moves(state, "B"))

    def test_apply_move_flips_single_direction(self):
        state = othello.initial_state()
        new_state = othello.apply_move(state, 2, 3, "B")
        self.assertEqual(new_state["board"][3][3], "B")
        self.assertEqual(new_state["board"][2][3], "B")

    def test_apply_move_flips_multiple_directions_at_once(self):
        state = empty_othello_board()
        state["board"][2][4] = "B"
        state["board"][3][4] = "W"
        state["board"][4][0] = "B"
        state["board"][4][1] = "W"
        state["board"][4][2] = "W"
        state["board"][4][3] = "W"
        new_state = othello.apply_move(state, 4, 4, "B")
        # Vertical flip above, and horizontal flip to the left, both at once.
        self.assertEqual(new_state["board"][3][4], "B")
        self.assertEqual(new_state["board"][4][1], "B")
        self.assertEqual(new_state["board"][4][2], "B")
        self.assertEqual(new_state["board"][4][3], "B")

    def test_apply_move_rejects_non_bracketing_cell(self):
        state = othello.initial_state()
        with self.assertRaises(InvalidMove):
            othello.apply_move(state, 0, 0, "B")

    def test_apply_move_rejects_occupied_cell(self):
        state = othello.initial_state()
        with self.assertRaises(InvalidMove):
            othello.apply_move(state, 3, 3, "B")

    def test_next_turn_state_passes_when_only_opponent_is_stuck(self):
        state = empty_othello_board()
        state["board"] = [["B"] * 8 for _ in range(8)]
        state["board"][0][0] = None
        state["board"][0][1] = "W"
        self.assertEqual(othello.next_turn_state(state, "B", "W"), ("pass", "B"))

    def test_next_turn_state_ends_game_by_piece_count(self):
        state = empty_othello_board()
        state["board"] = [["B"] * 8 for _ in range(8)]
        for c in range(8):
            state["board"][0][c] = "W"
            state["board"][1][c] = "W"
            state["board"][2][c] = "W"
        # 40 Black, 24 White - fully packed, nobody has a legal move.
        self.assertEqual(othello.next_turn_state(state, "B", "W"), ("game_over", "B"))

    def test_next_turn_state_is_a_tie_on_equal_piece_count(self):
        state = empty_othello_board()
        state["board"] = [["B"] * 8 for _ in range(8)]
        for r in range(4):
            for c in range(8):
                state["board"][r][c] = "W"
        self.assertEqual(othello.next_turn_state(state, "B", "W"), ("game_over", None))


class OthelloMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("othello-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("othello-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.OTHELLO)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("othello-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state=othello.initial_state(), turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("othello-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_move_by_wrong_player_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state=othello.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("othello-move", args=[match.pk]), {"row": 2, "col": 3})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["board"], othello.initial_state()["board"])

    def test_illegal_move_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state=othello.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("othello-move", args=[match.pk]), {"row": 0, "col": 0})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["board"], othello.initial_state()["board"])

    def test_valid_move_flips_pieces_and_switches_turn(self):
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state=othello.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        # player1 (alice) is always Black.
        self.client.post(reverse("othello-move", args=[match.pk]), {"row": 2, "col": 3})
        match.refresh_from_db()
        self.assertEqual(match.state["board"][3][3], "B")
        self.assertEqual(match.turn, self.bob)

    def test_move_that_leaves_opponent_stuck_passes_turn_back(self):
        board = [["W"] * 8 for _ in range(8)]
        board[0][0] = None
        board[0][1] = "B"
        board[4][4] = None
        board[4][5] = "B"
        # Bob (player2, White) has two independent moves available: (0,0)
        # and (4,4). Playing (0,0) flips Black's only other piece away,
        # leaving Alice (Black) with no legal move anywhere - but Bob still
        # has (4,4), so the turn should pass back to Bob, not switch.
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state={"board": board}, turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("othello-move", args=[match.pk]), {"row": 0, "col": 0})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.ACTIVE)
        self.assertEqual(match.turn, self.bob)

    def test_move_that_ends_game_sets_winner_by_piece_count(self):
        board = [["W"] * 8 for _ in range(8)]
        board[0][0] = None
        board[0][1] = "B"
        # The only empty cell left; Bob (White) filling it flips Black's
        # only remaining piece, completing a full, all-White board.
        match = Match.objects.create(
            game=Match.Game.OTHELLO, player1=self.alice, player2=self.bob,
            state={"board": board}, turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("othello-move", args=[match.pk]), {"row": 0, "col": 0})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.bob)
        self.assertIsNone(match.turn)


class NimLogicTests(TestCase):
    def test_initial_state_has_three_piles(self):
        state = nim.initial_state()
        self.assertEqual(state["piles"], [3, 5, 7])

    def test_apply_move_removes_from_one_pile(self):
        state = nim.apply_move({"piles": [3, 5, 7]}, 1, 2)
        self.assertEqual(state["piles"], [3, 3, 7])

    def test_apply_move_does_not_mutate_original_state(self):
        original = {"piles": [3, 5, 7]}
        nim.apply_move(original, 0, 1)
        self.assertEqual(original["piles"], [3, 5, 7])

    def test_taking_more_than_the_pile_has_is_invalid(self):
        with self.assertRaises(InvalidMove):
            nim.apply_move({"piles": [3, 5, 7]}, 0, 4)

    def test_taking_zero_is_invalid(self):
        with self.assertRaises(InvalidMove):
            nim.apply_move({"piles": [3, 5, 7]}, 0, 0)

    def test_pile_index_out_of_range_is_invalid(self):
        with self.assertRaises(InvalidMove):
            nim.apply_move({"piles": [3, 5, 7]}, 3, 1)

    def test_is_game_over_false_while_any_pile_has_sticks(self):
        self.assertFalse(nim.is_game_over({"piles": [0, 0, 1]}))

    def test_is_game_over_true_when_all_piles_empty(self):
        self.assertTrue(nim.is_game_over({"piles": [0, 0, 0]}))


class NimMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("nim-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("nim-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.NIM)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("nim-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        match = Match.objects.create(
            game=Match.Game.NIM, player1=self.alice, player2=self.bob,
            state=nim.initial_state(), turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("nim-match", args=[match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_move_by_wrong_player_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.NIM, player1=self.alice, player2=self.bob,
            state=nim.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("nim-move", args=[match.pk]), {"pile": 0, "count": 1})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["piles"], [3, 5, 7])

    def test_illegal_move_is_ignored(self):
        match = Match.objects.create(
            game=Match.Game.NIM, player1=self.alice, player2=self.bob,
            state=nim.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("nim-move", args=[match.pk]), {"pile": 0, "count": 99})
        match.refresh_from_db()
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.state["piles"], [3, 5, 7])

    def test_valid_move_switches_turn(self):
        match = Match.objects.create(
            game=Match.Game.NIM, player1=self.alice, player2=self.bob,
            state=nim.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("nim-move", args=[match.pk]), {"pile": 2, "count": 3})
        match.refresh_from_db()
        self.assertEqual(match.state["piles"], [3, 5, 4])
        self.assertEqual(match.turn, self.bob)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_taking_the_last_stick_wins_the_match(self):
        match = Match.objects.create(
            game=Match.Game.NIM, player1=self.alice, player2=self.bob,
            state={"piles": [0, 0, 1]}, turn=self.bob,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("nim-move", args=[match.pk]), {"pile": 2, "count": 1})
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.FINISHED)
        self.assertEqual(match.winner, self.bob)
        self.assertIsNone(match.turn)


class BattleshipLogicTests(TestCase):
    def test_initial_state_is_placement_phase_with_no_boards(self):
        state = battleship.initial_state()
        self.assertEqual(state["phase"], "placement")
        self.assertEqual(state["boards"], {})

    def test_apply_placement_places_first_ship_horizontally(self):
        state = battleship.apply_placement(battleship.initial_state(), "u1", 0, 0, "h")
        self.assertEqual(state["boards"]["u1"]["ships"], [[[0, 0], [0, 1], [0, 2], [0, 3]]])

    def test_apply_placement_places_ship_vertically(self):
        state = battleship.apply_placement(battleship.initial_state(), "u1", 0, 0, "v")
        self.assertEqual(state["boards"]["u1"]["ships"], [[[0, 0], [1, 0], [2, 0], [3, 0]]])

    def test_apply_placement_does_not_mutate_original_state(self):
        original = battleship.initial_state()
        battleship.apply_placement(original, "u1", 0, 0, "h")
        self.assertEqual(original["boards"], {})

    def test_apply_placement_rejects_off_board_ship(self):
        with self.assertRaises(InvalidMove):
            battleship.apply_placement(battleship.initial_state(), "u1", 0, 6, "h")

    def test_apply_placement_rejects_overlap(self):
        state = battleship.apply_placement(battleship.initial_state(), "u1", 0, 0, "h")
        with self.assertRaises(InvalidMove):
            battleship.apply_placement(state, "u1", 0, 3, "v")

    def test_apply_placement_rejects_a_fifth_ship(self):
        # Place all 4 fleet ships, each far enough apart not to overlap.
        state = battleship.initial_state()
        state = battleship.apply_placement(state, "u1", 0, 0, "h")
        state = battleship.apply_placement(state, "u1", 2, 0, "h")
        state = battleship.apply_placement(state, "u1", 4, 0, "h")
        state = battleship.apply_placement(state, "u1", 6, 0, "h")
        with self.assertRaises(InvalidMove):
            battleship.apply_placement(state, "u1", 7, 0, "h")

    def test_apply_placement_rejects_bad_orientation(self):
        with self.assertRaises(InvalidMove):
            battleship.apply_placement(battleship.initial_state(), "u1", 0, 0, "diagonal")

    def test_is_fully_placed(self):
        state = battleship.initial_state()
        state = battleship.apply_placement(state, "u1", 0, 0, "h")
        state = battleship.apply_placement(state, "u1", 2, 0, "h")
        state = battleship.apply_placement(state, "u1", 4, 0, "h")
        self.assertFalse(battleship.is_fully_placed(state, "u1"))
        state = battleship.apply_placement(state, "u1", 6, 0, "h")
        self.assertTrue(battleship.is_fully_placed(state, "u1"))

    def test_both_players_placed_requires_both(self):
        state = battleship.initial_state()
        state = battleship.apply_placement(state, "u1", 0, 0, "h")
        self.assertFalse(battleship.both_players_placed(state, "u1", "u2"))

    def test_apply_shot_records_shot_against_target(self):
        state = battleship.initial_state()
        state = battleship.apply_shot(state, "u2", 3, 4)
        self.assertEqual(state["boards"]["u2"]["shots_against"], [[3, 4]])

    def test_apply_shot_rejects_off_board(self):
        with self.assertRaises(InvalidMove):
            battleship.apply_shot(battleship.initial_state(), "u2", 8, 0)

    def test_apply_shot_rejects_repeat_shot(self):
        state = battleship.apply_shot(battleship.initial_state(), "u2", 3, 4)
        with self.assertRaises(InvalidMove):
            battleship.apply_shot(state, "u2", 3, 4)

    def test_is_hit_true_on_ship_cell(self):
        state = battleship.apply_placement(battleship.initial_state(), "u2", 0, 0, "h")
        self.assertTrue(battleship.is_hit(state, "u2", 0, 0))
        self.assertFalse(battleship.is_hit(state, "u2", 5, 5))

    def test_all_ships_sunk_false_until_every_cell_hit(self):
        state = battleship.apply_placement(battleship.initial_state(), "u2", 0, 0, "h")
        self.assertFalse(battleship.all_ships_sunk(state, "u2"))
        for col in range(4):
            state = battleship.apply_shot(state, "u2", 0, col)
        self.assertTrue(battleship.all_ships_sunk(state, "u2"))

    def test_all_ships_sunk_false_with_no_ships_placed_yet(self):
        self.assertFalse(battleship.all_ships_sunk(battleship.initial_state(), "u2"))

    def test_viewer_state_never_exposes_opponent_ship_layout(self):
        state = battleship.initial_state()
        state = battleship.apply_placement(state, "alice", 0, 0, "h")
        state = battleship.apply_placement(state, "bob", 5, 3, "h")
        state = battleship.apply_shot(state, "bob", 5, 5)  # alice hits bob
        state = battleship.apply_shot(state, "bob", 7, 7)  # alice misses

        viewer = battleship.viewer_state(state, "alice", "bob")
        self.assertEqual(viewer["your_ships"], state["boards"]["alice"]["ships"])
        self.assertNotIn("ships", viewer)
        self.assertCountEqual(
            viewer["your_shots"],
            [{"row": 5, "col": 5, "hit": True}, {"row": 7, "col": 7, "hit": False}],
        )
        # Bob's unfired-upon ship cells (5,3)/(5,4)/(5,6) must not appear anywhere.
        flattened = str(viewer)
        self.assertNotIn("[5, 3]", flattened)
        self.assertNotIn("[5, 4]", flattened)
        self.assertNotIn("[5, 6]", flattened)


class BattleshipMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def _place_full_fleet(self, user, row_offset=0):
        for i, _ in enumerate(battleship.FLEET):
            self.client.force_login(user)
            self.client.post(
                reverse("battleship-place", args=[self.match.pk]),
                {"cell": f"{row_offset + i * 2},0", "orientation": "h"},
            )

    def test_challenge_creates_active_match_in_placement_phase(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("battleship-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("battleship-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.BATTLESHIP)
        self.assertEqual(match.state["phase"], "placement")
        self.assertIsNone(match.turn)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("battleship-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob,
            state=battleship.initial_state(), turn=None,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("battleship-match", args=[self.match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_placing_ship_appends_to_boards(self):
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob,
            state=battleship.initial_state(), turn=None,
        )
        self.client.force_login(self.alice)
        self.client.post(
            reverse("battleship-place", args=[self.match.pk]), {"cell": "0,0", "orientation": "h"}
        )
        self.match.refresh_from_db()
        self.assertEqual(len(self.match.state["boards"][str(self.alice.id)]["ships"]), 1)

    def test_invalid_placement_is_ignored_and_shows_an_error(self):
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob,
            state=battleship.initial_state(), turn=None,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("battleship-place", args=[self.match.pk]), {"cell": "0,6", "orientation": "h"}, follow=True
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["boards"], {})
        self.assertContains(response, "fit on the board")

    def test_cannot_fire_before_both_players_have_placed(self):
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob,
            state=battleship.initial_state(), turn=None,
        )
        self._place_full_fleet(self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse("battleship-move", args=[self.match.pk]), {"row": 0, "col": 0})
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["phase"], "placement")

    def test_phase_flips_to_battle_once_both_have_placed(self):
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob,
            state=battleship.initial_state(), turn=None,
        )
        self._place_full_fleet(self.alice)
        self._place_full_fleet(self.bob, row_offset=1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["phase"], "battle")
        self.assertEqual(self.match.turn, self.alice)

    def test_move_by_wrong_player_is_ignored(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"ships": [[[3, 3], [3, 4]]], "shots_against": []},
                str(self.bob.id): {"ships": [[[0, 0], [0, 1]]], "shots_against": []},
            },
        }
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("battleship-move", args=[self.match.pk]), {"row": 0, "col": 0})
        self.match.refresh_from_db()
        self.assertEqual(self.match.turn, self.alice)
        self.assertEqual(self.match.state["boards"][str(self.alice.id)]["shots_against"], [])

    def test_sinking_all_ships_wins_the_match(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"ships": [[[3, 3], [3, 4], [3, 5], [3, 6]]], "shots_against": []},
                str(self.bob.id): {"ships": [[[0, 0], [0, 1]]], "shots_against": []},
            },
        }
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("battleship-move", args=[self.match.pk]), {"row": 0, "col": 0})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.ACTIVE)
        self.assertEqual(self.match.turn, self.bob)

        self.client.force_login(self.bob)
        self.client.post(reverse("battleship-move", args=[self.match.pk]), {"row": 7, "col": 7})
        self.match.refresh_from_db()
        self.assertEqual(self.match.turn, self.alice)

        self.client.force_login(self.alice)
        self.client.post(reverse("battleship-move", args=[self.match.pk]), {"row": 0, "col": 1})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(self.match.winner, self.alice)
        self.assertIsNone(self.match.turn)

    def test_opponent_board_context_never_includes_ship_positions(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"ships": [[[0, 0], [0, 1], [0, 2], [0, 3]]], "shots_against": []},
                str(self.bob.id): {"ships": [[[5, 5], [5, 6]]], "shots_against": []},
            },
        }
        self.match = Match.objects.create(
            game=Match.Game.BATTLESHIP, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("battleship-match", args=[self.match.pk]))
        for row in response.context["opponent_board_cells"]:
            for cell in row:
                self.assertNotIn("ship", cell)
        your_cells = response.context["your_board_cells"]
        self.assertTrue(any(cell["ship"] for row in your_cells for cell in row))


class StrategoLogicTests(TestCase):
    def test_initial_state_is_placement_phase_with_no_boards(self):
        state = stratego.initial_state()
        self.assertEqual(state["phase"], "placement")
        self.assertEqual(state["boards"], {})
        self.assertIsNone(state["last_combat"])

    def test_apply_placement_places_piece_in_own_zone(self):
        state = stratego.apply_placement(stratego.initial_state(), "u1", 1, 2, stratego.PLAYER1_ROWS)
        self.assertEqual(state["boards"]["u1"]["pieces"][0]["rank"], stratego.FLEET[0])
        self.assertEqual((state["boards"]["u1"]["pieces"][0]["row"], state["boards"]["u1"]["pieces"][0]["col"]), (1, 2))
        self.assertFalse(state["boards"]["u1"]["pieces"][0]["revealed"])

    def test_apply_placement_rejects_outside_own_zone(self):
        with self.assertRaises(InvalidMove):
            stratego.apply_placement(stratego.initial_state(), "u1", 5, 2, stratego.PLAYER1_ROWS)

    def test_apply_placement_rejects_occupied_cell(self):
        state = stratego.apply_placement(stratego.initial_state(), "u1", 1, 2, stratego.PLAYER1_ROWS)
        with self.assertRaises(InvalidMove):
            stratego.apply_placement(state, "u1", 1, 2, stratego.PLAYER1_ROWS)

    def test_apply_placement_rejects_once_fleet_is_full(self):
        state = stratego.initial_state()
        for i in range(len(stratego.FLEET)):
            state = stratego.apply_placement(state, "u1", i // 8, i % 8, stratego.PLAYER1_ROWS)
        with self.assertRaises(InvalidMove):
            stratego.apply_placement(state, "u1", 2, 7, stratego.PLAYER1_ROWS)

    def test_apply_placement_does_not_mutate_original_state(self):
        original = stratego.initial_state()
        stratego.apply_placement(original, "u1", 1, 2, stratego.PLAYER1_ROWS)
        self.assertEqual(original["boards"], {})

    def test_is_fully_placed_and_both_players_placed(self):
        state = stratego.initial_state()
        for i in range(len(stratego.FLEET)):
            state = stratego.apply_placement(state, "u1", i // 8, i % 8, stratego.PLAYER1_ROWS)
        self.assertTrue(stratego.is_fully_placed(state, "u1"))
        self.assertFalse(stratego.both_players_placed(state, "u1", "u2"))

    def test_resolve_combat_higher_rank_wins(self):
        marshal = {"rank": "marshal"}
        captain = {"rank": "captain"}
        self.assertEqual(stratego.resolve_combat(marshal, captain), "attacker_wins")
        self.assertEqual(stratego.resolve_combat(captain, marshal), "defender_wins")

    def test_resolve_combat_tie_on_equal_rank(self):
        self.assertEqual(stratego.resolve_combat({"rank": "captain"}, {"rank": "captain"}), "tie")

    def test_resolve_combat_spy_beats_marshal_when_attacking(self):
        self.assertEqual(stratego.resolve_combat({"rank": "spy"}, {"rank": "marshal"}), "attacker_wins")

    def test_resolve_combat_marshal_beats_spy_when_attacking(self):
        self.assertEqual(stratego.resolve_combat({"rank": "marshal"}, {"rank": "spy"}), "attacker_wins")

    def test_resolve_combat_bomb_defeats_non_miner_attacker(self):
        self.assertEqual(stratego.resolve_combat({"rank": "marshal"}, {"rank": "bomb"}), "defender_wins")

    def test_resolve_combat_miner_defuses_bomb(self):
        self.assertEqual(stratego.resolve_combat({"rank": "miner"}, {"rank": "bomb"}), "attacker_wins")

    def test_resolve_combat_any_attacker_captures_flag(self):
        self.assertEqual(stratego.resolve_combat({"rank": "scout"}, {"rank": "flag"}), "attacker_wins")

    def test_apply_move_to_empty_cell_just_relocates(self):
        state = {
            "phase": "battle",
            "boards": {
                "u1": {"pieces": [{"id": 0, "rank": "scout", "row": 3, "col": 3, "revealed": False}]},
                "u2": {"pieces": []},
            },
            "last_combat": None,
        }
        new_state = stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)
        piece = new_state["boards"]["u1"]["pieces"][0]
        self.assertEqual((piece["row"], piece["col"]), (3, 4))
        self.assertIsNone(new_state["last_combat"])

    def test_apply_move_rejects_immobile_piece(self):
        state = {
            "phase": "battle",
            "boards": {"u1": {"pieces": [{"id": 0, "rank": "bomb", "row": 3, "col": 3, "revealed": False}]}, "u2": {"pieces": []}},
            "last_combat": None,
        }
        with self.assertRaises(InvalidMove):
            stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)

    def test_apply_move_rejects_non_adjacent_destination(self):
        state = {
            "phase": "battle",
            "boards": {"u1": {"pieces": [{"id": 0, "rank": "scout", "row": 3, "col": 3, "revealed": False}]}, "u2": {"pieces": []}},
            "last_combat": None,
        }
        with self.assertRaises(InvalidMove):
            stratego.apply_move(state, "u1", "u2", 3, 3, 3, 5)
        with self.assertRaises(InvalidMove):
            stratego.apply_move(state, "u1", "u2", 3, 3, 4, 4)

    def test_apply_move_rejects_own_piece_at_destination(self):
        state = {
            "phase": "battle",
            "boards": {
                "u1": {
                    "pieces": [
                        {"id": 0, "rank": "scout", "row": 3, "col": 3, "revealed": False},
                        {"id": 1, "rank": "captain", "row": 3, "col": 4, "revealed": False},
                    ]
                },
                "u2": {"pieces": []},
            },
            "last_combat": None,
        }
        with self.assertRaises(InvalidMove):
            stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)

    def test_apply_move_combat_attacker_wins_reveals_both_and_removes_defender(self):
        state = {
            "phase": "battle",
            "boards": {
                "u1": {"pieces": [{"id": 0, "rank": "marshal", "row": 3, "col": 3, "revealed": False}]},
                "u2": {"pieces": [{"id": 0, "rank": "captain", "row": 3, "col": 4, "revealed": False}]},
            },
            "last_combat": None,
        }
        new_state = stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)
        self.assertEqual(new_state["boards"]["u2"]["pieces"], [])
        attacker = new_state["boards"]["u1"]["pieces"][0]
        self.assertEqual((attacker["row"], attacker["col"]), (3, 4))
        self.assertTrue(attacker["revealed"])
        self.assertEqual(new_state["last_combat"], {"attacker_rank": "marshal", "defender_rank": "captain", "outcome": "attacker_wins"})

    def test_apply_move_combat_defender_wins_removes_attacker_and_stays_put(self):
        state = {
            "phase": "battle",
            "boards": {
                "u1": {"pieces": [{"id": 0, "rank": "captain", "row": 3, "col": 3, "revealed": False}]},
                "u2": {"pieces": [{"id": 0, "rank": "marshal", "row": 3, "col": 4, "revealed": False}]},
            },
            "last_combat": None,
        }
        new_state = stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)
        self.assertEqual(new_state["boards"]["u1"]["pieces"], [])
        defender = new_state["boards"]["u2"]["pieces"][0]
        self.assertEqual((defender["row"], defender["col"]), (3, 4))
        self.assertTrue(defender["revealed"])

    def test_apply_move_combat_tie_removes_both(self):
        state = {
            "phase": "battle",
            "boards": {
                "u1": {"pieces": [{"id": 0, "rank": "captain", "row": 3, "col": 3, "revealed": False}]},
                "u2": {"pieces": [{"id": 0, "rank": "captain", "row": 3, "col": 4, "revealed": False}]},
            },
            "last_combat": None,
        }
        new_state = stratego.apply_move(state, "u1", "u2", 3, 3, 3, 4)
        self.assertEqual(new_state["boards"]["u1"]["pieces"], [])
        self.assertEqual(new_state["boards"]["u2"]["pieces"], [])

    def test_flag_captured_false_while_flag_remains(self):
        state = {"boards": {"u2": {"pieces": [{"id": 0, "rank": "flag", "row": 7, "col": 7, "revealed": False}]}}}
        self.assertFalse(stratego.flag_captured(state, "u2"))

    def test_flag_captured_true_once_removed(self):
        state = {"boards": {"u2": {"pieces": [{"id": 0, "rank": "scout", "row": 7, "col": 7, "revealed": False}]}}}
        self.assertTrue(stratego.flag_captured(state, "u2"))

    def test_viewer_state_hides_unrevealed_opponent_rank_but_shows_position(self):
        state = {
            "phase": "battle",
            "boards": {
                "alice": {"pieces": [{"id": 0, "rank": "marshal", "row": 0, "col": 0, "revealed": False}]},
                "bob": {
                    "pieces": [
                        {"id": 0, "rank": "captain", "row": 5, "col": 5, "revealed": False},
                        {"id": 1, "rank": "scout", "row": 6, "col": 6, "revealed": True},
                    ]
                },
            },
            "last_combat": None,
        }
        viewer = stratego.viewer_state(state, "alice", "bob")
        self.assertEqual(viewer["your_pieces"], state["boards"]["alice"]["pieces"])
        opponent_by_pos = {(p["row"], p["col"]): p["rank"] for p in viewer["opponent_pieces"]}
        self.assertEqual(opponent_by_pos[(5, 5)], None)
        self.assertEqual(opponent_by_pos[(6, 6)], "scout")
        self.assertEqual(set(opponent_by_pos), {(5, 5), (6, 6)})


class StrategoMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def _place_full_fleet(self, user, is_player1):
        zone_start = stratego.PLAYER1_ROWS[0] if is_player1 else stratego.PLAYER2_ROWS[0]
        self.client.force_login(user)
        for i in range(len(stratego.FLEET)):
            row, col = zone_start + i // 8, i % 8
            self.client.post(reverse("stratego-place", args=[self.match.pk]), {"cell": f"{row},{col}"})

    def test_challenge_creates_active_match_in_placement_phase(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("stratego-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("stratego-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.STRATEGO)
        self.assertEqual(match.state["phase"], "placement")
        self.assertIsNone(match.turn)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("stratego-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob,
            state=stratego.initial_state(), turn=None,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("stratego-match", args=[self.match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_placing_piece_appends_to_boards(self):
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob,
            state=stratego.initial_state(), turn=None,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("stratego-place", args=[self.match.pk]), {"cell": "0,0"})
        self.match.refresh_from_db()
        self.assertEqual(len(self.match.state["boards"][str(self.alice.id)]["pieces"]), 1)

    def test_placement_outside_own_zone_is_rejected_with_error(self):
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob,
            state=stratego.initial_state(), turn=None,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("stratego-place", args=[self.match.pk]), {"cell": "5,0"}, follow=True
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["boards"], {})
        self.assertContains(response, "own three rows")

    def test_cannot_move_before_both_players_have_placed(self):
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob,
            state=stratego.initial_state(), turn=None,
        )
        self._place_full_fleet(self.alice, is_player1=True)
        self.client.force_login(self.alice)
        self.client.post(
            reverse("stratego-move", args=[self.match.pk]), {"from_row": 0, "from_col": 0, "to_row": 1, "to_col": 0}
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["phase"], "placement")

    def test_phase_flips_to_battle_once_both_have_placed(self):
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob,
            state=stratego.initial_state(), turn=None,
        )
        self._place_full_fleet(self.alice, is_player1=True)
        self._place_full_fleet(self.bob, is_player1=False)
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["phase"], "battle")
        self.assertEqual(self.match.turn, self.alice)

    def test_move_by_wrong_player_is_ignored(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"pieces": [{"id": 0, "rank": "scout", "row": 3, "col": 3, "revealed": False}]},
                str(self.bob.id): {"pieces": [{"id": 0, "rank": "flag", "row": 7, "col": 7, "revealed": False}]},
            },
            "last_combat": None,
        }
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(
            reverse("stratego-move", args=[self.match.pk]), {"from_row": 7, "from_col": 7, "to_row": 6, "to_col": 7}
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.turn, self.alice)

    def test_combat_move_reveals_both_and_switches_turn(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"pieces": [{"id": 0, "rank": "marshal", "row": 3, "col": 3, "revealed": False}]},
                str(self.bob.id): {
                    "pieces": [
                        {"id": 0, "rank": "captain", "row": 3, "col": 4, "revealed": False},
                        {"id": 1, "rank": "flag", "row": 7, "col": 7, "revealed": False},
                    ]
                },
            },
            "last_combat": None,
        }
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(
            reverse("stratego-move", args=[self.match.pk]), {"from_row": 3, "from_col": 3, "to_row": 3, "to_col": 4}
        )
        self.match.refresh_from_db()
        self.assertEqual(len(self.match.state["boards"][str(self.bob.id)]["pieces"]), 1)
        self.assertEqual(self.match.status, Match.Status.ACTIVE)
        self.assertEqual(self.match.turn, self.bob)
        self.assertEqual(self.match.state["last_combat"]["outcome"], "attacker_wins")

    def test_capturing_flag_wins_the_match(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"pieces": [{"id": 0, "rank": "scout", "row": 3, "col": 3, "revealed": False}]},
                str(self.bob.id): {"pieces": [{"id": 0, "rank": "flag", "row": 3, "col": 4, "revealed": False}]},
            },
            "last_combat": None,
        }
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(
            reverse("stratego-move", args=[self.match.pk]), {"from_row": 3, "from_col": 3, "to_row": 3, "to_col": 4}
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(self.match.winner, self.alice)
        self.assertIsNone(self.match.turn)

    def test_opponent_board_context_never_exposes_unrevealed_rank(self):
        state = {
            "phase": "battle",
            "boards": {
                str(self.alice.id): {"pieces": [{"id": 0, "rank": "marshal", "row": 0, "col": 0, "revealed": False}]},
                str(self.bob.id): {"pieces": [{"id": 0, "rank": "captain", "row": 5, "col": 5, "revealed": False}]},
            },
            "last_combat": None,
        }
        self.match = Match.objects.create(
            game=Match.Game.STRATEGO, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("stratego-match", args=[self.match.pk]))
        cell = response.context["board_cells"][5][5]
        self.assertTrue(cell["opponent_present"])
        self.assertIsNone(cell["opponent_rank"])


class NineMensMorrisLogicTests(TestCase):
    def test_initial_state_has_empty_board(self):
        state = nine_mens_morris.initial_state()
        self.assertEqual(state["points"], [None] * 24)
        self.assertIsNone(state["pending_removal"])

    def test_apply_move_placement_decrements_to_place(self):
        state = nine_mens_morris.apply_move(nine_mens_morris.initial_state(), "u1", None, 5)
        self.assertEqual(state["points"][5], "u1")
        self.assertEqual(nine_mens_morris.to_place_count(state, "u1"), 8)

    def test_apply_move_placement_rejects_occupied_point(self):
        state = nine_mens_morris.apply_move(nine_mens_morris.initial_state(), "u1", None, 5)
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(state, "u2", None, 5)

    def test_apply_move_rejects_from_point_while_still_placing(self):
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(nine_mens_morris.initial_state(), "u1", 0, 5)

    def test_apply_move_does_not_mutate_original_state(self):
        original = nine_mens_morris.initial_state()
        nine_mens_morris.apply_move(original, "u1", None, 5)
        self.assertEqual(original["points"], [None] * 24)

    def test_apply_move_rejects_placement_once_fully_placed(self):
        state = {"points": [None] * 24, "to_place": {"u1": 0}, "pending_removal": None}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(state, "u1", None, 5)

    def test_slide_requires_adjacency_with_more_than_three_pieces(self):
        points = [None] * 24
        points[0], points[10], points[20], points[15] = "u1", "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(state, "u1", 0, 3)

    def test_slide_to_adjacent_point_succeeds(self):
        points = [None] * 24
        points[0], points[10], points[20], points[15] = "u1", "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        new_state = nine_mens_morris.apply_move(state, "u1", 0, 1)
        self.assertIsNone(new_state["points"][0])
        self.assertEqual(new_state["points"][1], "u1")

    def test_flying_allows_non_adjacent_destination_at_three_pieces(self):
        points = [None] * 24
        points[0], points[10], points[20] = "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        new_state = nine_mens_morris.apply_move(state, "u1", 0, 15)
        self.assertEqual(new_state["points"][15], "u1")

    def test_slide_rejects_occupied_destination(self):
        points = [None] * 24
        points[0], points[1], points[10], points[15] = "u1", "u2", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(state, "u1", 0, 1)

    def test_slide_rejects_moving_someone_elses_piece(self):
        points = [None] * 24
        points[0], points[10], points[20], points[15] = "u2", "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_move(state, "u1", 0, 1)

    def test_forming_a_mill_sets_pending_removal(self):
        points = [None] * 24
        points[0], points[2], points[9], points[15] = "u1", "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        new_state = nine_mens_morris.apply_move(state, "u1", 9, 1)
        self.assertEqual(new_state["pending_removal"], "u1")

    def test_no_mill_leaves_pending_removal_none(self):
        points = [None] * 24
        points[0], points[10], points[20], points[15] = "u1", "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        new_state = nine_mens_morris.apply_move(state, "u1", 0, 1)
        self.assertIsNone(new_state["pending_removal"])

    def test_removable_points_excludes_mill_pieces_unless_all_protected(self):
        points = [None] * 24
        points[0], points[1], points[2], points[5] = "u2", "u2", "u2", "u2"
        state = {"points": points, "to_place": {}, "pending_removal": "u1"}
        self.assertEqual(nine_mens_morris.removable_points(state, "u2"), {5})

    def test_removable_points_allows_all_when_every_piece_is_protected(self):
        points = [None] * 24
        points[0], points[1], points[2] = "u2", "u2", "u2"
        state = {"points": points, "to_place": {}, "pending_removal": "u1"}
        self.assertEqual(nine_mens_morris.removable_points(state, "u2"), {0, 1, 2})

    def test_apply_removal_rejects_when_not_pending(self):
        points = [None] * 24
        points[5] = "u2"
        state = {"points": points, "to_place": {}, "pending_removal": None}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_removal(state, "u1", "u2", 5)

    def test_apply_removal_rejects_removing_own_piece(self):
        points = [None] * 24
        points[5] = "u1"
        state = {"points": points, "to_place": {}, "pending_removal": "u1"}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_removal(state, "u1", "u2", 5)

    def test_apply_removal_rejects_protected_piece(self):
        points = [None] * 24
        points[0], points[1], points[2], points[5] = "u2", "u2", "u2", "u2"
        state = {"points": points, "to_place": {}, "pending_removal": "u1"}
        with self.assertRaises(InvalidMove):
            nine_mens_morris.apply_removal(state, "u1", "u2", 0)

    def test_apply_removal_clears_pending_removal_and_removes_piece(self):
        points = [None] * 24
        points[0], points[1], points[2], points[5] = "u2", "u2", "u2", "u2"
        state = {"points": points, "to_place": {}, "pending_removal": "u1"}
        new_state = nine_mens_morris.apply_removal(state, "u1", "u2", 5)
        self.assertIsNone(new_state["points"][5])
        self.assertIsNone(new_state["pending_removal"])

    def test_is_defeated_by_piece_count(self):
        points = [None] * 24
        points[0], points[1] = "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        self.assertTrue(nine_mens_morris.is_defeated_by_piece_count(state, "u1"))

    def test_not_defeated_while_still_placing(self):
        points = [None] * 24
        points[0], points[1] = "u1", "u1"
        state = {"points": points, "to_place": {"u1": 7}, "pending_removal": None}
        self.assertFalse(nine_mens_morris.is_defeated_by_piece_count(state, "u1"))

    def test_has_legal_move_false_when_completely_blocked(self):
        points = [None] * 24
        points[0], points[7], points[1] = "u1", "u2", "u2"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        self.assertFalse(nine_mens_morris.has_legal_move(state, "u1"))

    def test_has_legal_move_true_when_flying_and_board_not_full(self):
        points = [None] * 24
        points[0], points[10], points[20] = "u1", "u1", "u1"
        state = {"points": points, "to_place": {"u1": 0}, "pending_removal": None}
        self.assertTrue(nine_mens_morris.has_legal_move(state, "u1"))

    def test_is_game_over_true_when_opponent_has_no_legal_move(self):
        points = [None] * 24
        points[0], points[7], points[1] = "u2", "u1", "u1"
        state = {"points": points, "to_place": {"u2": 0}, "pending_removal": None}
        self.assertTrue(nine_mens_morris.is_game_over(state, "u2"))


class NineMensMorrisMatchTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_challenge_creates_active_match_with_player1_first(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("morris-challenge", args=["bob"]))
        match = Match.objects.get()
        self.assertRedirects(response, reverse("morris-match", args=[match.pk]))
        self.assertEqual(match.game, Match.Game.NINE_MENS_MORRIS)
        self.assertEqual(match.turn, self.alice)
        self.assertEqual(match.status, Match.Status.ACTIVE)

    def test_cannot_challenge_self(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("morris-challenge", args=["alice"]))
        self.assertEqual(Match.objects.count(), 0)

    def test_non_participant_cannot_view_match(self):
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob,
            state=nine_mens_morris.initial_state(), turn=self.alice,
        )
        carol = make_user("carol")
        self.client.force_login(carol)
        response = self.client.get(reverse("morris-match", args=[self.match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_placement_switches_turn_to_opponent(self):
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob,
            state=nine_mens_morris.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("morris-move", args=[self.match.pk]), {"to_point": 0})
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["points"][0], str(self.alice.id))
        self.assertEqual(self.match.turn, self.bob)

    def test_move_by_wrong_player_is_ignored(self):
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob,
            state=nine_mens_morris.initial_state(), turn=self.alice,
        )
        self.client.force_login(self.bob)
        self.client.post(reverse("morris-move", args=[self.match.pk]), {"to_point": 0})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.state["points"][0])
        self.assertEqual(self.match.turn, self.alice)

    def test_forming_a_mill_keeps_turn_with_mover_pending_removal(self):
        points = [None] * 24
        points[0] = str(self.alice.id)
        points[2] = str(self.alice.id)
        points[9] = str(self.alice.id)
        points[15] = str(self.alice.id)
        points[20] = str(self.bob.id)
        state = {
            "points": points,
            "to_place": {str(self.alice.id): 0, str(self.bob.id): 0},
            "pending_removal": None,
        }
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("morris-move", args=[self.match.pk]), {"from_point": 9, "to_point": 1})
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["pending_removal"], str(self.alice.id))
        self.assertEqual(self.match.turn, self.alice)
        self.assertEqual(self.match.status, Match.Status.ACTIVE)

    def test_removal_after_mill_switches_turn(self):
        # Bob's 20/21/22 form a mill (all protected) plus one unprotected
        # piece at 10 - removing the unprotected one leaves bob with 3
        # pieces, so the game continues and the turn just switches.
        points = [None] * 24
        points[0] = str(self.alice.id)
        points[1] = str(self.alice.id)
        points[2] = str(self.alice.id)
        points[20] = str(self.bob.id)
        points[21] = str(self.bob.id)
        points[22] = str(self.bob.id)
        points[10] = str(self.bob.id)
        state = {
            "points": points,
            "to_place": {str(self.alice.id): 0, str(self.bob.id): 0},
            "pending_removal": str(self.alice.id),
        }
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("morris-move", args=[self.match.pk]), {"remove_point": 10})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.state["points"][10])
        self.assertIsNone(self.match.state["pending_removal"])
        self.assertEqual(self.match.status, Match.Status.ACTIVE)
        self.assertEqual(self.match.turn, self.bob)

    def test_invalid_removal_of_protected_piece_shows_an_error(self):
        points = [None] * 24
        points[0] = str(self.alice.id)
        points[1] = str(self.alice.id)
        points[2] = str(self.alice.id)
        points[20] = str(self.bob.id)
        points[21] = str(self.bob.id)
        points[22] = str(self.bob.id)
        points[10] = str(self.bob.id)
        state = {
            "points": points,
            "to_place": {str(self.alice.id): 0, str(self.bob.id): 0},
            "pending_removal": str(self.alice.id),
        }
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("morris-move", args=[self.match.pk]), {"remove_point": 20}, follow=True
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.state["pending_removal"], str(self.alice.id))
        self.assertContains(response, "protected by a mill")

    def test_removal_bringing_opponent_below_three_wins_the_match(self):
        # Bob's only 3 pieces happen to form a mill - since all of his
        # pieces are protected, the "all-protected" exception makes any of
        # them removable anyway, and removing one drops him below 3.
        points = [None] * 24
        points[0] = str(self.alice.id)
        points[1] = str(self.alice.id)
        points[2] = str(self.alice.id)
        points[20] = str(self.bob.id)
        points[21] = str(self.bob.id)
        points[22] = str(self.bob.id)
        state = {
            "points": points,
            "to_place": {str(self.alice.id): 0, str(self.bob.id): 0},
            "pending_removal": str(self.alice.id),
        }
        self.match = Match.objects.create(
            game=Match.Game.NINE_MENS_MORRIS, player1=self.alice, player2=self.bob, state=state, turn=self.alice,
        )
        self.client.force_login(self.alice)
        self.client.post(reverse("morris-move", args=[self.match.pk]), {"remove_point": 20})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(self.match.winner, self.alice)
        self.assertIsNone(self.match.turn)


class SnakeResultTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def post_json(self, payload):
        return self.client.post(reverse("snake-finish"), data=payload, content_type="application/json")

    def test_valid_score_is_recorded(self):
        response = self.post_json({"score": 12})
        self.assertEqual(response.status_code, 200)
        result = SinglePlayerResult.objects.get()
        self.assertEqual(result.player, self.alice)
        self.assertEqual(result.game, SinglePlayerResult.Game.SNAKE)
        self.assertEqual(result.score, 12)
        self.assertFalse(result.won)

    def test_negative_score_is_rejected(self):
        response = self.post_json({"score": -1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_out_of_range_score_is_rejected(self):
        response = self.post_json({"score": 401})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_malformed_payload_is_rejected(self):
        response = self.client.post(reverse("snake-finish"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_submit_score(self):
        self.client.logout()
        response = self.post_json({"score": 10})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)


class DoodleJumpResultTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def post_json(self, payload):
        return self.client.post(reverse("doodle-finish"), data=payload, content_type="application/json")

    def test_valid_score_is_recorded(self):
        response = self.post_json({"score": 340})
        self.assertEqual(response.status_code, 200)
        result = SinglePlayerResult.objects.get()
        self.assertEqual(result.player, self.alice)
        self.assertEqual(result.game, SinglePlayerResult.Game.DOODLE_JUMP)
        self.assertEqual(result.score, 340)
        self.assertFalse(result.won)

    def test_negative_score_is_rejected(self):
        response = self.post_json({"score": -1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_out_of_range_score_is_rejected(self):
        response = self.post_json({"score": 2_000_000})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_malformed_payload_is_rejected(self):
        response = self.client.post(reverse("doodle-finish"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_submit_score(self):
        self.client.logout()
        response = self.post_json({"score": 100})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)


class FlappyBirdResultTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.client.force_login(self.alice)

    def post_json(self, payload):
        return self.client.post(reverse("flappy-finish"), data=payload, content_type="application/json")

    def test_valid_score_is_recorded(self):
        response = self.post_json({"score": 12})
        self.assertEqual(response.status_code, 200)
        result = SinglePlayerResult.objects.get()
        self.assertEqual(result.player, self.alice)
        self.assertEqual(result.game, SinglePlayerResult.Game.FLAPPY_BIRD)
        self.assertEqual(result.score, 12)
        self.assertFalse(result.won)

    def test_negative_score_is_rejected(self):
        response = self.post_json({"score": -1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_out_of_range_score_is_rejected(self):
        response = self.post_json({"score": 50_000})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)

    def test_malformed_payload_is_rejected(self):
        response = self.client.post(reverse("flappy-finish"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_anonymous_cannot_submit_score(self):
        self.client.logout()
        response = self.post_json({"score": 5})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SinglePlayerResult.objects.count(), 0)
