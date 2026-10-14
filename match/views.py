from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import IntegerField, Q, Value
from django.db.models.functions import Coalesce, Greatest
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import ChallengeRequest, Match, MatchMove
from .pairing import rating_pairing_service
from .timeouts import enforce_expired_clocks
import json

User = get_user_model()
LOBBY_WAITING_LIMIT = 50
LOBBY_LIVE_LIMIT = 80
LOBBY_RECENT_LIMIT = 20


def _user_has_active_match(user):
    return Match.objects.filter(
        Q(player_white=user) | Q(player_black=user),
        status__in=['WAIT', 'LIVE'],
    ).exists()


def _rating_expr(path):
    return Coalesce(path, Value(0), output_field=IntegerField())


def _top_rating_expr():
    return Greatest(
        _rating_expr('player_white__profile__rating'),
        _rating_expr('player_black__profile__rating'),
    )


def _display_name(user):
    return user.display_name if user else None


def _serialize_waiting_match(match):
    white = match.player_white
    return {
        'id': match.id,
        'white_username': white.username if white else None,
        'white_name': _display_name(white) or 'Waiting',
        'white_rating': getattr(getattr(white, 'profile', None), 'rating', None),
        'start_time': match.start_time.isoformat() if match.start_time else None,
    }


def _serialize_live_match(match):
    white = match.player_white
    black = match.player_black
    return {
        'id': match.id,
        'white_name': _display_name(white) or 'White',
        'black_name': _display_name(black) or 'Black',
        'white_rating': getattr(getattr(white, 'profile', None), 'rating', None),
        'black_rating': getattr(getattr(black, 'profile', None), 'rating', None),
        'start_time': match.start_time.isoformat() if match.start_time else None,
        'top_rating': getattr(match, 'top_rating', None),
    }


def _serialize_recent_match(match):
    return {
        'id': match.id,
        'white_name': _display_name(match.player_white) or 'White',
        'black_name': _display_name(match.player_black) or 'Black',
        'result': match.result,
        'end_time': match.end_time.isoformat() if match.end_time else None,
    }


def lobby_payload():
    waiting_count = Match.objects.filter(status='WAIT').count()
    live_count = Match.objects.filter(status='LIVE').count()
    recent_count = Match.objects.filter(status='END').count()
    waiting_matches = Match.objects.filter(status='WAIT').select_related(
        'player_white', 'player_white__profile'
    ).defer('move_history', 'pgn', 'current_fen').order_by('-start_time')[:LOBBY_WAITING_LIMIT]
    live_matches = Match.objects.filter(status='LIVE').select_related(
        'player_white', 'player_black',
        'player_white__profile', 'player_black__profile'
    ).defer('move_history', 'pgn', 'current_fen').annotate(
        top_rating=_top_rating_expr()
    ).order_by('-top_rating', '-start_time')[:LOBBY_LIVE_LIMIT]
    recent_matches = Match.objects.filter(status='END').select_related(
        'player_white', 'player_black'
    ).defer('move_history', 'pgn', 'current_fen').order_by('-end_time')[:LOBBY_RECENT_LIMIT]
    queue_snapshot = [
        {
            'user_id': e.user_id,
            'username': e.username,
            'rating': e.rating,
            'wait_seconds': round(e.wait_seconds()),
        }
        for e in rating_pairing_service.queue_snapshot()
    ]
    return {
        'success': True,
        'counts': {
            'waiting': waiting_count,
            'live': live_count,
            'recent': recent_count,
        },
        'limits': {
            'waiting': LOBBY_WAITING_LIMIT,
            'live': LOBBY_LIVE_LIMIT,
            'recent': LOBBY_RECENT_LIMIT,
        },
        'waiting_matches': [_serialize_waiting_match(m) for m in waiting_matches],
        'live_matches': [_serialize_live_match(m) for m in live_matches],
        'recent_matches': [_serialize_recent_match(m) for m in recent_matches],
        'queue': queue_snapshot,
        'queue_size': rating_pairing_service.queue_size(),
    }


