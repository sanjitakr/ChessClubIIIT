from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.db.models import Q

class User(AbstractUser):
    
    def __str__(self):
        return f"{self.username}"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "profile": self.profile.to_dict(),
        }
    
    @property
    def initials(self):
        a = ""
        b = ""
        if self.first_name:
            a = self.first_name[0]
        if self.last_name:
            b = self.last_name[0]
        c = a + b
        if c == "":
            c = self.username[:2].upper() if self.username else "NA"
        return str(c).upper()

    @property
    def display_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.username
    
    @property
    def tournaments(self):
        from tournaments.models import Tournament
        return Tournament.objects.filter(
            Q(matches__player1=self) | Q(matches__player2=self)
        ).distinct()
    
    @property
    def matches(self):
        from tournaments.models import TournamentMatch
        return TournamentMatch.objects.filter(Q(player1=self) | Q(player2=self)).select_related("tournament")


class Achievement(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="Lucide icon name (e.g. trophy, flame)", default="trophy")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    rating = models.IntegerField(default=600)
    last_rating = models.IntegerField(default=600)
    rank = models.IntegerField(default=0)
    last_rank = models.IntegerField(default=0)
    bio = models.TextField(max_length=500, blank=True, null=True)
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    chessdotcom = models.CharField(max_length=64, blank=True, null=True)
    lichess = models.CharField(max_length=64, blank=True, null=True)
    achievements = models.ManyToManyField(Achievement, related_name="players", blank=True)
    rating_history = models.JSONField(default=list, blank=True)    
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user.id,
            "rating": self.rating,
            "last_rating": self.last_rating,
            "rank": self.rank,
            "last_rank": self.last_rank,
            "bio": self.bio,
            "avatar_url": self.avatar_url,
            "chessdotcom": self.chessdotcom,
            "lichess": self.lichess,
            "rating_history": self.rating_history,
        }
    
    def save(self, *args, **kwargs):
        from django.utils import timezone
        with transaction.atomic():
            changed = False
            if self.pk:
                old = UserProfile.objects.select_for_update().get(pk=self.pk)
                if old.rating != self.rating:
                    self.last_rating = old.rating
                    changed = True
            else:
                self.last_rating = self.rating
                changed = True

            super().save(*args, **kwargs)
            if changed:
                history = self.rating_history if isinstance(self.rating_history, list) else []
                history.append({'date': str(timezone.now().date()), 'rating': self.rating})
                UserProfile.objects.filter(pk=self.pk).update(rating_history=history)
    
    @property
    def rating_change(self):
        return self.rating - self.last_rating

    @property
    def rank_change(self):
        return self.last_rank - self.rank if self.last_rank > 0 else 0

    @property
    def matches_played(self):
        return self.user.matches.count()
    
    @property
    def win_count(self):
        count = 0
        for m in self.user.matches:
            if m.winner == self.user:
                count += 1
        return count
