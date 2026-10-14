from django.db import models
from django.utils import timezone
from accounts.models import User

class Tournament(models.Model):
    name = models.CharField(max_length=200)
    PAIRING_TYPE_CHOICES = [
        ('RANDOM', 'Random (Tournament)'),
        ('ROUND_ROBIN', 'Round Robin'),
        ('SWISS', 'Swiss System'),
        ('CUSTOM_TOURNAMENT', 'Custom Tournament'),
        ('CUSTOM_ROUND_ROBIN', 'Custom Round Robin'),
    ]
    MODE_CHOICES = [
        ('ONLINE', 'Online'),
        ('OFFLINE', 'Offline (OTB)'),
    ]
    STATUS_CHOICES = [
        ('UPCOMING', 'Upcoming'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
    ]

    pairing_type = models.CharField(max_length=30, choices=PAIRING_TYPE_CHOICES, default='RANDOM')
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='ONLINE')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='UPCOMING')
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    current_round = models.PositiveIntegerField(default=0)
    total_rounds = models.PositiveIntegerField(default=0, help_text="0 = auto-calculated from player count")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    base_minutes = models.PositiveIntegerField(default=10)
    increment_seconds = models.PositiveIntegerField(default=0)
    venue = models.CharField(max_length=200, blank=True, default="IIIT Hyderabad Campus")
    
    max_players = models.PositiveIntegerField(default=0, help_text="0 for unlimited. If reached, goes to waitlist.")
    registration_start_time = models.DateTimeField(default=timezone.now)
    registration_end_time = models.DateTimeField(blank=True, null=True)
    registration_extended_until = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name
    
    def to_dict(self, include_matches=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "pairing_type": self.pairing_type,
            "mode": self.mode,
            "status": self.status,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "base_minutes": self.base_minutes,
            "increment_seconds": self.increment_seconds,
            "venue": self.venue,
        }
        if include_matches:
            data["matches"] = [match.to_dict() for match in self.matches.all()]
        return data
    
    class Meta:
        ordering = ['-start_date']
        
    @property
    def time_control_display(self):
        return f"{self.base_minutes}+{self.increment_seconds}"

    @property
    def is_online(self):
        return self.mode == "ONLINE"

    @property
    def is_offline(self):
        return self.mode == "OFFLINE"

    def registration_deadline(self):
        """Effective registration close time (includes one admin extension)."""
        if not self.registration_end_time:
            return None
        deadline = self.registration_end_time
        if self.registration_extended_until:
            deadline = max(deadline, self.registration_extended_until)
        return deadline

    def registration_open(self):
        current = timezone.now()
        if self.registration_start_time and current < self.registration_start_time:
            return False
        deadline = self.registration_deadline()
        if deadline and current > deadline:
            return False
        return True

    def registered_count(self):
        return self.registrations.filter(is_waitlisted=False).count()

    def waitlist_count(self):
        return self.registrations.filter(is_waitlisted=True).count()

    def can_extend_registration(self):
        if not self.registration_end_time:
            return False
        from datetime import timedelta
        max_deadline = self.registration_end_time + timedelta(minutes=15)
        current_deadline = self.registration_deadline()
        return current_deadline < max_deadline

    def max_extension_deadline(self):
        from datetime import timedelta
        if not self.registration_end_time:
            return None
        return self.registration_end_time + timedelta(minutes=15)


class TournamentRound(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="rounds")
    round_number = models.PositiveIntegerField()
    is_complete = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tournament", "round_number")
        ordering = ["round_number"]

    def __str__(self):
        return f"{self.tournament.name} — Round {self.round_number}"


