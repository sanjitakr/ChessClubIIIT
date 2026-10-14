from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db import IntegrityError, transaction
from django.utils.timezone import now
from django.views.decorators.http import require_POST, require_http_methods

from accounts.permissions import can_record_results, is_superadmin, is_tournament_manager
from .models import AuditLog, Tournament, TournamentRegistration, TournamentMatch, TournamentRound
from .services import create_round_pairings
from .standings import compute_standings, sync_tournament_results
from .swiss import recommended_rounds


def audit(actor, action, *, tournament=None, match=None, meta=""):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        tournament=tournament,
        match=match,
        meta=(meta or "")[:96],
    )


def can_correct_offline_result(tournament_match):
    tournament = tournament_match.tournament
    if tournament.mode != "OFFLINE" or tournament_match.result == "PENDING":
        return False
    return not tournament.matches.filter(round_number__gt=tournament_match.round_number).exists()


@require_POST
@login_required
def toggle_registration(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    if not tournament.registration_open():
        if tournament.registration_start_time and now() < tournament.registration_start_time:
            messages.error(request, "Registration has not opened yet.")
        else:
            messages.error(request, "Registration is closed.")
        return redirect(request.META.get('HTTP_REFERER', 'tournaments'))
            
    with transaction.atomic():
        tournament = Tournament.objects.select_for_update().get(pk=tournament.pk)
        reg = TournamentRegistration.objects.filter(user=request.user, tournament=tournament).first()
        if reg:
            was_waitlisted = reg.is_waitlisted
            reg.delete()
            messages.success(request, "You have been unregistered.")
            if not was_waitlisted and tournament.max_players > 0:
                first_waitlisted = tournament.registrations.select_for_update().filter(
                    is_waitlisted=True
                ).order_by('registered_at').first()
                if first_waitlisted:
                    first_waitlisted.is_waitlisted = False
                    first_waitlisted.save(update_fields=['is_waitlisted'])
        else:
            is_waitlisted = False
            if tournament.max_players > 0:
                current_regs = tournament.registrations.filter(is_waitlisted=False).count()
                if current_regs >= tournament.max_players:
                    is_waitlisted = True
                    messages.warning(request, "Tournament is full. You have been added to the waitlist.")

            try:
                TournamentRegistration.objects.create(
                    user=request.user,
                    tournament=tournament,
                    is_waitlisted=is_waitlisted
                )
                if not is_waitlisted:
                    messages.success(request, "You have successfully registered.")
            except IntegrityError:
                messages.info(request, "You are already registered for this tournament.")

    return redirect(request.META.get('HTTP_REFERER', 'tournaments'))

@require_POST
@user_passes_test(is_tournament_manager)
def guest_register(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    guest_name = request.POST.get('guest_name', '').strip()
    if not guest_name:
        messages.error(request, "Guest name is required.")
        return redirect('tournament_detail', tournament_id=tournament.id)
        
    if not tournament.is_offline:
        messages.error(request, "External participants can only be registered for OTB tournaments.")
        return redirect('tournament_detail', tournament_id=tournament.id)

    if not tournament.registration_open():
        messages.error(request, "Registration is closed.")
        return redirect('tournament_detail', tournament_id=tournament.id)

    with transaction.atomic():
        tournament = Tournament.objects.select_for_update().get(pk=tournament.pk)
        if tournament.registrations.filter(is_guest=True, guest_name__iexact=guest_name).exists():
            messages.info(request, f"Guest {guest_name} is already registered.")
            return redirect('tournament_detail', tournament_id=tournament.id)

        is_waitlisted = False
        if tournament.max_players > 0:
            current_regs = tournament.registrations.filter(is_waitlisted=False).count()
            if current_regs >= tournament.max_players:
                is_waitlisted = True

        TournamentRegistration.objects.create(
            tournament=tournament,
            is_guest=True,
            guest_name=guest_name,
            is_waitlisted=is_waitlisted
        )
    if is_waitlisted:
        messages.warning(request, f"Guest {guest_name} added to waitlist.")
    else:
        messages.success(request, f"Guest {guest_name} registered.")
    
    return redirect('tournament_detail', tournament_id=tournament.id)

@require_POST
@user_passes_test(is_tournament_manager)
def extend_registration(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.registration_end_time:
        messages.error(request, "Cannot extend since there is no hard deadline set.")
        return redirect('tournament_detail', tournament_id=tournament.id)

    if not tournament.can_extend_registration():
        messages.error(request, "Registration has already been extended by the maximum of 15 minutes.")
        return redirect('tournament_detail', tournament_id=tournament.id)

    from datetime import timedelta
    current_end = tournament.registration_deadline()
    max_deadline = tournament.max_extension_deadline()
    new_deadline = min(current_end + timedelta(minutes=15), max_deadline)
    tournament.registration_extended_until = new_deadline
    tournament.save(update_fields=['registration_extended_until'])
    messages.success(
        request,
        f"Registration extended. New deadline: {new_deadline.strftime('%b %d, %H:%M')}",
    )
    return redirect('tournament_detail', tournament_id=tournament.id)


@require_POST
@user_passes_test(is_tournament_manager)
def generate_matches(request, tournament_id):
    with transaction.atomic():
        tournament = get_object_or_404(Tournament.objects.select_for_update(), id=tournament_id)

        if TournamentMatch.objects.filter(tournament=tournament).exists():
            messages.warning(request, "Pairings already exist. Use 'Generate Next Round' for Swiss events.")
            return redirect("tournament_detail", tournament_id=tournament.id)

        if tournament.pairing_type.startswith('CUSTOM'):
            return redirect('tournaments')

        created = create_round_pairings(tournament, 1)
    messages.success(request, f"Round 1: {len(created)} pairings generated using FIDE rating order.")
    return redirect("tournament_detail", tournament_id=tournament.id)


@require_POST
@user_passes_test(is_tournament_manager)
def generate_next_round(request, tournament_id):
    with transaction.atomic():
        tournament = get_object_or_404(Tournament.objects.select_for_update(), id=tournament_id)
        next_round = tournament.current_round + 1

        pending = tournament.matches.filter(round_number=tournament.current_round, result="PENDING")
        if pending.exists():
            messages.error(request, f"Round {tournament.current_round} still has pending results.")
            return redirect("tournament_detail", tournament_id=tournament.id)

        if tournament.total_rounds and next_round > tournament.total_rounds:
            messages.info(request, "All rounds complete.")
            tournament.status = "COMPLETED"
            tournament.is_active = False
            tournament.save(update_fields=["status", "is_active"])
            sync_tournament_results(tournament)
            return redirect("tournament_detail", tournament_id=tournament.id)

        if tournament.rounds.filter(round_number=next_round).exists():
            messages.warning(request, f"Round {next_round} already exists.")
            return redirect("tournament_detail", tournament_id=tournament.id)

        if tournament.rounds.filter(round_number=tournament.current_round).exists():
            TournamentRound.objects.filter(
                tournament=tournament, round_number=tournament.current_round
            ).update(is_complete=True)

        created = create_round_pairings(tournament, next_round)
    messages.success(request, f"Round {next_round}: {len(created)} pairings generated.")
    return redirect("tournament_detail", tournament_id=tournament.id)


@require_POST
@user_passes_test(can_record_results)
def report_result(request, match_id):
    tournament_match = get_object_or_404(TournamentMatch, id=match_id)
    result = request.POST.get("result")
    if result not in ("PLAYER1", "PLAYER2", "DRAW"):
        messages.error(request, "Invalid result.")
        return redirect("tournament_detail", tournament_id=tournament_match.tournament_id)

    is_correction = tournament_match.result != "PENDING"
    if is_correction and not can_correct_offline_result(tournament_match):
        messages.error(request, "Offline results can only be corrected before the next round is paired.")
        return redirect("tournament_detail", tournament_id=tournament_match.tournament_id)

    old_result = tournament_match.result
    tournament_match.result = result
    tournament_match.completed_at = now()
    tournament_match.save(update_fields=["result", "completed_at"])
    sync_tournament_results(tournament_match.tournament)
    audit(
        request.user,
        AuditLog.RESULT_CORRECT if is_correction else AuditLog.RESULT_RECORD,
        tournament=tournament_match.tournament,
        match=tournament_match,
        meta=f"{old_result}>{result}" if is_correction else result,
    )
    messages.success(request, "Result corrected." if is_correction else "Result recorded.")
    return redirect("tournament_detail", tournament_id=tournament_match.tournament_id)


@require_POST
@user_passes_test(is_tournament_manager)
def update_time_control(request, tournament_id):
    tournament = get_object_or_404(Tournament.objects.select_for_update(), id=tournament_id)
    try:
        base_minutes = int(request.POST.get("base_minutes") or tournament.base_minutes)
        increment_seconds = int(request.POST.get("increment_seconds") or tournament.increment_seconds)
    except (TypeError, ValueError):
        messages.error(request, "Time control must use whole numbers.")
        return redirect("tournament_detail", tournament_id=tournament.id)

    if base_minutes < 1 or increment_seconds < 0:
        messages.error(request, "Base time must be at least 1 minute and increment cannot be negative.")
        return redirect("tournament_detail", tournament_id=tournament.id)

    if base_minutes > 180 or increment_seconds > 180:
        messages.error(request, "Time control is too large. Use 180 minutes or less and 180 seconds increment or less.")
        return redirect("tournament_detail", tournament_id=tournament.id)

    if base_minutes == tournament.base_minutes and increment_seconds == tournament.increment_seconds:
        messages.info(request, "Time control is unchanged.")
        return redirect("tournament_detail", tournament_id=tournament.id)

    match_count = tournament.matches.count()
    live_count = tournament.matches.filter(live_match__isnull=False).count()
    confirmed = request.POST.get("confirm_existing_matches") == "1"
    if match_count and not confirmed:
        messages.warning(
            request,
            f"{tournament.name} already has {match_count} pairing(s)"
            f"{f' and {live_count} live online clock(s)' if live_count else ''}. "
            "Confirm the warning before changing the tournament time control.",
        )
        return redirect("tournament_detail", tournament_id=tournament.id)

    old_time = tournament.time_control_display
    tournament.base_minutes = base_minutes
    tournament.increment_seconds = increment_seconds
    tournament.save(update_fields=["base_minutes", "increment_seconds"])
    audit(request.user, AuditLog.TIME_CONTROL, tournament=tournament, meta=f"{old_time}>{tournament.time_control_display}")

    if match_count:
        messages.warning(
            request,
            f"Time control changed from {old_time} to {tournament.time_control_display}. "
            "Existing pairings and live games keep the clocks they were created with; new pairings use the new control.",
        )
    else:
        messages.success(request, f"Time control changed to {tournament.time_control_display}.")
    return redirect("tournament_detail", tournament_id=tournament.id)


def tournament_detail(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    registered_ids = []
    user = request.user
    if user.is_authenticated:
        registered_ids = list(
            user.tournament_registrations.values_list('tournament_id', flat=True)
        )

    standings = compute_standings(tournament)
    matches = tournament.matches.select_related(
        "player1", "player2", "player1__profile", "player2__profile",
        "live_match", "white_player",
    ).order_by("round_number", "board_number")

    rounds = {}
    for m in matches:
        rounds.setdefault(m.round_number, []).append(m)
    rounds_sorted = sorted(rounds.items(), key=lambda x: x[0])

    reg_count = tournament.registrations.count()
    suggested_rounds = recommended_rounds(reg_count) if reg_count >= 2 else 0
    pending_current = matches.filter(
        round_number=tournament.current_round, result="PENDING"
    ).count() if tournament.current_round else 0

    can_manage = is_tournament_manager(user) if user.is_authenticated else False
    can_record = can_record_results(user) if user.is_authenticated else False

    user_active_match = None
    if user.is_authenticated and tournament.is_online:
        for m in matches:
            if m.result == "PENDING" and (m.player1 == user or m.player2 == user):
                if m.live_match_id:
                    user_active_match = m
                break

    reg_open = tournament.registration_open()
    confirmed_count = tournament.registered_count()
    waitlist_count = tournament.waitlist_count()
    match_count = matches.count()
    live_match_count = matches.filter(live_match__isnull=False).count()
    max_paired_round = max((m.round_number for m in matches), default=0)
    correctable_match_ids = {
        m.id for m in matches
        if (
            can_record
            and tournament.mode == "OFFLINE"
            and m.result != "PENDING"
            and m.round_number == max_paired_round
        )
    }

    return render(request, 'tournament-details.html', {
        'tournament': tournament,
        'matches': matches,
        'rounds': rounds_sorted,
        'standings': standings,
        'registrations': tournament.registrations.select_related('user', 'user__profile').order_by('is_waitlisted', 'registered_at'),
        'registered_ids': registered_ids,
        'today': now().date(),
        'is_manager': can_manage,
        'can_record_results': can_record,
        'suggested_rounds': suggested_rounds,
        'pending_current': pending_current,
        'user_active_match': user_active_match,
        'registration_open': reg_open,
        'confirmed_count': confirmed_count,
        'waitlist_count': waitlist_count,
        'match_count': match_count,
        'live_match_count': live_match_count,
        'correctable_match_ids': correctable_match_ids,
    })


def tournaments(request):
    user = request.user
    can_manage = is_tournament_manager(user) if user.is_authenticated else False
    
    if request.method == "POST" and can_manage:
        from django.contrib import messages
        from django.utils.timezone import now
        from django.utils.dateparse import parse_datetime
        name = request.POST.get("name", "").strip()
        if name:
            reg_start = parse_datetime(request.POST.get("registration_start_time") or "")
            reg_end = parse_datetime(request.POST.get("registration_end_time") or "")
            Tournament.objects.create(
                name=name,
                description=request.POST.get("description", ""),
                pairing_type=request.POST.get("pairing_type", "SWISS"),
                mode=request.POST.get("mode", "ONLINE"),
                status="UPCOMING",
                start_date=request.POST.get("start_date") or now().date(),
                base_minutes=int(request.POST.get("base_minutes") or 10),
                increment_seconds=int(request.POST.get("increment_seconds") or 0),
                venue=request.POST.get("venue", "IIIT Hyderabad Campus"),
                max_players=int(request.POST.get("max_players") or 0),
                registration_start_time=reg_start or now(),
                registration_end_time=reg_end,
            )
            messages.success(request, f'Tournament "{name}" created.')
        else:
            messages.error(request, "Tournament name is required.")
        return redirect('tournaments')

    upcoming_tournaments = Tournament.objects.all()
    if user.is_authenticated:
        registered_ids = set(
            TournamentRegistration.objects.filter(user=user)
            .values_list("tournament_id", flat=True)
        )
    else:
        registered_ids = set()
    tournaments_with_matches = set(
        TournamentMatch.objects.values_list("tournament_id", flat=True)
    )
    can_record = can_record_results(user) if user.is_authenticated else False

    return render(request, 'tournaments.html', {
        "upcoming_tournaments": upcoming_tournaments,
        "registered_ids": registered_ids,
        'is_manager': can_manage,
        'can_record_results': can_record,
        'tournaments_with_matches': tournaments_with_matches,
    })


@user_passes_test(is_tournament_manager)
def schedule_match(request, match_id):
    match = get_object_or_404(TournamentMatch, id=match_id)

    if request.method == "POST":
        from django.utils.dateparse import parse_datetime
        dt = request.POST.get("datetime")
        parsed = parse_datetime(dt) if dt else None
        if parsed:
            match.scheduled_at = parsed
            match.save(update_fields=["scheduled_at"])
        return redirect('tournament_detail', tournament_id=match.tournament.id)

    return render(request, "schedule-match.html", {
        "match": match,
        "tournament": match.tournament,
    })


@user_passes_test(is_tournament_manager)
def admin_dashboard(request):
    from newsletters.models import Newsletter
    from django.contrib import messages

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_tournament":
            name = request.POST.get("name", "").strip()
            if name:
                Tournament.objects.create(
                    name=name,
                    description=request.POST.get("description", ""),
                    pairing_type=request.POST.get("pairing_type", "SWISS"),
                    mode=request.POST.get("mode", "ONLINE"),
                    status="UPCOMING",
                    start_date=request.POST.get("start_date") or now().date(),
                    base_minutes=int(request.POST.get("base_minutes") or 10),
                    increment_seconds=int(request.POST.get("increment_seconds") or 0),
                    venue=request.POST.get("venue", "IIIT Hyderabad Campus"),
                    max_players=int(request.POST.get("max_players") or 0),
                    registration_end_time=request.POST.get("registration_end_time") or None,
                )
                messages.success(request, f'Tournament "{name}" created.')
            else:
                messages.error(request, "Tournament name is required.")
        elif action == "create_newsletter":
            title = request.POST.get("title", "").strip()
            if title:
                Newsletter.objects.create(
                    title=title,
                    excerpt=request.POST.get("excerpt", ""),
                    content=request.POST.get("content", ""),
                    author=request.user.display_name,
                )
                messages.success(request, f'Newsletter "{title}" published.')
            else:
                messages.error(request, "Newsletter title is required.")
        return redirect("admin_dashboard")

    tournaments_qs = Tournament.objects.filter(is_active=True).order_by("-start_date")
    pending_results = TournamentMatch.objects.filter(result="PENDING").select_related(
        "tournament", "player1", "player2"
    )[:20]
    from match.models import Match
    live_games = Match.objects.filter(status="LIVE").select_related(
        "player_white", "player_black"
    )[:10]
    recent_newsletters = Newsletter.objects.all()[:10]
    registration_summary = []
    for t in tournaments_qs[:8]:
        registration_summary.append({
            'tournament': t,
            'confirmed': t.registered_count(),
            'waitlist': t.waitlist_count(),
            'max_players': t.max_players,
            'registration_open': t.registration_open(),
            'deadline': t.registration_deadline(),
        })
    return render(request, "admin-dashboard.html", {
        "tournaments": tournaments_qs,
        "pending_results": pending_results,
        "live_games": live_games,
        "total_registrations": TournamentRegistration.objects.count(),
        "recent_newsletters": recent_newsletters,
        "registration_summary": registration_summary,
        "is_superadmin": is_superadmin(request.user),
    })


@require_http_methods(["GET"])
def tournament_standings_api(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    standings = compute_standings(tournament)
    data = [
        {
            "rank": s["rank"],
            "username": s["player"].username,
            "display_name": s["player"].display_name,
            "rating": getattr(getattr(s["player"], "profile", None), "rating", 600),
            "points": s["points"],
            "wins": s["wins"],
            "draws": s["draws"],
            "losses": s["losses"],
            "buchholz": round(s["buchholz"], 1),
            "sonneborn_berger": round(s["sonneborn_berger"], 1),
        }
        for s in standings
    ]
    return JsonResponse({"standings": data, "round": tournament.current_round})
