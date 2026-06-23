"""
Tournament Pairing Services — refactored to follow SOLID principles.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import User
    from .models import Tournament


class ITournamentPairingStrategy(ABC):
    @abstractmethod
    def generate(self, users: list) -> list[tuple]:
        raise NotImplementedError


class RandomPairingStrategy(ITournamentPairingStrategy):
    def generate(self, users: list) -> list[tuple]:
        players = list(users)
        random.shuffle(players)
        return [(players[i], players[i + 1]) for i in range(0, len(players) - 1, 2)]


class RoundRobinPairingStrategy(ITournamentPairingStrategy):
    def generate(self, users: list) -> list[tuple]:
        players = list(users)
        return [
            (players[i], players[j])
            for i in range(len(players))
            for j in range(i + 1, len(players))
        ]


class RatingOrderedPairingStrategy(ITournamentPairingStrategy):
    """First-round Swiss seeding: pair by FIDE rating (1v2, 3v4)."""

    def generate(self, users: list) -> list[tuple]:
        players = sorted(
            users,
            key=lambda u: getattr(getattr(u, "profile", None), "rating", 0),
            reverse=True,
        )
        pairings = []
        for i in range(0, len(players) - 1, 2):
            white, black = players[i], players[i + 1]
            pairings.append((white, black))
        if len(players) % 2 == 1:
            pairings.append((players[-1], None))
        return pairings


class SwissPairingStrategy(ITournamentPairingStrategy):
    """Delegates to full Swiss engine for multi-round tournaments."""

    def __init__(self, tournament=None, round_number: int = 1):
        self.tournament = tournament
        self.round_number = round_number

    def generate(self, users: list) -> list[tuple]:
        if self.tournament and self.round_number > 1:
            from .swiss import generate_swiss_pairings
            return generate_swiss_pairings(self.tournament, users, self.round_number)
        return RatingOrderedPairingStrategy().generate(users)


_STRATEGY_REGISTRY: dict[str, type[ITournamentPairingStrategy]] = {
    "RANDOM": RandomPairingStrategy,
    "ROUND_ROBIN": RoundRobinPairingStrategy,
    "SWISS": SwissPairingStrategy,
}


class PairingStrategyFactory:
    @staticmethod
    def create(pairing_type: str, tournament=None, round_number: int = 1) -> ITournamentPairingStrategy:
        if pairing_type == "SWISS":
            return SwissPairingStrategy(tournament=tournament, round_number=round_number)
        cls = _STRATEGY_REGISTRY.get(pairing_type)
        if cls is None:
            raise ValueError(
                f"Unknown pairing type '{pairing_type}'. "
                f"Available: {list(_STRATEGY_REGISTRY.keys())}"
            )
        return cls()

    @staticmethod
    def register(type_key: str, cls: type[ITournamentPairingStrategy]) -> None:
        _STRATEGY_REGISTRY[type_key] = cls


def generate_pairings(tournament, users: list, round_number: int = 1) -> list[tuple]:
    pairing_type = getattr(tournament, "pairing_type", "RANDOM")
    if pairing_type.startswith("CUSTOM"):
        return []
    strategy = PairingStrategyFactory.create(pairing_type, tournament=tournament, round_number=round_number)
    return strategy.generate(users)


def create_round_pairings(tournament, round_number: int) -> list:
    """Create TournamentMatch records for a round. Returns created matches."""
    from .models import TournamentMatch, TournamentRound
    from .swiss import recommended_rounds

    existing = list(
        TournamentMatch.objects.filter(
            tournament=tournament,
            round_number=round_number,
        ).order_by("board_number", "id")
    )
    if existing:
        return existing

    users = [
        r.user for r in tournament.registrations.filter(
            is_waitlisted=False, user__isnull=False
        ).select_related("user", "user__profile")
    ]
    if len(users) < 2:
        return []

    if tournament.total_rounds == 0:
        tournament.total_rounds = recommended_rounds(len(users))
        tournament.save(update_fields=["total_rounds"])

    round_obj, _ = TournamentRound.objects.get_or_create(
        tournament=tournament,
        round_number=round_number,
    )

    pairings = generate_pairings(tournament, users, round_number=round_number)
    created = []

    for board_num, pair in enumerate(pairings, start=1):
        if len(pair) == 2:
            p1, p2 = pair
        else:
            continue
        if p2 is None:
            continue

        white = p1
        black = p2
        if tournament.pairing_type == "SWISS" and round_number > 1:
            from .swiss import _assign_colors
            white, black = _assign_colors(tournament, p1, p2)

        match, was_created = TournamentMatch.objects.get_or_create(
            tournament=tournament,
            round_number=round_number,
            player1=white,
            player2=black,
            defaults={
                "white_player": white,
                "board_number": board_num,
                "tournament_round": round_obj,
                "result": "PENDING",
            },
        )
        if was_created:
            created.append(match)

    tournament.current_round = round_number
    if tournament.status == "UPCOMING":
        tournament.status = "ACTIVE"
    tournament.save(update_fields=["current_round", "status"])
    return created


def available_strategies() -> list[str]:
    return list(_STRATEGY_REGISTRY.keys())
