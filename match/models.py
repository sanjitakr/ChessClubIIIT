from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

class Match(models.Model):
    STATUS_CHOICES = [
        ('WAIT', 'Waiting'),
        ('LIVE', 'Live'),
        ('END', 'Ended')
    ]
    
    RESULT_CHOICES = [
        ('1-0', 'White Wins'),
        ('0-1', 'Black Wins'),
        ('1/2-1/2', 'Draw'),
        ('*', 'Ongoing')
    ]
    

    player_white = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matches_white',
        null = True,
        blank=True
    )
    player_black = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matches_black',
        null = True,
        blank = True
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='WAIT')
    current_fen = models.TextField(default='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    move_history = models.JSONField(default=list)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default='*')
    
    
    white_connected = models.BooleanField(default=False)
    black_connected = models.BooleanField(default=False)
    pgn = models.TextField(blank=True, default="")
    is_rated = models.BooleanField(default=True)
    ratings_applied = models.BooleanField(default=False)
    analysis_json = models.JSONField(default=dict, blank=True)
    white_time_ms = models.PositiveIntegerField(default=600000)
    black_time_ms = models.PositiveIntegerField(default=600000)
    increment_ms = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        white_name = self.player_white.username if self.player_white else "Waiting"
        black_name = self.player_black.username if self.player_black else "Waiting"
        return f"{white_name} vs {black_name}"
    
    def add_move(self, move_san, move_from, move_to, fen, moving_color=None):
        now = timezone.now()
        move_data = {
            'san': move_san,
            'from': move_from,
            'to': move_to,
            'fen': fen,
            'ts': now.isoformat(),
        }
        if not isinstance(self.move_history, list):
            self.move_history = []
        self.move_history.append(move_data)
        self.current_fen = fen
        if moving_color:
            self._apply_clock_for_move(moving_color, now=now)
        self.save()

    def _clock_reference_time(self):
        if self.move_history and len(self.move_history) > 1:
            prev_ts = self.move_history[-2].get('ts')
            if prev_ts:
                parsed = parse_datetime(prev_ts)
                if parsed:
                    return parsed
        return self.start_time

    def _apply_clock_for_move(self, moving_color, now=None):
        now = now or timezone.now()
        elapsed_ms = int((now - self._clock_reference_time()).total_seconds() * 1000)
        if moving_color == 'white':
            self.white_time_ms = max(0, self.white_time_ms - elapsed_ms + self.increment_ms)
        elif moving_color == 'black':
            self.black_time_ms = max(0, self.black_time_ms - elapsed_ms + self.increment_ms)

    def effective_clock_state(self, now=None):
        """Return clocks with the active side's elapsed time applied."""
        now = now or timezone.now()
        white_ms = self.white_time_ms
        black_ms = self.black_time_ms

        if self.status == 'LIVE' and self.player_white_id and self.player_black_id:
            ref = self._clock_reference_time()
            elapsed_ms = max(0, int((now - ref).total_seconds() * 1000))
            if self.get_current_turn() == 'white':
                white_ms = max(0, white_ms - elapsed_ms)
            else:
                black_ms = max(0, black_ms - elapsed_ms)

        return {
            'white_time_ms': white_ms,
            'black_time_ms': black_ms,
            'timed_out_color': (
                'white' if white_ms <= 0 else
                'black' if black_ms <= 0 else
                None
            ),
        }
    
    def get_current_turn(self):
        
        parts = self.current_fen.split()
        return 'white' if parts[1] == 'w' else 'black'
    
    def can_join(self, user):
        if self.scheduled_start and timezone.now() < self.scheduled_start:
            return False
        if self.status != 'WAIT':
            return False
        if not self.player_white or not self.player_black:
            return True
        return False
    
    def join_as_player(self, user):
        joined = False
        if not self.player_white:
            self.player_white = user
            joined = True
        elif not self.player_black:
            self.player_black = user
            joined = True

        if joined and self.player_white and self.player_black:
            self.status = 'LIVE'  
            self.start_time = timezone.now()
        self.save()
        return self.get_player_color(user)
    
    def get_player_color(self, user):
        if self.player_white == user:
            return 'white'
        elif self.player_black == user:
            return 'black'
        return None


class ChallengeRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('DECLINED', 'Declined'),
        ('CANCELLED', 'Cancelled'),
    ]

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenges_sent',
    )
    challenged = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenges_received',
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    is_rated = models.BooleanField(default=True)
    base_minutes = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    match = models.ForeignKey(
        'Match',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='challenge',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.challenger.username} → {self.challenged.username} ({self.status})"
