from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tournaments.models import Tournament, TournamentMatch


class TournamentTimeControlTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="manager",
            password="pass",
            is_staff=True,
        )
        self.player1 = User.objects.create_user(username="p1", password="pass")
        self.player2 = User.objects.create_user(username="p2", password="pass")
        self.client.force_login(self.admin)
        self.tournament = Tournament.objects.create(
            name="Rapid Event",
            mode="ONLINE",
            base_minutes=10,
            increment_seconds=0,
        )

    def test_updates_time_control_before_matches_exist(self):
        response = self.client.post(
            reverse("update_time_control", args=[self.tournament.id]),
            {"base_minutes": "15", "increment_seconds": "5"},
        )

        self.assertRedirects(response, reverse("tournament_detail", args=[self.tournament.id]))
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.base_minutes, 15)
        self.assertEqual(self.tournament.increment_seconds, 5)

    def test_existing_matches_require_confirmation(self):
        TournamentMatch.objects.create(
            tournament=self.tournament,
            player1=self.player1,
            player2=self.player2,
            white_player=self.player1,
        )

        response = self.client.post(
            reverse("update_time_control", args=[self.tournament.id]),
            {"base_minutes": "20", "increment_seconds": "10"},
        )

        self.assertRedirects(response, reverse("tournament_detail", args=[self.tournament.id]))
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.base_minutes, 10)
        self.assertEqual(self.tournament.increment_seconds, 0)

    def test_existing_matches_update_after_confirmation(self):
        TournamentMatch.objects.create(
            tournament=self.tournament,
            player1=self.player1,
            player2=self.player2,
            white_player=self.player1,
        )

        response = self.client.post(
            reverse("update_time_control", args=[self.tournament.id]),
            {
                "base_minutes": "20",
                "increment_seconds": "10",
                "confirm_existing_matches": "1",
            },
        )

        self.assertRedirects(response, reverse("tournament_detail", args=[self.tournament.id]))
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.base_minutes, 20)
        self.assertEqual(self.tournament.increment_seconds, 10)
