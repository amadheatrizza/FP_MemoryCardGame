import socket
import threading
import json
import uuid
import string
import random
import time
from concurrent.futures import ProcessPoolExecutor
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
    def __init__(self, player_id: str, socket_conn, name: str = ""):
        self.id = player_id
        self.socket = socket_conn
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
        if len(self.players) < 4:  # dari 2 menjadi 4
            self.players[player.id] = player
            if len(self.players) >= 2:  # mulai game saat minimal 2 pemain
                self.start_game()
            return True
        return False


    def start_game(self):
        self.state = GameState.IN_PROGRESS
        player_ids = list(self.players.keys())
        self.current_player_id = random.choice(player_ids)
        self.players[self.current_player_id].is_turn = True
        self.broadcast_game_update()
        logger.info(f"Game {self.room_id} started with players: {player_ids} at level: {self.level}")

        if self.level == "easy":
            for card in self.cards:
                card.is_revealed = True
            self.broadcast_game_update()

            def hide_all_cards():
                time.sleep(3)
                for card in self.cards:
                    if not card.is_matched:
                        card.is_revealed = False
                self.broadcast_game_update()

            threading.Thread(target=hide_all_cards, daemon=True).start()
        else:
            self.broadcast_game_update()

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
                    self.broadcast_game_update()

                threading.Thread(target=hide_cards_later, daemon=True).start()

            if all(card.is_matched for card in self.cards):
                self.finish_game()

        self.last_activity = datetime.now()
        return result

    def switch_turn(self):
        player_ids = list(self.players.keys())
        current_index = player_ids.index(self.current_player_id)
        next_index = (current_index + 1) % len(player_ids)

        # Update turn flags
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

    def broadcast_game_update(self):
        game_state = self.get_game_state()
        message = {
            "type": "game_update",
            "result": {
                "update": "cards_hidden_after_mismatch"
            },
            "game_state": game_state
        }
        for player in self.players.values():
            try:
                GameServer.send_message_static(player.socket, message)
            except Exception as e:
                logger.error(f"Error sending update to player {player.id}: {e}")

class GameServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.games: Dict[str, GameSession] = {}
        self.client_to_game: Dict[str, str] = {}
        self.executor = ProcessPoolExecutor(max_workers=4)
        self.running = False

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

    def handle_client_message(self, client_socket, player_id: str, message: Dict):
        try:
            action = message.get('action')
            response = {"success": False, "message": "Unknown action"}

            if action == 'create_room':
                level = message.get('level', 'normal')
                room_id = self.create_room(level=level)
                player = Player(player_id, client_socket, message.get('player_name', ''))
                self.join_room(room_id, player)
                response = {
                    "success": True,
                    "room_id": room_id,
                    "player_id": player_id,
                    "game_state": self.games[room_id].get_game_state()
                }

            elif action == 'join_room':
                room_id = message.get('room_id')
                if room_id in self.games:
                    player = Player(player_id, client_socket, message.get('player_name', ''))
                    if self.join_room(room_id, player):
                        response = {
                            "success": True,
                            "room_id": room_id,
                            "player_id": player_id,
                            "game_state": self.games[room_id].get_game_state()
                        }
                        self.broadcast_to_room(room_id, {
                            "type": "player_joined",
                            "game_state": self.games[room_id].get_game_state()
                        })
                    else:
                        response = {"success": False, "message": "Room is full"}
                else:
                    response = {"success": False, "message": "Room not found"}

            elif action == 'reveal_card':
                room_id = self.client_to_game.get(player_id)
                if room_id and room_id in self.games:
                    card_id = message.get('card_id')
                    result = self.games[room_id].reveal_card(card_id, player_id)
                    response = result
                    response["game_state"] = self.games[room_id].get_game_state()
                    self.broadcast_to_room(room_id, {
                        "type": "game_update",
                        "result": result,
                        "game_state": self.games[room_id].get_game_state()
                    })
                else:
                    response = {"success": False, "message": "Not in a game"}

            elif action == 'get_game_state':
                room_id = self.client_to_game.get(player_id)
                if room_id and room_id in self.games:
                    response = {
                        "success": True,
                        "game_state": self.games[room_id].get_game_state()
                    }

            return response

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {"success": False, "message": "Server error"}

    def broadcast_to_room(self, room_id: str, message: Dict):
        if room_id in self.games:
            game = self.games[room_id]
            for player in game.players.values():
                try:
                    self.send_message(player.socket, message)
                except Exception as e:
                    logger.error(f"Error broadcasting to player {player.id}: {e}")

    def send_message(self, client_socket, message: Dict):
        try:
            json_message = json.dumps(message)
            client_socket.send(f"{json_message}\n".encode())
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    @staticmethod
    def send_message_static(client_socket, message: Dict):
        try:
            json_message = json.dumps(message)
            client_socket.send(f"{json_message}\n".encode())
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def handle_client(self, client_socket, client_address):
        player_id = str(uuid.uuid4())
        logger.info(f"New client connected: {client_address} (ID: {player_id})")

        try:
            while self.running:
                data = client_socket.recv(1024).decode().strip()
                if not data:
                    break
                try:
                    message = json.loads(data)
                    response = self.handle_client_message(client_socket, player_id, message)
                    self.send_message(client_socket, response)
                except json.JSONDecodeError:
                    self.send_message(client_socket, {"success": False, "message": "Invalid JSON"})

        except Exception as e:
            logger.error(f"Error with client {client_address}: {e}")
        finally:
            self.cleanup_client(player_id)
            client_socket.close()
            logger.info(f"Client {client_address} disconnected")

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

    def start_server(self):
        self.running = True
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)

        logger.info(f"Memory Card Game Server started on {self.host}:{self.port}")

        try:
            while self.running:
                client_socket, client_address = server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        finally:
            self.running = False
            server_socket.close()
            self.executor.shutdown(wait=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Memory Card Game Server')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=8888, help='Server port')
    args = parser.parse_args()

    server = GameServer(args.host, args.port)
    server.start_server()

if __name__ == "__main__":
    main()
