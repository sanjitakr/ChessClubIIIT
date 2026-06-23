"""
Tournament standings with FIDE-style tiebreaks (Buchholz, Sonneborn-Berger).
"""

from __future__ import annotations

from collections import defaultdict


def _match_points(match, player_id: int) -> float:
    if match.result == "PENDING":
        return None
    if match.result == "DRAW":
        return 0.5
    if match.result == "PLAYER1":
        return 1.0 if match.player1_id == player_id else 0.0
    if match.result == "PLAYER2":
        return 1.0 if match.player2_id == player_id else 0.0
    return 0.0


def compute_standings(tournament) -> list[dict]:
    from .models import TournamentMatch, TournamentRegistration

    players = [
        r.user
        for r in tournament.registrations.filter(
            is_waitlisted=False,
            user__isnull=False,
        ).select_related("user", "user__profile")
    ]
    if not players:
        return []

    matches = list(
        TournamentMatch.objects.filter(tournament=tournament).select_related("player1", "player2")
    )

    stats: dict[int, dict] = {}
    for p in players:
        stats[p.id] = {
            "player": p,
            "points": 0.0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "games": 0,
            "opponents": [],
        }

    for m in matches:
        if m.result == "PENDING":
            continue
        for pid in (m.player1_id, m.player2_id):
            if pid not in stats:
                continue
            pts = _match_points(m, pid)
            if pts is None:
                continue
            stats[pid]["points"] += pts
            stats[pid]["games"] += 1
            opp_id = m.player2_id if pid == m.player1_id else m.player1_id
            stats[pid]["opponents"].append(opp_id)
            if pts == 1.0:
                stats[pid]["wins"] += 1
            elif pts == 0.5:
                stats[pid]["draws"] += 1
            else:
                stats[pid]["losses"] += 1

    for pid, s in stats.items():
        s["buchholz"] = sum(stats[oid]["points"] for oid in s["opponents"] if oid in stats)
        sb = 0.0
        for oid in s["opponents"]:
            if oid not in stats:
                continue
            opp_pts = stats[oid]["points"]
            for m in matches:
                if m.result == "PENDING":
                    continue
                if {m.player1_id, m.player2_id} != {pid, oid}:
                    continue
                my_pts = _match_points(m, pid)
                if my_pts == 1.0:
                    sb += opp_pts
                elif my_pts == 0.5:
                    sb += opp_pts * 0.5
        s["sonneborn_berger"] = sb

    profile_rating = lambda u: getattr(getattr(u, "profile", None), "rating", 600)

    ranked = sorted(
        stats.values(),
        key=lambda s: (
            -s["points"],
            -s["buchholz"],
            -s["sonneborn_berger"],
            -profile_rating(s["player"]),
        ),
    )

    for i, row in enumerate(ranked, start=1):
        row["rank"] = i

    return ranked


def sync_tournament_results(tournament) -> None:
    """Persist computed standings into TournamentResult records."""
    from .models import TournamentResult

    standings = compute_standings(tournament)
    for row in standings:
        TournamentResult.objects.update_or_create(
            tournament=tournament,
            player=row["player"],
            defaults={
                "position": row["rank"],
                "points": row["points"],
                "wins": row["wins"],
                "draws": row["draws"],
                "losses": row["losses"],
            },
        )
