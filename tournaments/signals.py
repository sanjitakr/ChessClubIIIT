from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from tournaments.models import TournamentMatch
from match.models import Match


@receiver(post_save, sender=TournamentMatch)
def create_match_when_scheduled(sender, instance, created, **kwargs):
    tournament = instance.tournament
    if tournament.mode != "ONLINE":
        return

    if instance.scheduled_at is None:
        return

    if instance.live_match is not None:
        return

    if instance.result != "PENDING":
        return

    white = instance.white_player or instance.player1
    black = instance.player2

    base_ms = tournament.base_minutes * 60 * 1000
    inc_ms = tournament.increment_seconds * 1000

    live_match = Match.objects.create(
        player_white=white,
        player_black=black,
        scheduled_start=instance.scheduled_at,
        status="WAIT",
        white_time_ms=base_ms,
        black_time_ms=base_ms,
        increment_ms=inc_ms,
        is_rated=True,
    )

    instance.live_match = live_match
    instance.match_created = True
    instance.save(update_fields=["live_match", "match_created"])
