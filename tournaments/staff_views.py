from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST, require_http_methods

from accounts.permissions import (
    RESULT_STAFF_GROUP,
    SUPERADMIN_GROUP,
    TOURNAMENT_MANAGER_GROUP,
    can_record_results,
    ensure_default_groups,
    is_superadmin,
    is_tournament_manager,
)
from .models import Tournament, TournamentMatch
from .models import AuditLog
from .standings import sync_tournament_results

User = get_user_model()

ROLE_GROUPS = {
    "result_staff": RESULT_STAFF_GROUP,
    "manager": TOURNAMENT_MANAGER_GROUP,
    "superadmin": SUPERADMIN_GROUP,
}


def audit(actor, action, *, target_user=None, tournament=None, match=None, meta=""):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_user=target_user,
        tournament=tournament,
        match=match,
        meta=(meta or "")[:96],
    )


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
    active_tournaments = (
        Tournament.objects.filter(is_active=True)
        .only("id", "name", "status", "start_date", "current_round", "total_rounds", "mode", "is_active")
        .order_by("-start_date", "name")
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

    elevated_group_names = [RESULT_STAFF_GROUP, TOURNAMENT_MANAGER_GROUP, SUPERADMIN_GROUP]
    staff_users = []
    if is_superadmin(request.user):
        staff_users = (
            User.objects.filter(
                Q(groups__name__in=elevated_group_names) | Q(is_staff=True) | Q(is_superuser=True)
            )
            .distinct()
            .only("id", "username", "first_name", "last_name", "email", "is_staff", "is_superuser", "is_active")
            .prefetch_related("groups")
            .order_by("username")
        )

    return render(request, "staff/portal.html", {
        "active_tournaments": active_tournaments,
        "pending_matches": pending,
        "recent_matches": recent,
        "pending_count": pending.count(),
        "can_manage_tournaments": is_tournament_manager(request.user),
        "is_superadmin": is_superadmin(request.user),
        "staff_users": staff_users,
        "audit_logs": AuditLog.objects.select_related("actor", "target_user", "tournament", "match")[:40] if is_superadmin(request.user) else [],
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
    audit(request.user, AuditLog.RESULT_RECORD, tournament=tournament_match.tournament, match=tournament_match, meta=result)

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


@require_POST
@login_required
@user_passes_test(is_tournament_manager)
def staff_end_tournament(request, tournament_id):
    with transaction.atomic():
        tournament = get_object_or_404(Tournament.objects.select_for_update(), id=tournament_id)
        pending_count = tournament.matches.filter(result="PENDING").count()
        force = request.POST.get("force") == "1"
        if pending_count and not force:
            messages.error(
                request,
                f"{tournament.name} still has {pending_count} pending result(s). Use force end only after confirming standings.",
            )
            return redirect("staff_portal")

        tournament.status = "COMPLETED"
        tournament.is_active = False
        tournament.end_date = now().date()
        tournament.save(update_fields=["status", "is_active", "end_date"])
        sync_tournament_results(tournament)
        audit(request.user, AuditLog.TOURNAMENT_END, tournament=tournament, meta=f"force={int(force)}")

    messages.success(request, f"{tournament.name} ended and standings were synchronized.")
    return redirect("staff_portal")


@require_POST
@login_required
@user_passes_test(is_superadmin)
def staff_set_role(request):
    ensure_default_groups()
    username = request.POST.get("username", "").strip()
    user_id = request.POST.get("user_id")
    role = request.POST.get("role")
    op = request.POST.get("op")
    group_name = ROLE_GROUPS.get(role)
    if not group_name or op not in ("add", "remove"):
        messages.error(request, "Invalid role action.")
        return redirect("staff_portal")

    user = User.objects.filter(id=user_id).first() if user_id else User.objects.filter(username__iexact=username).first()
    if not user:
        messages.error(request, "User was not found.")
        return redirect("staff_portal")

    if user == request.user and role == "superadmin" and op == "remove":
        messages.error(request, "You cannot remove your own Superadmin access.")
        return redirect("staff_portal")

    group = Group.objects.get(name=group_name)
    if op == "add":
        user.groups.add(group)
        if role == "superadmin":
            user.is_staff = True
            user.is_superuser = True
        user.is_active = True
        user.save(update_fields=["is_staff", "is_superuser", "is_active"])
        audit(request.user, AuditLog.ROLE_ADD, target_user=user, meta=group_name)
        messages.success(request, f"{group_name} added for {user.display_name}.")
    else:
        user.groups.remove(group)
        if role == "superadmin":
            user.is_superuser = False
            user.is_staff = False
        user.save(update_fields=["is_staff", "is_superuser"])
        audit(request.user, AuditLog.ROLE_REMOVE, target_user=user, meta=group_name)
        messages.success(request, f"{group_name} removed for {user.display_name}.")
    return redirect("staff_portal")


@require_POST
@login_required
@user_passes_test(is_superadmin)
def staff_disable_user(request, user_id):
    if user_id == request.user.id:
        messages.error(request, "You cannot disable your own staff access from this page.")
        return redirect("staff_portal")

    target = get_object_or_404(User, id=user_id)
    elevated_group_names = [RESULT_STAFF_GROUP, TOURNAMENT_MANAGER_GROUP, SUPERADMIN_GROUP]
    target.groups.remove(*Group.objects.filter(name__in=elevated_group_names))
    target.is_staff = False
    target.is_superuser = False
    target.save(update_fields=["is_staff", "is_superuser"])
    audit(request.user, AuditLog.STAFF_DISABLE, target_user=target)
    messages.success(request, f"Staff access disabled for {target.display_name}.")
    return redirect("staff_portal")


@login_required
def staff_logout(request):
    logout(request)
    messages.info(request, "Signed out of staff portal.")
    return redirect("staff_login")
