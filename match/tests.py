from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Match, MatchMove
from .timeouts import enforce_expired_clocks


User = get_user_model()


@override_settings(ALLOWED_HOSTS=['localhost', 'testserver'])
class MatchCoreTests(TestCase):
    def setUp(self):
        self.white = User.objects.create_user(username='white_player')
        self.black = User.objects.create_user(username='black_player')

    def test_join_resets_live_start_time(self):
        match = Match.objects.create(
            player_white=self.white,
            status='WAIT',
            white_time_ms=600000,
            black_time_ms=600000,
        )
        Match.objects.filter(pk=match.pk).update(start_time=timezone.now() - timedelta(minutes=5))
        match.refresh_from_db()

        color = match.join_as_player(self.black)
        clock = match.effective_clock_state()

        self.assertEqual(color, 'black')
        self.assertEqual(match.status, 'LIVE')
        self.assertGreater(match.start_time, timezone.now() - timedelta(seconds=5))
        self.assertGreater(clock['white_time_ms'], 595000)

    def test_add_move_persists_queryable_move_row_and_updates_clock_reference(self):
        match = Match.objects.create(
            player_white=self.white,
            player_black=self.black,
            status='LIVE',
            start_time=timezone.now() - timedelta(seconds=5),
            white_time_ms=600000,
            black_time_ms=600000,
        )

        match.add_move(
            move_san='e4',
            move_from='e2',
            move_to='e4',
            fen='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
            moving_color='white',
            move_uci='e2e4',
        )

        self.assertEqual(MatchMove.objects.filter(match=match).count(), 1)
        move = MatchMove.objects.get(match=match)
        self.assertEqual(move.move_number, 1)
        self.assertEqual(move.san, 'e4')
        self.assertEqual(move.uci, 'e2e4')
        match.refresh_from_db()
        self.assertIsNotNone(match.last_move_at)
        self.assertLess(match.white_time_ms, 600000)

    def test_server_side_timeout_enforcement_ends_expired_game(self):
        match = Match.objects.create(
            player_white=self.white,
            player_black=self.black,
            status='LIVE',
            start_time=timezone.now() - timedelta(seconds=3),
            current_fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
            white_time_ms=1000,
            black_time_ms=600000,
        )

        expired = enforce_expired_clocks(limit=10)
        match.refresh_from_db()

        self.assertEqual(expired, 1)
        self.assertEqual(match.status, 'END')
        self.assertEqual(match.result, '0-1')
        self.assertEqual(match.white_time_ms, 0)

    def test_lobby_api_returns_bounded_payload_shape(self):
        Match.objects.create(player_white=self.white, status='WAIT')
        Match.objects.create(player_white=self.white, player_black=self.black, status='LIVE')

        response = Client(HTTP_HOST='localhost').get('/match/api/lobby/data/')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('counts', data)
        self.assertIn('limits', data)
        self.assertIn('waiting_matches', data)
        self.assertIn('live_matches', data)

    def test_rematch_creates_reversed_live_game_for_original_player(self):
        original = Match.objects.create(
            player_white=self.white,
            player_black=self.black,
            status='END',
            result='1-0',
            white_time_ms=300000,
            black_time_ms=240000,
            increment_ms=2000,
            is_rated=False,
        )
        client = Client(HTTP_HOST='localhost')
        client.force_login(self.white)

        response = client.post(f'/match/api/{original.id}/rematch/')
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        rematch = Match.objects.get(pk=data['match_id'])
        self.assertEqual(rematch.status, 'LIVE')
        self.assertEqual(rematch.player_white, self.black)
        self.assertEqual(rematch.player_black, self.white)
        self.assertEqual(rematch.white_time_ms, original.black_time_ms)
        self.assertEqual(rematch.black_time_ms, original.white_time_ms)
        self.assertEqual(rematch.increment_ms, original.increment_ms)
        self.assertFalse(rematch.is_rated)
