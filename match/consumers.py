import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Match
import chess

User = get_user_model()

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.group_name = f"user_{self.scope['user'].id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if self.scope["user"].is_authenticated:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

@database_sync_to_async
def get_match_state(match_id):
    match = (
        Match.objects
        .select_related("player_white", "player_black")
        .get(id=match_id)
    )

    clock = match.effective_clock_state()
    return {
        "fen": match.current_fen,
        "move_history": match.move_history,
        "status": match.status,
        "result": match.result,
        "white_player": match.player_white.username if match.player_white else None,
        "black_player": match.player_black.username if match.player_black else None,
        "white_connected": match.white_connected,
        "black_connected": match.black_connected,
        "white_time_ms": clock["white_time_ms"],
        "black_time_ms": clock["black_time_ms"],
        "increment_ms": match.increment_ms,
    }


class MatchConsumer(AsyncWebsocketConsumer):
    connection_counts = {}
    disconnect_grace_seconds = 30

    async def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.room_group_name = f'match_{self.match_id}'
        self.user = self.scope.get('user')
        
        
        self.match = await self.get_match()
        if not self.match:
            await self.close()
            return
        
        
        if not self.user or not self.user.is_authenticated:
            self.player_color = 'spectator'
        else:
            self.player_color = await self.assign_player()
            if not self.player_color:
                self.player_color = 'spectator'

        
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        
        if self.player_color in ("white", "black"):
            await self.update_connection_status(True)
        
        await self.send_game_state()
        
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_connected',
                'color': self.player_color,
                'username': self.user.username if self.user.is_authenticated else 'Anonymous'
            }
        )

    async def disconnect(self, close_code):
        
        await self.update_connection_status(False)
        if self.player_color in ("white", "black"):
            asyncio.create_task(self.forfeit_after_disconnect_grace(self.player_color))
        
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_disconnected',
                'color': self.player_color,
                'username': self.user.username if self.user.is_authenticated else 'Anonymous'
            }
        )
        
        
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def forfeit_after_disconnect_grace(self, color):
        await asyncio.sleep(self.disconnect_grace_seconds)
        should_forfeit = await self.should_forfeit_disconnected_player(color)
        if not should_forfeit:
            return
        result = '0-1' if color == 'white' else '1-0'
        winner = 'Black' if color == 'white' else 'White'
        await self.end_game(result, f'{winner} wins by disconnect forfeit')

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'move':
                await self.handle_move(data)
            elif message_type == 'offer_draw':
                await self.handle_draw_offer()
            elif message_type == 'respond_draw':
                await self.handle_draw_response(data.get('accept', False))
            elif message_type == 'resign':
                await self.handle_resign()
            elif message_type == 'forfeit':
                await self.handle_forfeit()
            elif message_type == 'flag':
                await self.handle_flag()
            elif message_type == 'request_sync':
                await self.send_game_state()
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))

    async def handle_move(self, data):
        move_from = data.get('from')
        move_to = data.get('to')
        promotion = data.get('promotion')
        
        
        match = await self.get_match()
        if match.status != 'LIVE':
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'This game is not live'
            }))
            return

        current_turn = 'white' if 'w' in match.current_fen.split()[1] else 'black'
        
        if self.player_color not in ("white", "black"):
            await self.send(json.dumps({
                "type": "error",
                "message": "Spectators cannot make moves"
            }))
            return

        if self.player_color != current_turn:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Not your turn'
            }))
            return

        clock_before = await self.get_clock_state()
        if clock_before and clock_before.get('timed_out_color') == self.player_color:
            await self.end_game_on_time(self.player_color)
            return
        
        
        is_valid, new_fen, move_uci = await self.validate_move(
            match.current_fen, move_from, move_to, promotion
        )
        
        if not is_valid:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid move'
            }))
            return
        
        
        await self.save_move(move_uci, move_from, move_to, new_fen, self.player_color)
        
        
        game_status = await self.check_game_end(new_fen)
        clock_state = await self.get_clock_state()
        
        if clock_state and (
            clock_state['white_time_ms'] <= 0 or clock_state['black_time_ms'] <= 0
        ):
            loser = 'white' if clock_state['white_time_ms'] <= 0 else 'black'
            await self.end_game_on_time(loser)
            return
        
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_move',
                'move': {
                    'from': move_from,
                    'to': move_to,
                    'uci': move_uci,
                    'promotion': promotion
                },
                'fen': new_fen,
                'game_status': game_status,
                'white_time_ms': clock_state['white_time_ms'] if clock_state else None,
                'black_time_ms': clock_state['black_time_ms'] if clock_state else None,
            }
        )

    async def handle_draw_offer(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'draw_offered',
                'by': self.player_color
            }
        )

    async def handle_draw_response(self, accept):
        if accept:
            await self.end_game('1/2-1/2', 'Draw by agreement')
        else:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'draw_declined',
                    'by': self.player_color
                }
            )

    async def handle_resign(self):
        if self.player_color not in ("white", "black"):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Spectators cannot resign'
            }))
            return
        result = '0-1' if self.player_color == 'white' else '1-0'
        winner = 'Black' if self.player_color == 'white' else 'White'
        await self.end_game(result, f'{winner} wins by resignation')

    async def handle_forfeit(self):
        if self.player_color not in ("white", "black"):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Spectators cannot forfeit'
            }))
            return
        result = '0-1' if self.player_color == 'white' else '1-0'
        winner = 'Black' if self.player_color == 'white' else 'White'
        await self.end_game(result, f'{winner} wins by forfeit')

    async def handle_flag(self):
        clock_state = await self.get_clock_state()
        timed_out = clock_state.get('timed_out_color') if clock_state else None
        if not timed_out:
            await self.send_game_state()
            return
        await self.end_game_on_time(timed_out)

    async def end_game_on_time(self, loser):
        result = '0-1' if loser == 'white' else '1-0'
        winner = 'Black' if loser == 'white' else 'White'
        await self.end_game(result, f'{winner} wins on time')

    async def end_game(self, result, reason):
        await self.save_game_result(result)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_ended',
                'result': result,
                'reason': reason
            }
        )

    
    async def send_move(self, event):
        payload = {
            'type': 'move',
            'move': event['move'],
            'fen': event['fen'],
            'game_status': event.get('game_status'),
        }
        if event.get('white_time_ms') is not None:
            payload['white_time_ms'] = event['white_time_ms']
            payload['black_time_ms'] = event['black_time_ms']
        await self.send(text_data=json.dumps(payload))

    async def player_connected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_connected',
            'color': event['color'],
            'username': event['username']
        }))

    async def player_disconnected(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_disconnected',
            'color': event['color'],
            'username': event['username'],
            'grace_seconds': self.disconnect_grace_seconds
        }))

    async def draw_offered(self, event):
        await self.send(text_data=json.dumps({
            'type': 'draw_offered',
            'by': event['by']
        }))

    async def draw_declined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'draw_declined',
            'by': event['by']
        }))

    async def game_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_ended',
            'result': event['result'],
            'reason': event['reason']
        }))

    
    @database_sync_to_async
    def get_match(self):
        try:
            return Match.objects.get(id=self.match_id)
        except Match.DoesNotExist:
            return None

    @database_sync_to_async
    def assign_player(self):
        if not self.user.is_authenticated:
            return None

        match = Match.objects.get(id=self.match_id)

        if match.player_white == self.user:
            return 'white'
        if match.player_black == self.user:
            return 'black'

        if match.status == 'WAIT':
            from django.db.models import Q
            has_other_match = Match.objects.filter(
                Q(player_white=self.user) | Q(player_black=self.user),
                status__in=['WAIT', 'LIVE'],
            ).exclude(pk=match.pk).exists()
            if has_other_match:
                return None

            if not match.player_white:
                match.player_white = self.user
                match.save()
                return 'white'
            elif not match.player_black:
                match.player_black = self.user
                match.status = 'LIVE'
                from django.utils import timezone
                match.start_time = timezone.now()
                match.save(update_fields=['player_black', 'status', 'start_time'])
                return 'black'

        return None

    @database_sync_to_async
    def update_connection_status(self, connected):
        match = Match.objects.get(id=self.match_id)
        key = (str(self.match_id), self.player_color)
        if connected:
            self.connection_counts[key] = self.connection_counts.get(key, 0) + 1
        else:
            self.connection_counts[key] = max(0, self.connection_counts.get(key, 0) - 1)
        has_connection = self.connection_counts.get(key, 0) > 0

        if self.player_color == 'white':
            match.white_connected = has_connection
        elif self.player_color == 'black':
            match.black_connected = has_connection
        else:
            return
        match.save(update_fields=['white_connected', 'black_connected'])

    @database_sync_to_async
    def should_forfeit_disconnected_player(self, color):
        match = Match.objects.get(id=self.match_id)
        if match.status != 'LIVE':
            return False
        if color == 'white':
            return not match.white_connected
        if color == 'black':
            return not match.black_connected
        return False

    @database_sync_to_async
    def validate_move(self, fen, move_from, move_to, promotion):
        try:
            board = chess.Board(fen)
            
            
            move_uci = move_from + move_to + (promotion if promotion else '')
            move = chess.Move.from_uci(move_uci)
            
            if move in board.legal_moves:
                board.push(move)
                new_fen = board.fen()
                move_uci = board.uci(move)
                return True, new_fen, move_uci
            else:
                return False, None, None
                
        except Exception as e:
            print(f"Move validation error: {e}")
            return False, None, None

    @database_sync_to_async
    def save_move(self, move_uci, move_from, move_to, new_fen, moving_color):
        match = Match.objects.get(id=self.match_id)
        match.add_move(move_uci, move_from, move_to, new_fen, moving_color=moving_color)

    @database_sync_to_async
    def get_clock_state(self):
        match = Match.objects.get(id=self.match_id)
        return match.effective_clock_state()

    @database_sync_to_async
    def check_game_end(self, fen):
        try:
            board = chess.Board(fen)
            
            if board.is_checkmate():
                winner = 'Black' if board.turn == chess.WHITE else 'White'
                result = '0-1' if board.turn == chess.WHITE else '1-0'
                from django.utils import timezone
                from .services import finalize_match
                Match.objects.filter(id=self.match_id).update(
                    status='END',
                    result=result,
                    end_time=timezone.now()
                )
                try:
                    finalize_match(Match.objects.get(id=self.match_id))
                except Exception:
                    pass
                return {
                    'game_over': True,
                    'result': result,
                    'reason': f'{winner} wins by checkmate'
                }
            elif board.is_stalemate():
                from django.utils import timezone
                from .services import finalize_match
                Match.objects.filter(id=self.match_id).update(
                    status='END',
                    result='1/2-1/2',
                    end_time=timezone.now()
                )
                try:
                    finalize_match(Match.objects.get(id=self.match_id))
                except Exception:
                    pass
                return {
                    'game_over': True,
                    'result': '1/2-1/2',
                    'reason': 'Draw by stalemate'
                }
            elif board.is_insufficient_material():
                from django.utils import timezone
                from .services import finalize_match
                Match.objects.filter(id=self.match_id).update(
                    status='END',
                    result='1/2-1/2',
                    end_time=timezone.now()
                )
                try:
                    finalize_match(Match.objects.get(id=self.match_id))
                except Exception:
                    pass
                return {
                    'game_over': True,
                    'result': '1/2-1/2',
                    'reason': 'Draw by insufficient material'
                }
            elif board.is_fifty_moves():
                from django.utils import timezone
                from .services import finalize_match
                Match.objects.filter(id=self.match_id).update(
                    status='END',
                    result='1/2-1/2',
                    end_time=timezone.now()
                )
                try:
                    finalize_match(Match.objects.get(id=self.match_id))
                except Exception:
                    pass
                return {
                    'game_over': True,
                    'result': '1/2-1/2',
                    'reason': 'Draw by fifty-move rule'
                }
            elif board.is_repetition():
                from django.utils import timezone
                from .services import finalize_match
                Match.objects.filter(id=self.match_id).update(
                    status='END',
                    result='1/2-1/2',
                    end_time=timezone.now()
                )
                try:
                    finalize_match(Match.objects.get(id=self.match_id))
                except Exception:
                    pass
                return {
                    'game_over': True,
                    'result': '1/2-1/2',
                    'reason': 'Draw by repetition'
                }
            
            return {'game_over': False}
            
        except Exception as e:
            print(f"Game end check error: {e}")
            return {'game_over': False}

    @database_sync_to_async
    def save_game_result(self, result):
        from django.utils import timezone
        from .services import finalize_match
        match = Match.objects.get(id=self.match_id)
        clock = match.effective_clock_state()
        Match.objects.filter(id=self.match_id).update(
            status='END',
            result=result,
            end_time=timezone.now(),
            white_time_ms=clock['white_time_ms'],
            black_time_ms=clock['black_time_ms'],
        )
        try:
            match = Match.objects.get(id=self.match_id)
            finalize_match(match)
        except Exception as e:
            print(f"Post-game processing error: {e}")

    async def send_game_state(self):
        state = await get_match_state(self.match_id)

        await self.send(text_data=json.dumps({
            "type": "game_state",
            "player_color": self.player_color,
            **state
        }))
