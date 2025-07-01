import os
import sys
import uuid
import json
import time
import random
import socket
import threading
from glob import glob
from datetime import datetime
from enum import Enum
from typing import Dict, List

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

        if self.level == "easy":
            for card in self.cards:
                card.is_revealed = True
            def hide_all_cards():
                time.sleep(3)
                for card in self.cards:
                    if not card.is_matched:
                        card.is_revealed = False
            threading.Thread(target=hide_all_cards, daemon=True).start()

    def reveal_card(self, player_id: str, card_id: int) -> Dict:
        if self.current_player_id != player_id or self.state != GameState.IN_PROGRESS:
            return {"success": False, "message": "Not your turn"}

        if card_id >= len(self.cards):
            return {"success": False, "message": "Invalid card index"}

        card = self.cards[card_id]
        if card.is_matched or card.is_revealed:
            return {"success": False, "message": "Card already revealed or matched"}

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

                def hide_later():
                    time.sleep(1)
                    for c in revealed_copy:
                        c.is_revealed = False
                threading.Thread(target=hide_later, daemon=True).start()

            if all(card.is_matched for card in self.cards):
                self.state = GameState.FINISHED

        self.last_activity = datetime.now()
        return result

    def switch_turn(self):
        ids = list(self.players.keys())
        idx = ids.index(self.current_player_id)
        self.players[self.current_player_id].is_turn = False
        self.current_player_id = ids[(idx + 1) % len(ids)]
        self.players[self.current_player_id].is_turn = True

    def to_dict(self) -> Dict:
        return {
            "room_id": self.room_id,
            "level": self.level,
            "state": self.state.value,
            "current_player": self.current_player_id,
            "players": {
                pid: {
                    "name": p.name,
                    "score": p.score,
                    "is_turn": p.is_turn
                } for pid, p in self.players.items()
            },
            "cards": [
                {
                    "id": c.id,
                    "revealed": c.is_revealed or c.is_matched,
                    "value": c.value if c.is_revealed or c.is_matched else None,
                    "matched": c.is_matched
                } for c in self.cards
            ]
        }

class HttpServer:
    def __init__(self):
        self.games: Dict[str, GameSession] = {}
        self.client_to_game: Dict[str, str] = {}

    def _response(self, kode=200, message='OK', body=b'', headers=None):
        if headers is None:
            headers = {}
        if not isinstance(body, bytes):
            body = str(body).encode()
        tanggal = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        lines = [
            f"HTTP/1.1 {kode} {message}\r\n",
            f"Date: {tanggal}\r\n",
            "Connection: close\r\n",
            f"Content-Length: {len(body)}\r\n",
            "Content-Type: application/json\r\n",
        ] + [f"{k}: {v}\r\n" for k, v in headers.items()] + ["\r\n"]
        return "".join(lines).encode() + body

    def proses(self, raw_data):
        head, _, body = raw_data.partition("\r\n\r\n")
        lines = head.split("\r\n")
        method, path, _ = lines[0].split()
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.lower()] = v.strip()
        content_len = int(headers.get('content-length', 0))
        while len(body) < content_len:
            body += conn.recv(1024).decode()
        if method == 'POST':
            return self._handle_post(path, body)
        return self._response(404, 'Not Found', 'Only POST supported')

    def _handle_post(self, path, body):
        try:
            data = json.loads(body)
        except:
            return self._response(400, 'Bad Request', 'Invalid JSON')

        action = data.get("action")
        if action == "create_room":
            level = data.get("level", "normal")
            rid = self._create_room(level)
            p = self._register_player(rid, data.get("player_name", ""))
            return self._response(200, 'OK', json.dumps({
                "success": True,
                "room_id": rid,
                "player_id": p.id,
                "game_state": self.games[rid].to_dict()
            }))

        elif action == "join_room":
            rid = data.get("room_id")
            if rid not in self.games:
                return self._response(404, 'Not Found', 'Room not found')
            p = self._register_player(rid, data.get("player_name", ""))
            ok = self.games[rid].add_player(p)
            if not ok:
                return self._response(400, 'Bad Request', 'Room full')
            return self._response(200, 'OK', json.dumps({
                "success": True,
                "room_id": rid,
                "player_id": p.id,
                "game_state": self.games[rid].to_dict()
            }))

        elif action == "reveal_card":
            pid = data.get("player_id")
            cid = data.get("card_id")
            if pid not in self.client_to_game:
                return self._response(400, 'Bad Request', 'Unknown player')
            rid = self.client_to_game[pid]
            result = self.games[rid].reveal_card(pid, cid)
            result["game_state"] = self.games[rid].to_dict()
            return self._response(200, 'OK', json.dumps(result))

        elif action == "get_game_state":
            pid = data.get("player_id")
            if pid not in self.client_to_game:
                return self._response(400, 'Bad Request', 'Unknown player')
            rid = self.client_to_game[pid]
            return self._response(200, 'OK', json.dumps({
                "success": True,
                "game_state": self.games[rid].to_dict()
            }))

        return self._response(400, 'Bad Request', 'Unknown action')

    def _create_room(self, level):
        while True:
            rid = ''.join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
            if rid not in self.games:
                break
        self.games[rid] = GameSession(rid, level)
        return rid

    def _register_player(self, rid, name):
        pid = str(uuid.uuid4())
        player = Player(pid, name)
        self.games[rid].add_player(player)
        self.client_to_game[pid] = rid
        return player

if __name__ == "__main__":
    srv = HttpServer()
    host, port = '127.0.0.1', 8001
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(5)
    print(f"HTTP Memory Game running on {host}:{port}")

    def handler(conn, addr):
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(1024)
        head, _, body = data.partition(b"\r\n\r\n")
        content_len = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length"):
                content_len = int(line.split(b":")[1].strip())
        while len(body) < content_len:
            body += conn.recv(1024)
        full_req = (head + b"\r\n\r\n" + body).decode()
        resp = srv.proses(full_req)
        conn.sendall(resp)
        conn.close()

    while True:
        conn, addr = sock.accept()
        threading.Thread(target=handler, args=(conn, addr), daemon=True).start()
