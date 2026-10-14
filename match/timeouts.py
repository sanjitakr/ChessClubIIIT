from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Match


def finish_match_on_time(match: Match, loser: str, now=None) -> bool:
    now = now or timezone.now()
    result = '0-1' if loser == 'white' else '1-0'
    clock = match.effective_clock_state(now=now)
    with transaction.atomic():
        updated = Match.objects.filter(pk=match.pk, status='LIVE').update(
            status='END',
            result=result,
            end_time=now,
            white_time_ms=clock['white_time_ms'],
            black_time_ms=clock['black_time_ms'],
        )
    if not updated:
        return False

    try:
        match.refresh_from_db()
        from .services import finalize_match

        finalize_match(match)
    except Exception:
        pass
    return True


def enforce_expired_clocks(limit: int = 200) -> int:
    now = timezone.now()
    expired = 0
    matches = (
        Match.objects
        .filter(status='LIVE', player_white__isnull=False, player_black__isnull=False)
        .select_related('player_white', 'player_black')
        .order_by('start_time')[:limit]
    )
    for match in matches:
        timed_out = match.effective_clock_state(now=now).get('timed_out_color')
        if timed_out and finish_match_on_time(match, timed_out, now=now):
            expired += 1
    return expired
