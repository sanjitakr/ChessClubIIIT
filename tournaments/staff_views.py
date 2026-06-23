from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST, require_http_methods

from accounts.permissions import can_record_results, is_result_staff, ensure_default_groups
from .models import Tournament, TournamentMatch
from .standings import sync_tournament_results


def _staff_check(user):
    return can_record_results(user)


@require_http_methods(["GET", "POST"])
def staff_login(request):
    ensure_default_groups()
    if request.user.is_authenticated and can_record_results(request.user):
        return redirect("staff_portal")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user and can_record_results(user):
            login(request, user)
            next_url = request.GET.get("next") or "staff_portal"
            return redirect(next_url)
        error = "Invalid credentials or you do not have result-entry access."

    return render(request, "staff/login.html", {"error": error})


@login_required
@user_passes_test(_staff_check)
def staff_portal(request):
    tournaments = (
        Tournament.objects.filter(is_active=True)
        .prefetch_related("matches__player1", "matches__player2")
        .order_by("-start_date")
    )

    pending = (
        TournamentMatch.objects.filter(result="PENDING")
        .select_related("tournament", "player1", "player2", "white_player")
        .order_by("tournament__name", "round_number", "board_number")
    )

    recent = (
        TournamentMatch.objects.exclude(result="PENDING")
        .select_related("tournament", "player1", "player2")
        .order_by("-completed_at")[:15]
    )

    return render(request, "staff/portal.html", {
        "tournaments": tournaments,
        "pending_matches": pending,
        "recent_matches": recent,
        "pending_count": pending.count(),
    })


@require_POST
@login_required
@user_passes_test(_staff_check)
def staff_record_result(request, match_id):
    tournament_match = get_object_or_404(TournamentMatch, id=match_id)
    result = request.POST.get("result")
    if result not in ("PLAYER1", "PLAYER2", "DRAW"):
        messages.error(request, "Invalid result selected.")
        return redirect("staff_portal")

    tournament_match.result = result
    tournament_match.completed_at = now()
    tournament_match.save(update_fields=["result", "completed_at"])
    sync_tournament_results(tournament_match.tournament)

    p1 = tournament_match.player1.display_name
    p2 = tournament_match.player2.display_name
    if result == "PLAYER1":
        outcome = f"{p1} wins"
    elif result == "PLAYER2":
        outcome = f"{p2} wins"
    else:
        outcome = "Draw"

    messages.success(
        request,
        f"Recorded: {p1} vs {p2} — {outcome} ({tournament_match.tournament.name}, Round {tournament_match.round_number})",
    )
    return redirect("staff_portal")


@login_required
def staff_logout(request):
    logout(request)
    messages.info(request, "Signed out of staff portal.")
    return redirect("staff_login")
