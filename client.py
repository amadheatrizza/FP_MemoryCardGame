import pygame
import socket
import json
import threading
import time
import sys
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GameState(Enum):
    MENU = "menu"
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"

class NetworkClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.player_id = None
        self.room_id = None
        self.message_queue = []
        self.running = False
        
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            self.running = True
            listen_thread = threading.Thread(target=self._listen_for_messages)
            listen_thread.daemon = True
            listen_thread.start()
            logger.info("Connected to server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def _listen_for_messages(self):
        buffer = ""
        while self.running and self.connected:
            try:
                data = self.socket.recv(1024).decode()
                if not data:
                    break
                
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            message = json.loads(line.strip())
                            self.message_queue.append(message)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON received: {line}")
                            
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                break
        
        self.connected = False
    
    def send_message(self, message: Dict):
        if self.connected:
            try:
                json_message = json.dumps(message)
                self.socket.send(f"{json_message}\n".encode())
                return True
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                self.connected = False
        return False
    
    def get_messages(self):
        messages = self.message_queue.copy()
        self.message_queue.clear()
        return messages
    
    def disconnect(self):
        self.running = False
        self.connected = False
        if self.socket:
            self.socket.close()

class Card:
    def __init__(self, card_id: int, x: int, y: int, width: int, height: int):
        self.id = card_id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.value = None
        self.revealed = False
        self.matched = False
        self.rect = pygame.Rect(x, y, width, height)
        
        self.colors = {
            'card_0': (255, 100, 100),  # Red
            'card_1': (100, 255, 100),  # Green
            'card_2': (100, 100, 255),  # Blue
            'card_3': (255, 255, 100),  # Yellow
            'card_4': (255, 100, 255),  # Magenta
            'card_5': (100, 255, 255),  # Cyan
            'card_6': (255, 150, 100),  # Orange
            'card_7': (150, 100, 255),  # Purple
        }
    
    def update(self, card_data: Dict):
        self.value = card_data.get('value')
        self.revealed = card_data.get('revealed', False)
        self.matched = card_data.get('matched', False)
    
    def draw(self, screen):
        if self.revealed or self.matched:
            color = self.colors.get(self.value, (128, 128, 128))
            pygame.draw.rect(screen, color, self.rect)
            pygame.draw.rect(screen, (0, 0, 0), self.rect, 2)
            
            center_x = self.rect.centerx
            center_y = self.rect.centery
            pygame.draw.circle(screen, (255, 255, 255), (center_x, center_y), 20)
            
            if self.matched:
                pygame.draw.lines(screen, (0, 200, 0), False, 
                                [(center_x - 10, center_y), 
                                 (center_x - 5, center_y + 5), 
                                 (center_x + 10, center_y - 5)], 3)
        else:
            pygame.draw.rect(screen, (50, 50, 150), self.rect)
            pygame.draw.rect(screen, (0, 0, 0), self.rect, 2)
            
            center_x = self.rect.centerx
            center_y = self.rect.centery
            pygame.draw.lines(screen, (100, 100, 200), False,
                            [(center_x - 15, center_y - 15),
                             (center_x + 15, center_y + 15)], 2)
            pygame.draw.lines(screen, (100, 100, 200), False,
                            [(center_x + 15, center_y - 15),
                             (center_x - 15, center_y + 15)], 2)
    
    def is_clicked(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

class Button:
    def __init__(self, x: int, y: int, width: int, height: int, text: str, color=(100, 100, 200)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = (min(255, color[0] + 50), min(255, color[1] + 50), min(255, color[2] + 50))
        self.is_hovered = False
        
    def update(self, mouse_pos: Tuple[int, int]):
        self.is_hovered = self.rect.collidepoint(mouse_pos)
    
    def draw(self, screen, font):
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, (0, 0, 0), self.rect, 2)
        
        text_surface = font.render(self.text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)
    
    def is_clicked(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

class InputBox:
    def __init__(self, x: int, y: int, width: int, height: int, placeholder: str = ""):
        self.rect = pygame.Rect(x, y, width, height)
        self.color_inactive = (100, 100, 100)
        self.color_active = (150, 150, 200)
        self.color = self.color_inactive
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self.color = self.color_active if self.active else self.color_inactive
            
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    self.text += event.unicode
    
    def draw(self, screen, font):
        pygame.draw.rect(screen, self.color, self.rect)
        pygame.draw.rect(screen, (0, 0, 0), self.rect, 2)
        
        display_text = self.text if self.text else self.placeholder
        text_color = (255, 255, 255) if self.text else (150, 150, 150)
        text_surface = font.render(display_text, True, text_color)
        screen.blit(text_surface, (self.rect.x + 5, self.rect.y + 5))

class MemoryCardGame:
    def __init__(self):
        pygame.init()
        self.width = 1000
        self.height = 700
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Memory Card Game")
        
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = GameState.MENU
        
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        
        self.client = NetworkClient()
        
        self.cards = []
        self.game_state_data = None
        self.player_id = None
        self.room_id = None
        self.players = {}
        self.current_player = None
        
        self.create_ui_elements()
        
        self.status_message = ""
        self.status_timer = 0
        
    def create_ui_elements(self):
        self.create_game_btn = Button(350, 250, 300, 60, "Create New Game")
        
        self.room_input = InputBox(350, 410, 300, 40, "Enter Room ID")
        self.join_room_btn = Button(350, 470, 300, 40, "Join Room")
        
        self.start_btn = Button(400, 500, 200, 50, "Start Game")
        
        self.back_btn = Button(50, 50, 100, 40, "Back")
        
    def connect_to_server(self):
        if not self.client.connected:
            if not self.client.connect():
                self.show_status("Failed to connect to server!")
                return False
        return True
    
    def show_status(self, message: str, duration: int = 3000):
        self.status_message = message
        self.status_timer = duration
    
    def create_cards_grid(self, num_cards: int = 16):
        self.cards.clear()
        
        cols = 4
        rows = 4
        card_width = 100
        card_height = 120
        spacing = 20
        
        start_x = (self.width - (cols * card_width + (cols - 1) * spacing)) // 2
        start_y = 150
        
        for i in range(num_cards):
            row = i // cols
            col = i % cols
            x = start_x + col * (card_width + spacing)
            y = start_y + row * (card_height + spacing)
            
            card = Card(i, x, y, card_width, card_height)
            self.cards.append(card)
    
    def handle_server_messages(self):
        messages = self.client.get_messages()
        for message in messages:
            self.process_server_message(message)
    
    def process_server_message(self, message: Dict):
        if message.get('success'):
            if 'room_id' in message:
                self.room_id = message['room_id']
                self.player_id = message['player_id']
                
            if 'game_state' in message:
                self.update_game_state(message['game_state'])
                
        elif message.get('type') == 'player_joined':
            self.update_game_state(message['game_state'])
            self.show_status("Player joined!")
            
        elif message.get('type') == 'game_update':
            self.update_game_state(message['game_state'])
            result = message.get('result', {})
            if 'match' in result:
                if result['match']:
                    self.show_status("Match found!")
                else:
                    self.show_status("No match. Turn switches.")
        else:
            self.show_status(message.get('message', 'Unknown error'))
    
    def update_game_state(self, game_state: Dict):
        self.game_state_data = game_state
        self.players = game_state.get('players', {})
        self.current_player = game_state.get('current_player')
        
        cards_data = game_state.get('cards', [])
        if not self.cards and cards_data:
            self.create_cards_grid(len(cards_data))
        
        for i, card_data in enumerate(cards_data):
            if i < len(self.cards):
                self.cards[i].update(card_data)
        
        if game_state.get('state') == 'in_progress':
            self.state = GameState.PLAYING
        elif game_state.get('state') == 'finished':
            self.state = GameState.FINISHED
        elif game_state.get('state') == 'waiting':
            self.state = GameState.WAITING
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mouse_click(event.pos)
            
            
            if self.state == GameState.MENU:
                self.room_input.handle_event(event)
        
        mouse_pos = pygame.mouse.get_pos()
        self.create_game_btn.update(mouse_pos)
        self.join_room_btn.update(mouse_pos)
        self.start_btn.update(mouse_pos)
        self.back_btn.update(mouse_pos)
    
    def handle_mouse_click(self, pos: Tuple[int, int]):
        if self.state == GameState.MENU:
            if self.create_game_btn.is_clicked(pos):
                if self.connect_to_server():
                    self.client.send_message({'action': 'create_room', 'player_name': 'Player'})
                    self.state = GameState.WAITING
            
            elif self.join_room_btn.is_clicked(pos):
                room_id = self.room_input.text.strip()
                if room_id and self.connect_to_server():
                    self.client.send_message({
                        'action': 'join_room', 
                        'room_id': room_id,
                        'player_name': 'Player'
                    })
                    self.state = GameState.WAITING
        
        elif self.state == GameState.WAITING:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.disconnect()
        
        elif self.state == GameState.PLAYING:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.disconnect()
                return
            
            if self.current_player == self.player_id:
                for card in self.cards:
                    if card.is_clicked(pos) and not card.revealed and not card.matched:
                        self.client.send_message({
                            'action': 'reveal_card',
                            'card_id': card.id
                        })
                        break
        
        elif self.state == GameState.FINISHED:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.disconnect()
    
    def draw_menu(self):
        self.screen.fill((30, 30, 50))
        
        title = self.font_large.render("Memory Card Game", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title, title_rect)
        
        self.create_game_btn.draw(self.screen, self.font_medium)
        
        room_label = self.font_small.render("Room ID:", True, (255, 255, 255))
        self.screen.blit(room_label, (350, 385))
        self.room_input.draw(self.screen, self.font_small)
        self.join_room_btn.draw(self.screen, self.font_small)
    
    def draw_waiting(self):
        self.screen.fill((30, 30, 50))
        
        self.back_btn.draw(self.screen, self.font_small)
        
        title = self.font_large.render("Waiting for Players", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title, title_rect)
        
        if self.room_id:
            room_text = self.font_medium.render(f"Room ID: {self.room_id}", True, (255, 255, 255))
            room_rect = room_text.get_rect(center=(self.width // 2, 250))
            self.screen.blit(room_text, room_rect)
        
        y_offset = 300
        for player_id, player_data in self.players.items():
            player_text = self.font_small.render(f"Player: {player_data['name']}", True, (255, 255, 255))
            self.screen.blit(player_text, (400, y_offset))
            y_offset += 30
        
        if len(self.players) < 2:
            instruction = self.font_small.render("Waiting for another player to join...", True, (200, 200, 200))
            instruction_rect = instruction.get_rect(center=(self.width // 2, 400))
            self.screen.blit(instruction, instruction_rect)
        else:
            instruction = self.font_small.render("Game will start automatically when both players are ready!", True, (200, 200, 200))
            instruction_rect = instruction.get_rect(center=(self.width // 2, 400))
            self.screen.blit(instruction, instruction_rect)
    
    def draw_game(self):
        self.screen.fill((20, 40, 20))
        
        self.back_btn.draw(self.screen, self.font_small)
        
        title = self.font_medium.render("Memory Card Game", True, (255, 255, 255))
        self.screen.blit(title, (self.width // 2 - 100, 20))
        
        x_offset = 50
        for player_id, player_data in self.players.items():
            name = player_data['name']
            score = player_data['score']
            is_turn = player_data['is_turn']
            
            color = (255, 255, 100) if is_turn else (255, 255, 255)
            if player_id == self.player_id:
                name += " (You)"
            
            score_text = self.font_small.render(f"{name}: {score}", True, color)
            self.screen.blit(score_text, (x_offset, 70))
            x_offset += 200
        
        if self.current_player:
            current_name = self.players.get(self.current_player, {}).get('name', 'Unknown')
            if self.current_player == self.player_id:
                turn_text = "Your turn!"
                color = (100, 255, 100)
            else:
                turn_text = f"{current_name}'s turn"
                color = (255, 100, 100)
            
            turn_surface = self.font_small.render(turn_text, True, color)
            turn_rect = turn_surface.get_rect(center=(self.width // 2, 110))
            self.screen.blit(turn_surface, turn_rect)
        
        for card in self.cards:
            card.draw(self.screen)
    
    def draw_finished(self):
        self.screen.fill((30, 30, 50))
        
        self.back_btn.draw(self.screen, self.font_small)
        
        title = self.font_large.render("Game Finished!", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title, title_rect)
        
        y_offset = 250
        scores = [(pid, data['score']) for pid, data in self.players.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        
        for i, (player_id, score) in enumerate(scores):
            name = self.players[player_id]['name']
            if player_id == self.player_id:
                name += " (You)"
            
            position = "Winner!" if i == 0 else f"Rank {i + 1}"
            color = (255, 255, 100) if i == 0 else (255, 255, 255)
            
            score_text = self.font_medium.render(f"{name}: {score} pairs - {position}", True, color)
            score_rect = score_text.get_rect(center=(self.width // 2, y_offset))
            self.screen.blit(score_text, score_rect)
            y_offset += 50
    
    def draw_status(self):
        if self.status_message and self.status_timer > 0:
            status_surface = self.font_small.render(self.status_message, True, (255, 255, 100))
            status_rect = status_surface.get_rect(center=(self.width // 2, self.height - 50))
            
            bg_rect = status_rect.inflate(20, 10)
            pygame.draw.rect(self.screen, (50, 50, 50), bg_rect)
            pygame.draw.rect(self.screen, (255, 255, 100), bg_rect, 2)
            
            self.screen.blit(status_surface, status_rect)
            self.status_timer -= self.clock.get_time()
    
    def run(self):
        while self.running:
            self.handle_events()
            
            if self.client.connected:
                self.handle_server_messages()
            
            if self.state == GameState.MENU:
                self.draw_menu()
            elif self.state == GameState.WAITING:
                self.draw_waiting()
            elif self.state == GameState.PLAYING:
                self.draw_game()
            elif self.state == GameState.FINISHED:
                self.draw_finished()
            
            self.draw_status()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        self.client.disconnect()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = MemoryCardGame()
    game.run()