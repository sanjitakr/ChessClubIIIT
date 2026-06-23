from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Tournament, TournamentMatch, TournamentRegistration,
    TournamentResult, TournamentRound,
)
from .services import create_round_pairings
from .standings import sync_tournament_results


class TournamentRegistrationInline(admin.TabularInline):
    model = TournamentRegistration
    extra = 0
    readonly_fields = ("registered_at",)


class TournamentMatchInline(admin.TabularInline):
    model = TournamentMatch
    extra = 0
    readonly_fields = ("live_match", "match_created", "completed_at")
    fields = (
        "round_number", "board_number", "player1", "player2",
        "white_player", "result", "scheduled_at", "live_match",
    )


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "name", "mode", "pairing_type", "status", "current_round",
        "start_date", "is_active", "registration_count",
    )
    list_filter = ("mode", "pairing_type", "status", "is_active")
    search_fields = ("name",)
    inlines = [TournamentRegistrationInline, TournamentMatchInline]
    actions = ["start_first_round", "sync_standings", "mark_completed"]

    fieldsets = (
        (None, {"fields": ("name", "description", "venue")}),
        ("Format", {"fields": ("mode", "pairing_type", "status", "current_round", "total_rounds")}),
        ("Schedule", {"fields": ("start_date", "end_date", "is_active")}),
        ("Time Control", {"fields": ("base_minutes", "increment_seconds")}),
    )

    @admin.display(description="Registrations")
    def registration_count(self, obj):
        return obj.registrations.count()

    @admin.action(description="Generate Round 1 pairings (FIDE seeding)")
    def start_first_round(self, request, queryset):
        for t in queryset:
            if t.matches.exists():
                self.message_user(request, f"{t.name}: pairings already exist.", level="warning")
                continue
            created = create_round_pairings(t, 1)
            self.message_user(request, f"{t.name}: created {len(created)} pairings for Round 1.")

    @admin.action(description="Recalculate standings")
    def sync_standings(self, request, queryset):
        for t in queryset:
            sync_tournament_results(t)
        self.message_user(request, f"Standings updated for {queryset.count()} tournament(s).")

    @admin.action(description="Mark as completed")
    def mark_completed(self, request, queryset):
        queryset.update(status="COMPLETED", is_active=False)


@admin.register(TournamentMatch)
class TournamentMatchAdmin(admin.ModelAdmin):
    list_display = (
        "tournament", "round_number", "board_number",
        "player1", "player2", "result", "mode_display", "scheduled_at",
    )
    list_filter = ("tournament", "result", "round_number")
    search_fields = ("player1__username", "player2__username")
    actions = ["set_player1_win", "set_player2_win", "set_draw"]

    @admin.display(description="Mode")
    def mode_display(self, obj):
        if obj.tournament.mode == "ONLINE":
            return format_html('<span style="color:#22c55e;">Online</span>')
        return format_html('<span style="color:#94a3b8;">Offline</span>')

    def _set_result(self, queryset, result):
        from django.utils import timezone
        queryset.update(result=result, completed_at=timezone.now())

    @admin.action(description="Result: Player 1 wins")
    def set_player1_win(self, request, queryset):
        self._set_result(queryset, "PLAYER1")

    @admin.action(description="Result: Player 2 wins")
    def set_player2_win(self, request, queryset):
        self._set_result(queryset, "PLAYER2")

    @admin.action(description="Result: Draw")
    def set_draw(self, request, queryset):
        self._set_result(queryset, "DRAW")


@admin.register(TournamentRegistration)
class TournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "tournament", "registered_at")
    list_filter = ("tournament",)


@admin.register(TournamentResult)
class TournamentResultAdmin(admin.ModelAdmin):
    list_display = ("tournament", "player", "position", "points", "wins", "draws", "losses")
    list_filter = ("tournament",)


@admin.register(TournamentRound)
class TournamentRoundAdmin(admin.ModelAdmin):
    list_display = ("tournament", "round_number", "is_complete", "started_at")
    list_filter = ("tournament", "is_complete")
