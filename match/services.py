"""
Match lifecycle services: Elo rating updates, tournament sync, PGN export.
"""

from __future__ import annotations

import chess
import chess.pgn
from django.utils import timezone
from io import StringIO


def _elo_expected(ra: int, rb: int) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400))


def _elo_change(rating: int, opponent_rating: int, score: float, k: int = 32) -> int:
    expected = _elo_expected(rating, opponent_rating)
    return round(k * (score - expected))


def count_rated_games(user, exclude_match=None) -> int:
    from .models import Match
    from django.db.models import Q

    qs = Match.objects.filter(
        status="END",
        is_rated=True,
    ).filter(Q(player_white=user) | Q(player_black=user))
    if exclude_match:
        qs = qs.exclude(pk=exclude_match.pk)
    return qs.count()


def get_fide_k_factor(rating: int, rated_games: int) -> int:
    """
    FIDE + club defaults:
    K=40 — fewer than 30 rated games and rating under 2300 (FIDE provisional)
    K=32 — rating under 2400 (standard; chess.com-style)
    K=24 — rating 2400+ (established high-rated players)
    """
    if rated_games < 30 and rating < 2300:
        return 40
    if rating < 2400:
        return 32
    return 24


def get_player_k_factor(user) -> int:
    profile = user.profile
    games = count_rated_games(user)
    return get_fide_k_factor(profile.rating, games)


def _result_to_scores(result: str) -> tuple[float, float]:
    if result == "1-0":
        return 1.0, 0.0
    if result == "0-1":
        return 0.0, 1.0
    if result == "1/2-1/2":
        return 0.5, 0.5
    return 0.0, 0.0


def generate_pgn(match) -> str:
    game = chess.pgn.Game()
    game.headers["Event"] = "IIIT Chess Club"
    game.headers["Site"] = "IIIT Hyderabad"
    game.headers["Date"] = match.start_time.strftime("%Y.%m.%d") if match.start_time else "????.??.??"
    game.headers["White"] = match.player_white.username if match.player_white else "?"
    game.headers["Black"] = match.player_black.username if match.player_black else "?"
    game.headers["Result"] = match.result if match.result != "*" else "*"

    board = chess.Board()
    node = game
    for move_data in match.move_history or []:
        uci = move_data.get("san") or move_data.get("uci")
        if not uci:
            from_sq = move_data.get("from", "")
            to_sq = move_data.get("to", "")
            if from_sq and to_sq:
                uci = from_sq + to_sq
        if uci:
            try:
                move = chess.Move.from_uci(uci) if len(uci) >= 4 else board.parse_san(uci)
                if move in board.legal_moves:
                    node = node.add_variation(move)
                    board.push(move)
            except (ValueError, chess.InvalidMoveError):
                continue

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def update_ratings(match, k_factor: int | None = None) -> dict | None:
    if match.result in ("*", "") or not match.player_white or not match.player_black:
        return None
    if not getattr(match, "is_rated", True):
        return None
    if getattr(match, "ratings_applied", False):
        return None

    white = match.player_white
    black = match.player_black
    w_profile = white.profile
    b_profile = black.profile

    w_score, b_score = _result_to_scores(match.result)
    w_k = get_fide_k_factor(w_profile.rating, count_rated_games(white, match)) if k_factor is None else k_factor
    b_k = get_fide_k_factor(b_profile.rating, count_rated_games(black, match)) if k_factor is None else k_factor
    w_delta = _elo_change(w_profile.rating, b_profile.rating, w_score, w_k)
    b_delta = _elo_change(b_profile.rating, w_profile.rating, b_score, b_k)

    w_profile.last_rating = w_profile.rating
    b_profile.last_rating = b_profile.rating
    w_profile.rating = max(100, w_profile.rating + w_delta)
    b_profile.rating = max(100, b_profile.rating + b_delta)
    w_profile.save(update_fields=["rating", "last_rating"])
    b_profile.save(update_fields=["rating", "last_rating"])

    from .models import Match

    Match.objects.filter(pk=match.pk).update(ratings_applied=True)

    return {
        "white_delta": w_delta,
        "black_delta": b_delta,
        "white_rating": w_profile.rating,
        "black_rating": b_profile.rating,
        "white_k": w_k,
        "black_k": b_k,
    }


def sync_tournament_match(match) -> None:
    """Propagate online match result to linked TournamentMatch."""
    pairing = getattr(match, "tournament_pairing", None)
    if pairing is None:
        try:
            from tournaments.models import TournamentMatch

            pairing = TournamentMatch.objects.filter(live_match=match).first()
        except Exception:
            return

    if pairing is None or match.result == "*":
        return

    if match.result == "1/2-1/2":
        pairing.result = "DRAW"
    elif match.player_white and match.result == "1-0":
        pairing.result = "PLAYER1" if pairing.player1_id == match.player_white_id else "PLAYER2"
    elif match.player_black and match.result == "0-1":
        pairing.result = "PLAYER2" if pairing.player2_id == match.player_black_id else "PLAYER1"
    else:
        return

    pairing.completed_at = timezone.now()
    pairing.save(update_fields=["result", "completed_at"])

    from tournaments.standings import sync_tournament_results

    sync_tournament_results(pairing.tournament)


def finalize_match(match) -> dict:
    """Complete post-game processing: PGN, ratings, tournament sync."""
    from .models import Match

    match = Match.objects.select_related(
        "player_white__profile", "player_black__profile"
    ).get(pk=match.pk)

    updates = {}
    pgn = generate_pgn(match)
    if pgn and pgn != getattr(match, "pgn", ""):
        Match.objects.filter(pk=match.pk).update(pgn=pgn)
        updates["pgn"] = pgn

    if match.status == "END" and match.result != "*":
        rating_changes = update_ratings(match)
        if rating_changes:
            updates["ratings"] = rating_changes
        sync_tournament_match(match)

    return updates