def notify_lobby_changed():
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'match_lobby',
            {'type': 'lobby.changed'}
        )

def match_view(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    if match.scheduled_start and timezone.now() < match.scheduled_start:
        return HttpResponseForbidden("This match has not started yet.")
    player_color = None
    if request.user.is_authenticated:
        if match.player_white == request.user:
            player_color = 'white'
        elif match.player_black == request.user:
            player_color = 'black'
        else:
            player_color = 'spectator'
    else:
        player_color = 'spectator'
    context = {
        'match': match,
        'player_color': player_color,
        'match_id': match_id,
    }
    return render(request, 'match.html', context)

def lobby_view(request):
    waiting_matches = Match.objects.filter(status='WAIT').select_related(
        'player_white', 'player_white__profile'
    ).defer('move_history', 'pgn', 'current_fen').order_by('-start_time')[:LOBBY_WAITING_LIMIT]
    live_matches = Match.objects.filter(status='LIVE').select_related(
        'player_white', 'player_black',
        'player_white__profile', 'player_black__profile'
    ).defer('move_history', 'pgn', 'current_fen').annotate(
        top_rating=_top_rating_expr()
    ).order_by('-top_rating', '-start_time')[:LOBBY_LIVE_LIMIT]
    recent_matches = Match.objects.filter(status='END').select_related(
        'player_white', 'player_black'
    ).defer('move_history', 'pgn', 'current_fen').order_by('-end_time')[:LOBBY_RECENT_LIMIT]
    queue_entries = rating_pairing_service.queue_snapshot()
    user_in_queue = False
    incoming_challenges = []
    outgoing_challenges = []
    if request.user.is_authenticated:
        user_in_queue = rating_pairing_service.is_in_queue(request.user.id)
        incoming_challenges = ChallengeRequest.objects.filter(
            challenged=request.user, status='PENDING'
        ).select_related('challenger', 'challenger__profile')
        outgoing_challenges = ChallengeRequest.objects.filter(
            challenger=request.user, status='PENDING'
        ).select_related('challenged', 'challenged__profile')
    context = {
        'waiting_matches': waiting_matches,
        'live_matches': live_matches,
        'recent_matches': recent_matches,
        'incoming_challenges': incoming_challenges,
        'outgoing_challenges': outgoing_challenges,
        'queue_entries': queue_entries,
        'queue_size': rating_pairing_service.queue_size(),
        'user_in_queue': user_in_queue,
        'user_in_queue_js': 'true' if user_in_queue else 'false',
    }
    return render(request, 'lobby.html', context)

@login_required
@require_http_methods(["POST"])
def create_match(request):
    try:
        data = json.loads(request.body) if request.body else {}
        time_control = data.get('time_control', '10+0')
        base_str, inc_str = time_control.split('+')
        base_ms = int(base_str) * 60000
        inc_ms = int(inc_str) * 1000

        with transaction.atomic():
            existing = (
                Match.objects.select_for_update()
                .filter(status='WAIT')
                .filter(Q(player_white=request.user) | Q(player_black=request.user))
                .order_by('-start_time')
                .first()
            )
            if existing:
                return JsonResponse({
                    'success': True,
                    'match_id': existing.id,
                    'redirect_url': f'/match/{existing.id}/',
                    'message': 'Existing waiting match reused',
                })

            match = Match.objects.create(
                player_white=request.user,
                status='WAIT',
                current_fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                white_time_ms=base_ms,
                black_time_ms=base_ms,
                increment_ms=inc_ms
            )
        notify_lobby_changed()
        return JsonResponse({
            'success': True,
            'match_id': match.id,
            'redirect_url': f'/match/{match.id}/'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def join_match(request, match_id):
    try:
        with transaction.atomic():
            match = get_object_or_404(Match.objects.select_for_update(), id=match_id)
            if match.status != 'WAIT':
                return JsonResponse({'success': False, 'error': 'Match is not available to join'}, status=400)
            if match.player_white == request.user or match.player_black == request.user:
                return JsonResponse({'success': True, 'match_id': match.id, 'redirect_url': f'/match/{match.id}/'})
            active_match = Match.objects.filter(
                Q(player_white=request.user) | Q(player_black=request.user),
                status__in=['WAIT', 'LIVE'],
            ).exclude(pk=match.pk).first()
            if active_match:
                return JsonResponse({
                    'success': False,
                    'error': 'You already have an active or waiting match'
                }, status=400)
            if not match.player_black:
                match.player_black = request.user
                match.status = 'LIVE'
                match.start_time = timezone.now()
                match.save(update_fields=['player_black', 'status', 'start_time'])
                notify_lobby_changed()
                return JsonResponse({'success': True, 'match_id': match.id, 'redirect_url': f'/match/{match.id}/'})
            if not match.player_white:
                match.player_white = request.user
                match.status = 'LIVE'
                match.start_time = timezone.now()
                match.save(update_fields=['player_white', 'status', 'start_time'])
                notify_lobby_changed()
                return JsonResponse({'success': True, 'match_id': match.id, 'redirect_url': f'/match/{match.id}/'})
            return JsonResponse({'success': False, 'error': 'Match is full'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def create_rematch(request, match_id):
    try:
        original = get_object_or_404(
            Match.objects.select_related('player_white', 'player_black'),
            id=match_id,
        )
        if original.status != 'END':
            return JsonResponse({
                'success': False,
                'error': 'Rematch is available after the game ends',
            }, status=400)
        if request.user.id not in (original.player_white_id, original.player_black_id):
            return JsonResponse({
                'success': False,
                'error': 'Only players from this match can create a rematch',
            }, status=403)
        if not original.player_white_id or not original.player_black_id:
            return JsonResponse({
                'success': False,
                'error': 'This match does not have two players',
            }, status=400)

        with transaction.atomic():
            active = Match.objects.select_for_update().filter(
                Q(player_white=request.user) | Q(player_black=request.user),
                status__in=['WAIT', 'LIVE'],
            ).first()
            if active:
                return JsonResponse({
                    'success': True,
                    'match_id': active.id,
                    'redirect_url': f'/match/{active.id}/',
                    'message': 'Existing active match reused',
                })

            match = Match.objects.create(
                player_white=original.player_black,
                player_black=original.player_white,
                status='LIVE',
                start_time=timezone.now(),
                white_time_ms=original.black_time_ms or 600000,
                black_time_ms=original.white_time_ms or 600000,
                increment_ms=original.increment_ms,
                is_rated=original.is_rated,
            )
        notify_lobby_changed()
        return JsonResponse({
            'success': True,
            'match_id': match.id,
            'redirect_url': f'/match/{match.id}/',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def _finish_match(match, result):
    from .services import finalize_match

    match.result = result
    match.status = 'END'
    match.end_time = timezone.now()
    match.save(update_fields=['result', 'status', 'end_time'])
    finalize_match(match)


@login_required
@require_http_methods(["POST"])
def leave_match(request, match_id):
    try:
        match = get_object_or_404(Match.objects.only('id', 'status', 'player_white_id'), id=match_id)
        if match.status != 'WAIT':
            return JsonResponse({'success': True, 'message': 'Left match'})

        if match.status == 'WAIT' and match.player_white_id == request.user.id:
            match.delete()
            notify_lobby_changed()
            return JsonResponse({'success': True, 'message': 'Match cancelled'})
        return JsonResponse({'success': True, 'message': 'Left match'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@require_http_methods(["GET"])
def match_state(request, match_id):
    try:
        enforce_expired_clocks(limit=50)
        match = get_object_or_404(
            Match.objects.only(
                'id', 'status', 'result', 'current_fen', 'start_time', 'last_move_at',
                'white_connected', 'black_connected', 'white_time_ms', 'black_time_ms',
                'increment_ms', 'player_white_id', 'player_black_id',
                'player_white__username', 'player_black__username',
                'player_white__profile__rating', 'player_black__profile__rating',
            ).select_related('player_white', 'player_black', 'player_white__profile', 'player_black__profile'),
            id=match_id
        )
        moves = list(
            MatchMove.objects
            .filter(match_id=match_id)
            .order_by('move_number')
            .values('move_number', 'san', 'uci', 'from_square', 'to_square', 'color')[:500]
        )
        clock = match.effective_clock_state()
        return JsonResponse({
            'success': True,
            'match': {
                'id': match.id,
                'status': match.status,
                'result': match.result,
                'current_fen': match.current_fen,
                'move_history': moves,
                'player_white': match.player_white.username if match.player_white else None,
                'player_black': match.player_black.username if match.player_black else None,
                'player_white_rating': match.player_white.profile.rating if match.player_white and hasattr(match.player_white, 'profile') else None,
                'player_black_rating': match.player_black.profile.rating if match.player_black and hasattr(match.player_black, 'profile') else None,
                'white_connected': match.white_connected,
                'black_connected': match.black_connected,
                'white_time_ms': clock['white_time_ms'],
                'black_time_ms': clock['black_time_ms'],
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@require_http_methods(["GET"])
def lobby_data(request):
    try:
        enforce_expired_clocks(limit=200)
        return JsonResponse(lobby_payload())
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def queue_join(request):
    try:
        user = request.user
        if _user_has_active_match(user):
            return JsonResponse({
                'success': False,
                'error': 'Finish or cancel your current match before joining the queue',
            }, status=400)
        rating = getattr(getattr(user, 'profile', None), 'rating', 600)
        joined = rating_pairing_service.join_queue(
            user_id=user.id,
            username=user.username,
            rating=rating,
        )
        notify_lobby_changed()
        return JsonResponse({
            'success': True,
            'already_queued': not joined,
            'queue_size': rating_pairing_service.queue_size(),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def queue_leave(request):
    try:
        left = rating_pairing_service.leave_queue(request.user.id)
        notify_lobby_changed()
        return JsonResponse({
            'success': True,
            'was_queued': left,
            'queue_size': rating_pairing_service.queue_size(),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

_recent_matches = {}

def _store_match_notification(user_id, match_info):
    rating_pairing_service.notify_match(user_id, match_info)
    _recent_matches[user_id] = match_info

def _pop_match_notification(user_id):
    redis_match = rating_pairing_service.get_match_notification(user_id)
    if redis_match:
        return redis_match
    return _recent_matches.pop(user_id, None)

def _store_challenge_match(user_id, match_info):
    _store_match_notification(user_id, match_info)

@login_required
@require_http_methods(["GET"])
def queue_status(request):
    user = request.user
    
    match_info = _pop_match_notification(user.id)
    if match_info:
        return JsonResponse({
            'matched': True,
            'match_id': match_info['match_id'],
            'redirect_url': f'/match/{match_info["match_id"]}/',
            'opponent': match_info['opponent'],
            'rating_diff': match_info['rating_diff'],
        })

    in_queue = rating_pairing_service.is_in_queue(user.id)
    if in_queue:
        result = rating_pairing_service.try_pair()
        if result:
            p1 = result.player1
            p2 = result.player2
            from accounts.models import User as UserModel
            u1 = UserModel.objects.get(id=p1.user_id)
            u2 = UserModel.objects.get(id=p2.user_id)
            if p1.rating >= p2.rating:
                white, black = u1, u2
            else:
                white, black = u2, u1
            match = Match.objects.create(
                player_white=white,
                player_black=black,
                status='LIVE',
                start_time=timezone.now(),
            )
            notify_lobby_changed()
            
            other_user_id = p2.user_id if user.id == p1.user_id else p1.user_id
            opponent_name = p2.username if user.id == p1.user_id else p1.username

            match_info = {
                'match_id': match.id,
                'opponent': user.username,
                'rating_diff': result.rating_diff,
            }
            _store_match_notification(other_user_id, match_info)

            return JsonResponse({
                'matched': True,
                'match_id': match.id,
                'redirect_url': f'/match/{match.id}/',
                'opponent': opponent_name,
                'rating_diff': result.rating_diff,
            })

    return JsonResponse({
        'matched': False,
        'in_queue': in_queue,
        'queue_size': rating_pairing_service.queue_size(),
        'queue': [
            {
                'username': e.username,
                'rating': e.rating,
                'wait_seconds': round(e.wait_seconds()),
            }
            for e in rating_pairing_service.queue_snapshot()
        ],
    })

@login_required
@require_http_methods(["GET"])
def match_pgn(request, match_id):
    from .services import generate_pgn
    match = get_object_or_404(Match, id=match_id)
    pgn = match.pgn or generate_pgn(match)
    return JsonResponse({'success': True, 'pgn': pgn})


@login_required
@require_http_methods(["POST"])
def send_challenge(request, username):
    challenged = get_object_or_404(User, username=username)
    if challenged == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot challenge yourself'}, status=400)
    if _user_has_active_match(request.user):
        return JsonResponse({
            'success': False,
            'error': 'Finish or cancel your current match before sending a challenge'
        }, status=400)
    if _user_has_active_match(challenged):
        return JsonResponse({
            'success': False,
            'error': f'{challenged.display_name} is already in a match'
        }, status=400)

    existing = ChallengeRequest.objects.filter(
        challenger=request.user, challenged=challenged, status='PENDING'
    ).first()
    if existing:
        return JsonResponse({
            'success': True,
            'message': 'Challenge already sent',
            'challenge_id': existing.id,
        })

    reverse = ChallengeRequest.objects.filter(
        challenger=challenged, challenged=request.user, status='PENDING'
    ).first()
    if reverse:
        return JsonResponse({
            'success': False,
            'error': f'{challenged.username} already challenged you — accept from the lobby',
            'challenge_id': reverse.id,
        }, status=400)

    challenge = ChallengeRequest.objects.create(
        challenger=request.user,
        challenged=challenged,
    )
    
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"user_{challenged.id}",
            {
                "type": "notification",
                "payload": {
                    "type": "new_challenge",
                    "challenge_id": challenge.id,
                    "challenger": request.user.display_name,
                    "challenger_username": request.user.username,
                }
            }
        )

    return JsonResponse({
        'success': True,
        'message': f'Challenge sent to {challenged.display_name}',
        'challenge_id': challenge.id,
    })


@login_required
@require_http_methods(["POST"])
def accept_challenge(request, challenge_id):
    with transaction.atomic():
        challenge = get_object_or_404(
            ChallengeRequest.objects.select_for_update().select_related('challenger', 'challenged'),
            id=challenge_id,
            challenged=request.user,
            status='PENDING',
        )
        if _user_has_active_match(challenge.challenger) or _user_has_active_match(challenge.challenged):
            challenge.status = 'CANCELLED'
            challenge.save(update_fields=['status'])
            return JsonResponse({
                'success': False,
                'error': 'One of the players is already in a match'
            }, status=400)
        match = Match.objects.create(
            player_white=challenge.challenger,
            player_black=challenge.challenged,
            status='LIVE',
            start_time=timezone.now(),
            is_rated=challenge.is_rated,
            white_time_ms=challenge.base_minutes * 60000,
            black_time_ms=challenge.base_minutes * 60000,
        )
        notify_lobby_changed()
        challenge.status = 'ACCEPTED'
        challenge.match = match
        challenge.save(update_fields=['status', 'match'])

        ChallengeRequest.objects.filter(
            challenger__in=[challenge.challenger, challenge.challenged],
            challenged__in=[challenge.challenger, challenge.challenged],
            status='PENDING',
        ).exclude(pk=challenge.pk).update(status='CANCELLED')

    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    match_info = {
        'match_id': match.id,
        'redirect_url': f'/match/{match.id}/',
        'opponent': request.user.display_name,
    }
    _store_challenge_match(challenge.challenger.id, match_info)
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"user_{challenge.challenger.id}",
            {
                "type": "notification",
                "payload": {
                    "type": "challenge_accepted",
                    "match_id": match.id,
                    "redirect_url": f'/match/{match.id}/',
                    "accepter": request.user.display_name,
                }
            }
        )
        async_to_sync(channel_layer.group_send)(
            f"user_{challenge.challenged.id}",
            {
                "type": "notification",
                "payload": {
                    "type": "challenge_ready",
                    "match_id": match.id,
                    "redirect_url": f'/match/{match.id}/',
                    "opponent": challenge.challenger.display_name,
                }
            }
        )

    return JsonResponse({
        'success': True,
        'match_id': match.id,
        'redirect_url': f'/match/{match.id}/',
    })


@login_required
@require_http_methods(["POST"])
def decline_challenge(request, challenge_id):
    challenge = get_object_or_404(
        ChallengeRequest, id=challenge_id, challenged=request.user, status='PENDING'
    )
    challenge.status = 'DECLINED'
    challenge.save(update_fields=['status'])
    return JsonResponse({'success': True, 'message': 'Challenge declined'})


@login_required
@require_http_methods(["POST"])
def cancel_challenge(request, challenge_id):
    challenge = get_object_or_404(
        ChallengeRequest, id=challenge_id, challenger=request.user, status='PENDING'
    )
    challenge.status = 'CANCELLED'
    challenge.save(update_fields=['status'])
    return JsonResponse({'success': True, 'message': 'Challenge cancelled'})


@login_required
@require_http_methods(["GET"])
def challenge_status(request):
    """Poll for accepted challenges — ensures both players reach the match page."""
    match_info = _pop_match_notification(request.user.id)
    if match_info:
        return JsonResponse({
            'matched': True,
            'match_id': match_info['match_id'],
            'redirect_url': match_info.get('redirect_url') or f'/match/{match_info["match_id"]}/',
            'opponent': match_info.get('opponent', ''),
        })

    incoming = ChallengeRequest.objects.filter(
        challenged=request.user, status='PENDING'
    ).count()
    outgoing = ChallengeRequest.objects.filter(
        challenger=request.user, status='PENDING'
    ).count()

    return JsonResponse({
        'matched': False,
        'incoming_count': incoming,
        'outgoing_count': outgoing,
    })


@login_required
@require_http_methods(["GET"])
def list_challenges(request):
    incoming = ChallengeRequest.objects.filter(
        challenged=request.user, status='PENDING'
    ).select_related('challenger', 'challenger__profile')
    outgoing = ChallengeRequest.objects.filter(
        challenger=request.user, status='PENDING'
    ).select_related('challenged', 'challenged__profile')
    return JsonResponse({
        'success': True,
        'incoming': [
            {
                'id': c.id,
                'challenger': c.challenger.username,
                'challenger_name': c.challenger.display_name,
                'rating': getattr(getattr(c.challenger, 'profile', None), 'rating', 600),
                'created_at': c.created_at.isoformat(),
            }
            for c in incoming
        ],
        'outgoing': [
            {
                'id': c.id,
                'challenged': c.challenged.username,
                'challenged_name': c.challenged.display_name,
                'rating': getattr(getattr(c.challenged, 'profile', None), 'rating', 600),
                'created_at': c.created_at.isoformat(),
            }
            for c in outgoing
        ],
    })
