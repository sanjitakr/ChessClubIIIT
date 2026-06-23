"""
FIDE-style Swiss pairing engine for multi-round tournaments.
Pairs players within score groups, avoids rematches, balances colors.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import User


def _player_rating(user: User) -> int:
    profile = getattr(user, "profile", None)
    return getattr(profile, "rating", 600) if profile else 600


def _played_pairs(tournament) -> set[frozenset[int]]:
    from .models import TournamentMatch

    pairs = set()
    for m in TournamentMatch.objects.filter(tournament=tournament).exclude(result="PENDING"):
        pairs.add(frozenset({m.player1_id, m.player2_id}))
    return pairs


def _color_history(tournament, user_id: int) -> list[str]:
    from .models import TournamentMatch

    colors: list[str] = []
    for m in TournamentMatch.objects.filter(tournament=tournament).order_by("round_number"):
        if user_id not in (m.player1_id, m.player2_id):
            continue
        if m.white_player_id == user_id:
            colors.append("W")
        elif m.white_player_id:
            colors.append("B")
    return colors


def _preferred_color(tournament, user_id: int) -> str | None:
    history = _color_history(tournament, user_id)
    if not history:
        return None
    w = history.count("W")
    b = history.count("B")
    if w > b:
        return "B"
    if b > w:
        return "W"
    return "W" if history[-1] == "B" else "B"


def generate_swiss_pairings(tournament, players: list, round_number: int) -> list[tuple]:
    """
    Return list of (white_user, black_user) pairings for the given round.
    Odd player count yields one bye (None as black).
    """
    from .standings import compute_standings

    if len(players) < 2:
        return []

    standings = compute_standings(tournament)
    score_map = {s["player"].id: s["points"] for s in standings}
    played = _played_pairs(tournament)

    sorted_players = sorted(
        players,
        key=lambda u: (-score_map.get(u.id, 0.0), -_player_rating(u)),
    )

    paired: set[int] = set()
    pairings: list[tuple] = []

    score_groups: dict[float, list] = defaultdict(list)
    for p in sorted_players:
        score_groups[score_map.get(p.id, 0.0)].append(p)

    for score in sorted(score_groups.keys(), reverse=True):
        group = [p for p in score_groups[score] if p.id not in paired]
        group.sort(key=lambda u: -_player_rating(u))

        while len(group) >= 2:
            top = group.pop(0)
            if top.id in paired:
                continue

            opponent = None
            for i, candidate in enumerate(group):
                key = frozenset({top.id, candidate.id})
                if key not in played:
                    opponent = group.pop(i)
                    break

            if opponent is None and group:
                opponent = group.pop(0)

            if opponent is None:
                break

            white, black = _assign_colors(tournament, top, opponent)
            pairings.append((white, black))
            paired.add(top.id)
            paired.add(opponent.id)

        if len(group) == 1 and group[0].id not in paired:
            pairings.append((group[0], None))
            paired.add(group[0].id)

    return pairings


def _assign_colors(tournament, p1, p2):
    pref1 = _preferred_color(tournament, p1.id)
    pref2 = _preferred_color(tournament, p2.id)

    if pref1 == "W" and pref2 != "W":
        return p1, p2
    if pref2 == "W" and pref1 != "W":
        return p2, p1
    if pref1 == "B":
        return p2, p1
    if pref2 == "B":
        return p1, p2
    if _player_rating(p1) >= _player_rating(p2):
        return p1, p2
    return p2, p1


def recommended_rounds(player_count: int) -> int:
    if player_count < 2:
        return 0
    import math

    return max(3, math.ceil(math.log2(player_count)))
