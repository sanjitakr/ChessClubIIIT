from django.contrib import admin
from .models import Match, MatchMove

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'player_white', 'player_black', 'status', 'start_time']
    list_filter = ['status']
    search_fields = ['player_white__username', 'player_black__username']


@admin.register(MatchMove)
class MatchMoveAdmin(admin.ModelAdmin):
    list_display = ['match_id', 'move_number', 'color', 'uci', 'played_at']
    list_filter = ['color']
    search_fields = ['match__player_white__username', 'match__player_black__username', 'uci']
