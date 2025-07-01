# http.py
import json
import uuid
import string
import random
import time
import threading
from datetime import datetime
from enum import Enum
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GameState(Enum):
    WAITING_FOR_PLAYERS = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"

class Card:
    def __init__(self, card_id: int, value: str):
        self.id = card_id
        self.value = value
        self.is_revealed = False
        self.is_matched = False

class Player:
    def __init__(self, player_id: str, name: str = ""):
        self.id = player_id
        self.name = name or f"Player_{player_id[:8]}"
        self.score = 0
        self.is_turn = False

class GameSession:
    def __init__(self, room_id: str, level: str = "normal"):
        self.room_id = room_id
        self.level = level
        self.players: Dict[str, Player] = {}
        self.cards: List[Card] = []
        self.state = GameState.WAITING_FOR_PLAYERS
        self.current_player_id = None
        self.revealed_cards = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.initialize_cards()

    def initialize_cards(self, pairs=8):
        values = [f"card_{i}" for i in range(pairs)]
        all_cards = values + values
        random.shuffle(all_cards)
        self.cards = [Card(i, value) for i, value in enumerate(all_cards)]

    def add_player(self, player: Player) -> bool:
        if len(self.players) < 4:
            self.players[player.id] = player
            if len(self.players) >= 2:
                self.start_game()
            return True
        return False

    def start_game(self):
        self.state = GameState.IN_PROGRESS
        player_ids = list(self.players.keys())
        self.current_player_id = random.choice(player_ids)
        self.players[self.current_player_id].is_turn = True
        logger.info(f"Game {self.room_id} started with players: {player_ids} at level: {self.level}")

        if self.level == "easy":
            for card in self.cards:
                card.is_revealed = True

            def hide_all_cards():
                time.sleep(3)
                for card in self.cards:
                    if not card.is_matched:
                        card.is_revealed = False

            threading.Thread(target=hide_all_cards, daemon=True).start()

    def reveal_card(self, card_id: int, player_id: str) -> Dict:
        if self.current_player_id != player_id or self.state != GameState.IN_PROGRESS:
            return {"success": False, "message": "Not your turn"}

        if card_id >= len(self.cards) or self.cards[card_id].is_matched or self.cards[card_id].is_revealed:
            return {"success": False, "message": "Invalid card selection"}

        card = self.cards[card_id]
        card.is_revealed = True
        self.revealed_cards.append(card)

        result = {"success": True, "card": {"id": card.id, "value": card.value}}

        if len(self.revealed_cards) == 2:
            if self.revealed_cards[0].value == self.revealed_cards[1].value:
                for c in self.revealed_cards:
                    c.is_matched = True
                self.players[player_id].score += 1
                result["match"] = True
                result["continue_turn"] = True
                self.revealed_cards = []
            else:
                result["match"] = False
                result["continue_turn"] = False
                revealed_copy = list(self.revealed_cards)
                self.revealed_cards = []
                self.switch_turn()

                def hide_cards_later():
                    time.sleep(0.5)
                    for c in revealed_copy:
                        c.is_revealed = False

                threading.Thread(target=hide_cards_later, daemon=True).start()

            if all(card.is_matched for card in self.cards):
                self.finish_game()

        self.last_activity = datetime.now()
        return result

    def switch_turn(self):
        player_ids = list(self.players.keys())
        current_index = player_ids.index(self.current_player_id)
        next_index = (current_index + 1) % len(player_ids)
        self.players[self.current_player_id].is_turn = False
        self.current_player_id = player_ids[next_index]
        self.players[self.current_player_id].is_turn = True

    def finish_game(self):
        self.state = GameState.FINISHED
        scores = [(pid, player.score) for pid, player in self.players.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def get_game_state(self) -> Dict:
        return {
            "room_id": self.room_id,
            "level": self.level,
            "state": self.state.value,
            "players": {
                pid: {
                    "name": player.name,
                    "score": player.score,
                    "is_turn": player.is_turn
                } for pid, player in self.players.items()
            },
            "cards": [
                {
                    "id": card.id,
                    "revealed": card.is_revealed or card.is_matched,
                    "value": card.value if (card.is_revealed or card.is_matched) else None,
                    "matched": card.is_matched
                } for card in self.cards
            ],
            "current_player": self.current_player_id
        }

class GameServer:
    def __init__(self):
        self.games: Dict[str, GameSession] = {}
        self.client_to_game: Dict[str, str] = {}

    def _response(self, kode=200, message='OK', body=b'', headers=None):
        if headers is None:
            headers = {}
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        tanggal = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        lines = [
            f"HTTP/1.1 {kode} {message}\r\n",
            f"Date: {tanggal}\r\n",
            "Connection: close\r\n",
            f"Content-Length: {len(body)}\r\n",
            "Content-Type: application/json\r\n",
        ] + [f"{k}: {v}\r\n" for k, v in headers.items()] + ["\r\n"]
        return "".join(lines).encode() + body

    def proses(self, raw_data, connection):
        requests = raw_data.split("\r\n")
        lines = requests[0]
        j = lines.split(" ")
        try:
            method = j[0].upper().strip()
            if method == 'POST':
                path = j[1].strip()
                body_start = False
                body = ""
                for line in requests:
                    if body_start:
                        body = line
                        break
                    if line == "":
                        body_start = True
                
                return self._handle_post(path, body, connection)
            else:
                return self._response(400, 'Bad Request', {'error': 'Only POST method supported'})
        except IndexError:
            return self._response(400, 'Bad Request', {'error': 'Invalid request'})

    def _handle_post(self, path, body, connection):
        try:
            data = json.loads(body) if body else {}
            
            if path == '/create_room':
                level = data.get('level', 'normal')
                player_name = data.get('player_name', '')
                room_id = self.create_room(level)
                player_id = str(uuid.uuid4())
                player = Player(player_id, player_name)
                self.join_room(room_id, player)
                return self._response(200, 'OK', {
                    'success': True,
                    'room_id': room_id,
                    'player_id': player_id,
                    'game_state': self.games[room_id].get_game_state()
                })
                
            elif path == '/join_room':
                room_id = data.get('room_id')
                player_name = data.get('player_name', '')
                if room_id in self.games:
                    player_id = str(uuid.uuid4())
                    player = Player(player_id, player_name)
                    if self.join_room(room_id, player):
                        return self._response(200, 'OK', {
                            'success': True,
                            'room_id': room_id,
                            'player_id': player_id,
                            'game_state': self.games[room_id].get_game_state()
                        })
                    else:
                        return self._response(400, 'Bad Request', {'error': 'Room is full'})
                else:
                    return self._response(404, 'Not Found', {'error': 'Room not found'})
                    
            elif path == '/reveal_card':
                player_id = data.get('player_id')
                room_id = self.client_to_game.get(player_id)
                if room_id and room_id in self.games:
                    card_id = data.get('card_id')
                    result = self.games[room_id].reveal_card(card_id, player_id)
                    result['game_state'] = self.games[room_id].get_game_state()
                    return self._response(200, 'OK', result)
                else:
                    return self._response(400, 'Bad Request', {'error': 'Not in a game'})
                    
            elif path == '/game_state':
                player_id = data.get('player_id')
                room_id = self.client_to_game.get(player_id)
                if room_id and room_id in self.games:
                    return self._response(200, 'OK', {
                        'success': True,
                        'game_state': self.games[room_id].get_game_state()
                    })
                else:
                    return self._response(400, 'Bad Request', {'error': 'Not in a game'})
                    
            else:
                return self._response(404, 'Not Found', {'error': 'Endpoint not found'})
                
        except json.JSONDecodeError:
            return self._response(400, 'Bad Request', {'error': 'Invalid JSON'})
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return self._response(500, 'Internal Server Error', {'error': str(e)})

    def create_room(self, level="normal") -> str:
        room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self.games[room_id] = GameSession(room_id, level=level)
        logger.info(f"Created room: {room_id} with level: {level}")
        return room_id

    def join_room(self, room_id: str, player: Player) -> bool:
        if room_id in self.games:
            success = self.games[room_id].add_player(player)
            if success:
                self.client_to_game[player.id] = room_id
                logger.info(f"Player {player.id} joined room {room_id}")
            return success
        return False

    def cleanup_client(self, player_id: str):
        if player_id in self.client_to_game:
            room_id = self.client_to_game[player_id]
            if room_id in self.games:
                game = self.games[room_id]
                if player_id in game.players:
                    del game.players[player_id]
                    if len(game.players) == 0:
                        del self.games[room_id]
                        logger.info(f"Removed empty room: {room_id}")
            del self.client_to_game[player_id]