class TournamentMatch(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name='matches'
    )

    player1 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='matches_as_player1'
    )
    player2 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='matches_as_player2'
    )
    match_created = models.BooleanField(default=False)
    result = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('DRAW', 'Draw'),
            ('PLAYER1', 'Player 1 Won'),
            ('PLAYER2', 'Player 2 Won'),
        ],
        default='PENDING'
    )

    scheduled_at = models.DateTimeField(default=timezone.now)
    round_number = models.PositiveIntegerField(default=1)
    board_number = models.PositiveIntegerField(default=0)
    white_player = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tournament_matches_as_white",
    )
    tournament_round = models.ForeignKey(
        TournamentRound, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pairings",
    )

    completed_at = models.DateTimeField(blank=True, null=True)
    live_match = models.OneToOneField(
        "match.Match",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tournament_pairing"
    )

    def __str__(self):
        return f"{self.tournament.name}: {self.player1.username} vs {self.player2.username}"

    def to_dict(self):
        return {
            "id": self.id,
            "tournament_id": self.tournament.id,
            "tournament_name": self.tournament.name,
            "player1": self.player1.to_dict(),
            "player2": self.player2.to_dict(),
            "scheduled_at": self.scheduled_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "live_match_id": self.live_match.id if self.live_match else None,
            "result": self.result,
            "match_created": self.match_created,
            "round_number": self.round_number,
            "board_number": self.board_number,
            "mode": self.tournament.mode,
            "fen": getattr(self.live_match, 'current_fen', None),
        }

    @property
    def winner(self):
        if self.result == "PLAYER1":
            return self.player1
        if self.result == "PLAYER2":
            return self.player2
        return None
    
    class Meta:
        ordering = ['round_number', 'board_number', '-scheduled_at']
        constraints = [
            models.UniqueConstraint(
                fields=['tournament', 'round_number', 'player1', 'player2'],
                name='unique_pair_per_round'
            )
        ]

class TournamentResult(models.Model):
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="results"
    )
    player = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tournament_results"
    )
    position = models.IntegerField(blank=True, null=True)
    points = models.FloatField(default=0)
    wins = models.IntegerField(default=0)
    draws = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.player.username} - {self.tournament.name} ({self.position or 'N/A'})"

    def badge_class(self):
        if self.position == 1:
            return "badge-success"
        elif self.position == 2:
            return "badge-warning"
        elif self.position == 3:
            return "badge-warning"
        else:
            return "badge-secondary"

    def result_text(self):
        if self.position:
            if self.position == 1:
                return "1st Place"
            elif self.position == 2:
                return "2nd Place"
            elif self.position == 3:
                return "3rd Place"
            else:
                return f"{self.position}th Place"
        return "Participant"
    
class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tournament_registrations", null=True, blank=True)
    is_guest = models.BooleanField(default=False)
    guest_name = models.CharField(max_length=150, blank=True, null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    is_waitlisted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tournament', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_user_registration_per_tournament'
            )
        ]

    def __str__(self):
        name = self.guest_name if self.is_guest else self.user.username
        return f"{name} in {self.tournament.name}"


class AuditLog(models.Model):
    ROLE_ADD = 1
    ROLE_REMOVE = 2
    STAFF_DISABLE = 3
    TOURNAMENT_END = 4
    RESULT_RECORD = 5
    RESULT_CORRECT = 6
    TIME_CONTROL = 7
    ACTION_CHOICES = [
        (ROLE_ADD, "Role Added"),
        (ROLE_REMOVE, "Role Removed"),
        (STAFF_DISABLE, "Staff Disabled"),
        (TOURNAMENT_END, "Tournament Ended"),
        (RESULT_RECORD, "Result Recorded"),
        (RESULT_CORRECT, "Result Corrected"),
        (TIME_CONTROL, "Time Control Changed"),
    ]

    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_actions")
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_targets")
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs")
    match = models.ForeignKey(TournamentMatch, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs")
    action = models.PositiveSmallIntegerField(choices=ACTION_CHOICES)
    meta = models.CharField(max_length=96, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["-id"], name="auditlog_id_desc_idx"),
            models.Index(fields=["tournament", "-id"], name="auditlog_tourn_id_idx"),
        ]
