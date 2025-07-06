import pygame
import socket
import json
import threading
import time
import sys
import math
import random
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GameState(Enum):
    MENU = "menu"
    LEVEL_SELECT = "level_select"
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"

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
        
        self.flip_progress = 0.0
        self.target_flip = 0.0
        self.bounce_offset = 0.0
        self.bounce_timer = 0.0
        self.shake_offset_x = 0.0
        self.shake_offset_y = 0.0
        self.shake_timer = 0.0
        self.scale = 1.0
        self.target_scale = 1.0
        self.glow_intensity = 0.0
        self.match_celebration_timer = 0.0
        
        self.colors = {
            'card_0': [(255, 120, 120), (220, 80, 80)],
            'card_1': [(120, 255, 120), (80, 220, 80)],
            'card_2': [(120, 120, 255), (80, 80, 220)],
            'card_3': [(255, 255, 120), (220, 220, 80)],
            'card_4': [(255, 120, 255), (220, 80, 220)],
            'card_5': [(120, 255, 255), (80, 220, 220)],
            'card_6': [(255, 180, 120), (220, 140, 80)],
            'card_7': [(180, 120, 255), (140, 80, 220)],
        }
        
        self.back_color = [(70, 70, 180), (40, 40, 120)]

    def update(self, card_data: Dict, dt: float):
        old_revealed = self.revealed
        old_matched = self.matched
        
        self.value = card_data.get('value')
        self.revealed = card_data.get('revealed', False)
        self.matched = card_data.get('matched', False)
        
        if self.revealed or self.matched:
            self.target_flip = 1.0
        else:
            self.target_flip = 0.0
        
        flip_speed = 8.0
        if abs(self.flip_progress - self.target_flip) > 0.01:
            if self.flip_progress < self.target_flip:
                self.flip_progress = min(1.0, self.flip_progress + flip_speed * dt)
            else:
                self.flip_progress = max(0.0, self.flip_progress - flip_speed * dt)
        
        if self.revealed and not old_revealed:
            self.bounce_timer = 0.5
        
        if self.bounce_timer > 0:
            self.bounce_timer -= dt
            bounce_progress = 1.0 - (self.bounce_timer / 0.5)
            self.bounce_offset = math.sin(bounce_progress * math.pi * 3) * 10 * (1 - bounce_progress)
        else:
            self.bounce_offset = 0
        
        if self.matched and not old_matched:
            self.match_celebration_timer = 1.0
            self.target_scale = 1.2
        
        if self.match_celebration_timer > 0:
            self.match_celebration_timer -= dt
            if self.match_celebration_timer <= 0:
                self.target_scale = 1.0
        
        scale_speed = 5.0
        if abs(self.scale - self.target_scale) > 0.01:
            if self.scale < self.target_scale:
                self.scale = min(self.target_scale, self.scale + scale_speed * dt)
            else:
                self.scale = max(self.target_scale, self.scale - scale_speed * dt)
        
        if self.shake_timer > 0:
            self.shake_timer -= dt
            shake_intensity = self.shake_timer / 0.3
            self.shake_offset_x = (random.random() - 0.5) * 10 * shake_intensity
            self.shake_offset_y = (random.random() - 0.5) * 10 * shake_intensity
        else:
            self.shake_offset_x = 0
            self.shake_offset_y = 0
        
        if self.glow_intensity > 0:
            self.glow_intensity = max(0, self.glow_intensity - dt * 2)

    def trigger_shake(self):
        self.shake_timer = 0.3

    def trigger_glow(self):
        self.glow_intensity = 1.0

    def draw_gradient_rect(self, surface, color1, color2, rect, corner_radius=15):
        temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        
        for y in range(max(1, rect.height)):
            ratio = y / max(1, rect.height)
            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            pygame.draw.line(temp_surface, (r, g, b), (0, y), (rect.width, y))
        
        mask_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(mask_surface, (255, 255, 255, 255),
                         (0, 0, rect.width, rect.height), border_radius=corner_radius)
        
        temp_surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
        
        surface.blit(temp_surface, rect.topleft)

    def draw(self, screen):
        animated_x = self.x + self.shake_offset_x
        animated_y = self.y + self.shake_offset_y - self.bounce_offset
        
        scaled_width = int(self.width * self.scale)
        scaled_height = int(self.height * self.scale)
        scaled_x = animated_x + (self.width - scaled_width) // 2
        scaled_y = animated_y + (self.height - scaled_height) // 2
        
        animated_rect = pygame.Rect(scaled_x, scaled_y, scaled_width, scaled_height)
        
        if self.glow_intensity > 0:
            glow_surface = pygame.Surface((scaled_width + 20, scaled_height + 20), pygame.SRCALPHA)
            glow_color = (255, 255, 100, int(50 * self.glow_intensity))
            pygame.draw.rect(glow_surface, glow_color,
                           (0, 0, scaled_width + 20, scaled_height + 20), border_radius=25)
            screen.blit(glow_surface, (scaled_x - 10, scaled_y - 10))
        
        flip_scale_x = abs(math.cos(self.flip_progress * math.pi))
        if flip_scale_x < 0.1:
            flip_scale_x = 0.1
        
        flip_width = int(scaled_width * flip_scale_x)
        flip_x = scaled_x + (scaled_width - flip_width) // 2
        flip_rect = pygame.Rect(flip_x, scaled_y, flip_width, scaled_height)
        
        show_front = self.flip_progress > 0.5
        
        if show_front and (self.revealed or self.matched):
            if self.value in self.colors:
                color1, color2 = self.colors[self.value]
            else:
                color1, color2 = (128, 128, 128), (100, 100, 100)
            
            self.draw_gradient_rect(screen, color1, color2, flip_rect, 15)
            
            border_color = (255, 255, 255) if not self.matched else (0, 255, 0)
            pygame.draw.rect(screen, border_color, flip_rect, 3, border_radius=15)
            
            center_x = flip_rect.centerx
            center_y = flip_rect.centery
            symbol_radius = min(20, flip_width // 4)
            
            pygame.draw.circle(screen, (255, 255, 255), (center_x, center_y), symbol_radius + 5)
            pygame.draw.circle(screen, (0, 0, 0), (center_x, center_y), symbol_radius + 5, 2)
            
            if self.value:
                symbol_color = color2
                pygame.draw.circle(screen, symbol_color, (center_x, center_y), symbol_radius)
            
            if self.matched:
                pygame.draw.lines(screen, (0, 200, 0), False,
                                [(center_x - 12, center_y),
                                 (center_x - 6, center_y + 6),
                                 (center_x + 12, center_y - 6)], 4)
        else:
            self.draw_gradient_rect(screen, self.back_color[0], self.back_color[1], flip_rect, 15)
            
            pygame.draw.rect(screen, (100, 100, 255), flip_rect, 3, border_radius=15)
            
            center_x = flip_rect.centerx
            center_y = flip_rect.centery
            
            diamond_size = min(15, flip_width // 6)
            diamond_points = [
                (center_x, center_y - diamond_size),
                (center_x + diamond_size, center_y),
                (center_x, center_y + diamond_size),
                (center_x - diamond_size, center_y)
            ]
            pygame.draw.polygon(screen, (150, 150, 255), diamond_points)
            pygame.draw.polygon(screen, (200, 200, 255), diamond_points, 2)

    def is_clicked(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

class Button:
    def __init__(self, x: int, y: int, width: int, height: int, text: str,
                 color=(70, 130, 180), hover_color=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = hover_color or (min(255, color[0] + 40),
                                          min(255, color[1] + 40),
                                          min(255, color[2] + 40))
        self.is_hovered = False
        self.scale = 1.0
        self.target_scale = 1.0

    def update(self, mouse_pos: Tuple[int, int], dt: float):
        was_hovered = self.is_hovered
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        
        if self.is_hovered and not was_hovered:
            self.target_scale = 1.05
        elif not self.is_hovered and was_hovered:
            self.target_scale = 1.0
        
        scale_speed = 8.0
        if abs(self.scale - self.target_scale) > 0.01:
            if self.scale < self.target_scale:
                self.scale = min(self.target_scale, self.scale + scale_speed * dt)
            else:
                self.scale = max(self.target_scale, self.scale - scale_speed * dt)

    def draw(self, screen, font):
        scaled_width = int(self.rect.width * self.scale)
        scaled_height = int(self.rect.height * self.scale)
        scaled_x = self.rect.x + (self.rect.width - scaled_width) // 2
        scaled_y = self.rect.y + (self.rect.height - scaled_height) // 2
        scaled_rect = pygame.Rect(scaled_x, scaled_y, scaled_width, scaled_height)
        
        current_color = self.hover_color if self.is_hovered else self.color
        
        pygame.draw.rect(screen, current_color, scaled_rect, border_radius=10)
        
        shadow_color = (max(0, current_color[0] - 50),
                       max(0, current_color[1] - 50),
                       max(0, current_color[2] - 50))
        shadow_rect = pygame.Rect(scaled_x + 2, scaled_y + 2, scaled_width, scaled_height)
        pygame.draw.rect(screen, shadow_color, shadow_rect, border_radius=10)
        pygame.draw.rect(screen, current_color, scaled_rect, border_radius=10)
        
        border_color = (255, 255, 255) if self.is_hovered else (200, 200, 200)
        pygame.draw.rect(screen, border_color, scaled_rect, 2, border_radius=10)
        
        text_surface = font.render(self.text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=scaled_rect.center)
        screen.blit(text_surface, text_rect)

    def is_clicked(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

class InputBox:
    def __init__(self, x: int, y: int, width: int, height: int, placeholder: str = ""):
        self.rect = pygame.Rect(x, y, width, height)
        self.color_inactive = (60, 60, 80)
        self.color_active = (80, 80, 120)
        self.color = self.color_inactive
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.cursor_timer = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self.color = self.color_active if self.active else self.color_inactive
            
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    if len(self.text) < 10:
                        self.text += event.unicode

    def update(self, dt: float):
        self.cursor_timer += dt

    def draw(self, screen, font):
        pygame.draw.rect(screen, self.color, self.rect, border_radius=8)
        pygame.draw.rect(screen, (200, 200, 200), self.rect, 2, border_radius=8)
        
        display_text = self.text if self.text else self.placeholder
        text_color = (255, 255, 255) if self.text else (150, 150, 150)
        text_surface = font.render(display_text, True, text_color)
        text_y = self.rect.y + (self.rect.height - text_surface.get_height()) // 2
        screen.blit(text_surface, (self.rect.x + 10, text_y))
        
        if self.active and self.cursor_timer % 1.0 < 0.5:
            cursor_x = self.rect.x + 10 + font.size(self.text)[0]
            cursor_y = self.rect.y + 5
            pygame.draw.line(screen, (255, 255, 255),
                           (cursor_x, cursor_y), (cursor_x, cursor_y + self.rect.height - 10), 2)

class NetworkClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.player_id = None
        self.room_id = None
        self.game_state_data = None
        self.polling = False

    def send_http_request(self, path: str, data: Dict) -> Dict:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))
            
            json_data = json.dumps(data)
            request = f"POST {path} HTTP/1.1\r\n"
            request += f"Host: {self.host}:{self.port}\r\n"
            request += "Content-Type: application/json\r\n"
            request += f"Content-Length: {len(json_data)}\r\n"
            request += "Connection: close\r\n"
            request += "\r\n"
            request += json_data
            
            sock.send(request.encode())
            
            response = b""
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                response += data
            
            sock.close()
            
            response_str = response.decode()
            if "\r\n\r\n" in response_str:
                headers, body = response_str.split("\r\n\r\n", 1)
                if body:
                    return json.loads(body)
            
            return {"success": False, "error": "Invalid response"}
            
        except Exception as e:
            logger.error(f"HTTP request error: {e}")
            return {"success": False, "error": str(e)}

    def create_room(self, level: str = "normal", player_name: str = "Player") -> Dict:
        response = self.send_http_request("/create_room", {
            "level": level,
            "player_name": player_name
        })
        
        if response.get("success"):
            self.player_id = response.get("player_id")
            self.room_id = response.get("room_id")
            
        return response

    def join_room(self, room_id: str, player_name: str = "Player") -> Dict:
        response = self.send_http_request("/join_room", {
            "room_id": room_id,
            "player_name": player_name
        })
        
        if response.get("success"):
            self.player_id = response.get("player_id")
            self.room_id = response.get("room_id")
            
        return response

    def reveal_card(self, card_id: int) -> Dict:
        if not self.player_id:
            return {"success": False, "error": "Not connected"}
            
        return self.send_http_request("/reveal_card", {
            "player_id": self.player_id,
            "card_id": card_id
        })

    def get_game_state(self) -> Dict:
        if not self.player_id:
            return {"success": False, "error": "Not connected"}
            
        return self.send_http_request("/game_state", {
            "player_id": self.player_id
        })

    def poll_game_state(self):
        while hasattr(self, 'polling') and self.polling:
            try:
                response = self.get_game_state()
                if response.get("success"):
                    self.game_state_data = response.get("game_state")
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(1)

    def start_polling(self):
        self.polling = True
        self.poll_thread = threading.Thread(target=self.poll_game_state, daemon=True)
        self.poll_thread.start()

    def stop_polling(self):
        self.polling = False

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
        self.last_processed_state = None
        
        self.cards = []
        self.players = {}
        self.current_player = None
        self.selected_level = "normal"
        
        self.create_ui_elements()
        
        self.status_message = ""
        self.status_timer = 0
        self.bg_time = 0
        
        self.last_poll_time = 0
        self.poll_interval = 0.5

    def create_ui_elements(self):
        self.create_game_btn = Button(350, 200, 300, 50, "Create New Game", (70, 130, 180))
        self.room_input = InputBox(350, 275 + 50, 300, 35, "Enter Room ID")
        self.join_game_btn = Button(350, 320 + 60, 300, 50, "Join Game", (100, 150, 100))
        self.easy_level_btn = Button(330, 200, 200, 80, "Easy", (100, 200, 100))
        self.normal_level_btn = Button(570, 200, 200, 80, "Normal", (200, 100, 100))
        self.start_btn = Button(400, 500, 200, 50, "Start Game", (180, 70, 70))
        self.back_btn = Button(50, 50, 100, 40, "Back", (120, 120, 120))

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

    def process_game_state(self, game_state: Dict):
        if not game_state:
            return
            
        self.players = game_state.get('players', {})
        self.current_player = game_state.get('current_player')
        
        cards_data = game_state.get('cards', [])
        if not self.cards and cards_data:
            self.create_cards_grid(len(cards_data))
        
        dt = self.clock.get_time() / 1000.0
        for i, card_data in enumerate(cards_data):
            if i < len(self.cards):
                old_revealed = self.cards[i].revealed
                old_matched = self.cards[i].matched
                
                self.cards[i].update(card_data, dt)
                
                if card_data.get('matched') and not old_matched:
                    self.cards[i].match_celebration_timer = 1.0
                elif card_data.get('revealed') != old_revealed and not card_data.get('revealed'):
                    self.cards[i].trigger_shake()
        
        if game_state.get('state') == 'in_progress':
            self.state = GameState.PLAYING
        elif game_state.get('state') == 'finished':
            self.state = GameState.FINISHED
        elif game_state.get('state') == 'waiting':
            self.state = GameState.WAITING

    def handle_events(self):
        dt = self.clock.get_time() / 1000.0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mouse_click(event.pos)
            
            if self.state == GameState.MENU:
                self.room_input.handle_event(event)
        
        mouse_pos = pygame.mouse.get_pos()
        self.create_game_btn.update(mouse_pos, dt)
        self.join_game_btn.update(mouse_pos, dt)
        self.easy_level_btn.update(mouse_pos, dt)
        self.normal_level_btn.update(mouse_pos, dt)
        self.start_btn.update(mouse_pos, dt)
        self.back_btn.update(mouse_pos, dt)
        
        if self.state == GameState.MENU:
            self.room_input.update(dt)
        
        for card in self.cards:
            card.update({'value': card.value, 'revealed': card.revealed, 'matched': card.matched}, dt)
        
        if self.status_timer > 0:
            self.status_timer -= dt * 1000

    def handle_mouse_click(self, pos: Tuple[int, int]):
        if self.state == GameState.MENU:
            if self.create_game_btn.is_clicked(pos):
                self.state = GameState.LEVEL_SELECT
            
            elif self.join_game_btn.is_clicked(pos):
                room_id = self.room_input.text.strip()
                if room_id:
                    response = self.client.join_room(room_id, "Player")
                    if response.get("success"):
                        self.show_status(f"Joined room {room_id}")
                        self.state = GameState.WAITING
                        if 'game_state' in response:
                          self.process_game_state(response['game_state'])
                        
                        self.client.start_polling()
                    else:
                        self.show_status(response.get("error", "Failed to join room"))
        
        elif self.state == GameState.LEVEL_SELECT:
            level_chosen = None
            if self.easy_level_btn.is_clicked(pos):
                level_chosen = "easy"
            elif self.normal_level_btn.is_clicked(pos):
                level_chosen = "normal"
            
            if level_chosen:
                self.selected_level = level_chosen
                response = self.client.create_room(self.selected_level, "Player")
                if response.get("success"):
                    self.state = GameState.WAITING
                    if 'game_state' in response:
                        self.process_game_state(response['game_state'])
                    
                    self.client.start_polling()

            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
        
        elif self.state == GameState.WAITING:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.stop_polling()
                self.client.player_id = None
                self.client.room_id = None
        
        elif self.state == GameState.PLAYING:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.stop_polling()
                self.client.player_id = None
                self.client.room_id = None
                return
            
            if self.current_player == self.client.player_id:
                for card in self.cards:
                    if card.is_clicked(pos) and not card.revealed and not card.matched:
                        response = self.client.reveal_card(card.id)
                        if response.get("success"):
                            if 'game_state' in response:
                                self.process_game_state(response['game_state'])
                                self.client.game_state_data = response['game_state']
                        break
        
        elif self.state == GameState.FINISHED:
            if self.back_btn.is_clicked(pos):
                self.state = GameState.MENU
                self.client.stop_polling()
                self.client.player_id = None
                self.client.room_id = None

    def draw_animated_background(self):
        self.bg_time += self.clock.get_time() / 1000.0
        
        r1 = int(30 + 15 * math.sin(self.bg_time * 0.5))
        g1 = int(30 + 15 * math.sin(self.bg_time * 0.7))
        b1 = int(50 + 20 * math.sin(self.bg_time * 0.3))
        
        r2 = int(20 + 10 * math.sin(self.bg_time * 0.4))
        g2 = int(40 + 15 * math.sin(self.bg_time * 0.6))
        b2 = int(20 + 10 * math.sin(self.bg_time * 0.8))
        
        for y in range(self.height):
            ratio = y / self.height
            r = int(r1 * (1 - ratio) + r2 * ratio)
            g = int(g1 * (1 - ratio) + g2 * ratio)
            b = int(b1 * (1 - ratio) + b2 * ratio)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (self.width, y))
        
        for i in range(20):
            particle_time = self.bg_time + i * 0.3
            x = (50 + i * 45 + math.sin(particle_time * 0.5) * 30) % self.width
            y = (100 + math.sin(particle_time * 0.3 + i) * 50) % self.height
            alpha = int(50 + 30 * math.sin(particle_time * 0.7))
            size = 2 + int(math.sin(particle_time + i) * 1)
            
            particle_surface = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(particle_surface, (255, 255, 255, alpha), (size, size), size)
            self.screen.blit(particle_surface, (x - size, y - size))

    def draw_menu(self):
        self.draw_animated_background()
        
        title_text = "Memory Card Game"
        title_main = self.font_large.render(title_text, True, (255, 255, 255))
        title_glow = self.font_large.render(title_text, True, (100, 150, 255))
        
        title_rect = title_main.get_rect(center=(self.width // 2, 120))
        glow_rect = title_glow.get_rect(center=(self.width // 2 + 2, 122))
        
        self.screen.blit(title_glow, glow_rect)
        self.screen.blit(title_main, title_rect)
        
        subtitle_alpha = int(180 + 75 * math.sin(self.bg_time * 2))
        subtitle_surface = pygame.Surface((400, 30), pygame.SRCALPHA)
        subtitle_text = self.font_small.render("Challenge your memory with friends!", True, (255, 255, 255, subtitle_alpha))
        subtitle_rect = subtitle_text.get_rect(center=(200, 15))
        subtitle_surface.blit(subtitle_text, subtitle_rect)
        self.screen.blit(subtitle_surface, (self.width // 2 - 200, 150))
        
        self.create_game_btn.draw(self.screen, self.font_medium)
        
        room_bg = pygame.Surface((320, 80), pygame.SRCALPHA)
        pygame.draw.rect(room_bg, (0, 0, 0, 100), (0, 0, 320, 80), border_radius=15)
        pygame.draw.rect(room_bg, (100, 150, 255, 150), (0, 0, 320, 80), 3, border_radius=15)
        self.screen.blit(room_bg, (340, 250 + 40))

        room_label = self.font_small.render("Room ID:", True, (200, 220, 255))
        self.screen.blit(room_label, (350, 260 + 40))

        self.room_input.draw(self.screen, self.font_small)

        self.join_game_btn.draw(self.screen, self.font_medium)
        
        instruction_y = 450
        instructions = [
            "Create a new game to select difficulty level",
            "Or enter a Room ID above and click Join Game"
        ]
        
        for i, instruction in enumerate(instructions):
            color_intensity = int(200 + 55 * math.sin(self.bg_time + i * 0.5))
            color = (color_intensity, color_intensity, color_intensity)
            instruction_surface = self.font_small.render(instruction, True, color)
            instruction_rect = instruction_surface.get_rect(center=(self.width // 2, instruction_y + i * 25))
            self.screen.blit(instruction_surface, instruction_rect)

    def draw_level_select(self):
        self.draw_animated_background()
        
        self.back_btn.draw(self.screen, self.font_small)
        
        title = self.font_large.render("Select Difficulty", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.width // 2, 120))
        self.screen.blit(title, title_rect)
        
        self.easy_level_btn.draw(self.screen, self.font_medium)
        self.normal_level_btn.draw(self.screen, self.font_medium)
        
        descriptions = [
            ("Easy Mode", ["All cards shown for 3 ", "seconds at the start", "of the game"], (150, 255, 150), 330),
            ("Normal Mode", ["No card previews", "Classic memory", "game"], (255, 150, 150), 570)
        ]

        for title_text, desc_lines, color, x_pos in descriptions:
            desc_bg = pygame.Surface((180, 120), pygame.SRCALPHA)
            pygame.draw.rect(desc_bg, (0, 0, 0, 120), (0, 0, 180, 120), border_radius=10)
            pygame.draw.rect(desc_bg, color + (100,), (0, 0, 180, 120), 2, border_radius=10)
            self.screen.blit(desc_bg, (x_pos, 290))
            
            title_surface = self.font_small.render(title_text, True, (255, 255, 255))
            self.screen.blit(title_surface, (x_pos + 10, 300))
            
            for i, line in enumerate(desc_lines):
                line_surface = self.font_small.render(line, True, color)
                self.screen.blit(line_surface, (x_pos + 10, 325 + i * 25))

    def draw_waiting(self):
        self.draw_animated_background()
        
        self.back_btn.draw(self.screen, self.font_small)
        
        waiting_scale = 1.0 + 0.1 * math.sin(self.bg_time * 3)
        title_font = pygame.font.Font(None, int(48 * waiting_scale))
        title = title_font.render("Waiting for Players", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title, title_rect)
        
        if self.client.room_id:
            room_bg = pygame.Surface((300, 60), pygame.SRCALPHA)
            pygame.draw.rect(room_bg, (0, 0, 0, 150), (0, 0, 300, 60), border_radius=15)
            pygame.draw.rect(room_bg, (100, 255, 100, 200), (0, 0, 300, 60), 3, border_radius=15)
            self.screen.blit(room_bg, (self.width // 2 - 150, 200))
            
            room_text = self.font_medium.render(f"Room ID: {self.client.room_id}", True, (255, 255, 255))
            room_rect = room_text.get_rect(center=(self.width // 2, 230))
            self.screen.blit(room_text, room_rect)
        
        if hasattr(self, 'game_state_data') and self.game_state_data:
            level = self.game_state_data.get('level', 'normal')
            level_bg = pygame.Surface((200, 30), pygame.SRCALPHA)
            pygame.draw.rect(level_bg, (100, 100, 255, 100), (0, 0, 200, 30), border_radius=10)
            self.screen.blit(level_bg, (self.width // 2 - 100, 270))
            
            level_text = self.font_small.render(f"Difficulty: {level.title()}", True, (200, 200, 255))
            level_rect = level_text.get_rect(center=(self.width // 2, 285))
            self.screen.blit(level_text, level_rect)
        
        y_offset = 320
        for i, (player_id, player_data) in enumerate(self.players.items()):
            player_bg = pygame.Surface((250, 35), pygame.SRCALPHA)
            color_alpha = int(100 + 50 * math.sin(self.bg_time + i))
            pygame.draw.rect(player_bg, (50, 150, 200, color_alpha), (0, 0, 250, 35), border_radius=8)
            self.screen.blit(player_bg, (self.width // 2 - 125, y_offset - 5))
            
            player_text = self.font_small.render(f"Player: {player_data['name']}", True, (255, 255, 255))
            player_rect = player_text.get_rect(center=(self.width // 2, y_offset + 10))
            self.screen.blit(player_text, player_rect)
            y_offset += 45
        
        status_y = 420
        if len(self.players) < 2:
            pulse = 0.8 + 0.2 * math.sin(self.bg_time * 4)
            waiting_color = (int(200 * pulse), int(200 * pulse), int(200 * pulse))
            
            instruction = self.font_small.render("Waiting for another player to join...", True, waiting_color)
            instruction_rect = instruction.get_rect(center=(self.width // 2, status_y))
            self.screen.blit(instruction, instruction_rect)
            
            share_text = self.font_small.render("Share the Room ID with a friend!", True, (150, 150, 255))
            share_rect = share_text.get_rect(center=(self.width // 2, status_y + 30))
            self.screen.blit(share_text, share_rect)
        else:
            ready_color = (100, 255, 100)
            instruction = self.font_small.render("Game will start automatically when both players are ready!", True, ready_color)
            instruction_rect = instruction.get_rect(center=(self.width // 2, status_y))
            self.screen.blit(instruction, instruction_rect)

    def draw_game(self):
        bg_r = int(20 + 10 * math.sin(self.bg_time * 0.2))
        bg_g = int(40 + 15 * math.sin(self.bg_time * 0.3))
        bg_b = int(20 + 10 * math.sin(self.bg_time * 0.25))
        self.screen.fill((bg_r, bg_g, bg_b))
        
        self.back_btn.draw(self.screen, self.font_small)
        
        title = self.font_medium.render("Memory Card Game", True, (255, 255, 255))
        title_glow = self.font_medium.render("Memory Card Game", True, (100, 200, 255))
        self.screen.blit(title_glow, (self.width // 2 - 98, 22))
        self.screen.blit(title, (self.width // 2 - 100, 20))
        
        if hasattr(self, 'game_state_data') and self.game_state_data:
            level = self.game_state_data.get('level', 'normal')
            level_bg = pygame.Surface((120, 25), pygame.SRCALPHA)
            pygame.draw.rect(level_bg, (100, 100, 255, 150), (0, 0, 120, 25), border_radius=8)
            self.screen.blit(level_bg, (740, 20))
            
            level_text = self.font_small.render(f"Level: {level.title()}", True, (200, 200, 255))
            self.screen.blit(level_text, (750, 27))
        
        x_offset = 50
        for player_id, player_data in self.players.items():
            name = player_data['name']
            score = player_data['score']
            is_turn = player_data['is_turn']
            
            if player_id == self.client.player_id:
                name += " (You)"
            
            score_width = 180
            score_bg = pygame.Surface((score_width, 35), pygame.SRCALPHA)
            
            if is_turn:
                turn_pulse = 0.7 + 0.3 * math.sin(self.bg_time * 6)
                bg_color = (int(255 * turn_pulse), int(255 * turn_pulse), 100, 150)
                border_color = (255, 255, 100)
            else:
                bg_color = (50, 50, 100, 100)
                border_color = (100, 100, 150)
            
            pygame.draw.rect(score_bg, bg_color, (0, 0, score_width, 35), border_radius=10)
            pygame.draw.rect(score_bg, border_color, (0, 0, score_width, 35), 2, border_radius=10)
            self.screen.blit(score_bg, (x_offset, 60))
            
            color = (255, 255, 100) if is_turn else (255, 255, 255)
            score_text = self.font_small.render(f"{name}: {score}", True, color)
            self.screen.blit(score_text, (x_offset + 10, 70))
            x_offset += 200
        
        if self.current_player:
            current_name = self.players.get(self.current_player, {}).get('name', 'Unknown')
            if self.current_player == self.client.player_id:
                turn_text = "Your turn!"
                color = (100, 255, 100)
                pulse = 0.8 + 0.2 * math.sin(self.bg_time * 5)
                color = (int(100 * pulse), int(255 * pulse), int(100 * pulse))
            else:
                turn_text = f" {current_name}'s turn"
                color = (255, 100, 100)
            
            turn_bg = pygame.Surface((250, 30), pygame.SRCALPHA)
            pygame.draw.rect(turn_bg, (0, 0, 0, 120), (0, 0, 250, 30), border_radius=10)
            pygame.draw.rect(turn_bg, color + (150,), (0, 0, 250, 30), 2, border_radius=10)
            self.screen.blit(turn_bg, (self.width // 2 - 125, 105))
            
            turn_surface = self.font_small.render(turn_text, True, color)
            turn_rect = turn_surface.get_rect(center=(self.width // 2, 120))
            self.screen.blit(turn_surface, turn_rect)
        
        for card in self.cards:
            card.draw(self.screen)

    def draw_finished(self):
        self.draw_animated_background()
        
        self.back_btn.draw(self.screen, self.font_small)
        
        victory_scale = 1.0 + 0.15 * math.sin(self.bg_time * 2)
        victory_font = pygame.font.Font(None, int(48 * victory_scale))
        title = victory_font.render("Game Finished!", True, (255, 255, 100))
        title_rect = title.get_rect(center=(self.width // 2, 150))
        
        title_glow = victory_font.render("Game Finished!", True, (255, 200, 0))
        glow_rect = title_glow.get_rect(center=(self.width // 2 + 3, 153))
        self.screen.blit(title_glow, glow_rect)
        self.screen.blit(title, title_rect)
        
        y_offset = 250
        scores = [(pid, data['score']) for pid, data in self.players.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        
        for i, (player_id, score) in enumerate(scores):
            name = self.players[player_id]['name']
            if player_id == self.client.player_id:
                name += " (You)"
            
            result_width = 400
            result_bg = pygame.Surface((result_width, 50), pygame.SRCALPHA)
            
            if i == 0:
                bg_color = (255, 215, 0, 150)
                border_color = (255, 255, 0)
                position = "Winner!"
                text_color = (255, 255, 100)
                sparkle_alpha = int(100 + 100 * math.sin(self.bg_time * 8))
                sparkle_color = (255, 255, 255, sparkle_alpha)
            else:
                bg_color = (100, 100, 150, 100)
                border_color = (150, 150, 200)
                position = f"Rank {i + 1}"
                text_color = (255, 255, 255)
            
            pygame.draw.rect(result_bg, bg_color, (0, 0, result_width, 50), border_radius=15)
            pygame.draw.rect(result_bg, border_color, (0, 0, result_width, 50), 3, border_radius=15)
            
            if i == 0:
                for j in range(5):
                    sparkle_x = 20 + j * 70 + int(math.sin(self.bg_time * 4 + j) * 10)
                    sparkle_y = 25 + int(math.cos(self.bg_time * 6 + j) * 5)
                    pygame.draw.circle(result_bg, sparkle_color, (sparkle_x, sparkle_y), 2)
            
            self.screen.blit(result_bg, (self.width // 2 - result_width // 2, y_offset))
            
            score_text = self.font_medium.render(f"{name}: {score} pairs - {position}", True, text_color)
            score_rect = score_text.get_rect(center=(self.width // 2, y_offset + 25))
            self.screen.blit(score_text, score_rect)
            y_offset += 70
        
        hint_alpha = int(150 + 105 * math.sin(self.bg_time * 3))
        hint_surface = pygame.Surface((350, 25), pygame.SRCALPHA)
        hint_text = self.font_small.render("Click 'Back' to return to menu and play again!", True, (255, 255, 255, hint_alpha))
        hint_rect = hint_text.get_rect(center=(175, 12))
        hint_surface.blit(hint_text, hint_rect)
        self.screen.blit(hint_surface, (self.width // 2 - 175, y_offset + 20))

    def draw_status(self):
        if self.status_message and self.status_timer > 0:
            status_alpha = min(255, self.status_timer // 10)
            status_scale = 1.0 + 0.1 * math.sin(self.bg_time * 6)
            
            status_font = pygame.font.Font(None, int(24 * status_scale))
            status_surface = status_font.render(self.status_message, True, (255, 255, 100))
            status_rect = status_surface.get_rect(center=(self.width // 2, self.height - 50))
            
            bg_width = status_rect.width + 40
            bg_height = status_rect.height + 20
            bg_rect = pygame.Rect(status_rect.centerx - bg_width // 2,
                                status_rect.centery - bg_height // 2,
                                bg_width, bg_height)
            
            glow_surface = pygame.Surface((bg_width + 20, bg_height + 20), pygame.SRCALPHA)
            pygame.draw.rect(glow_surface, (255, 255, 100, 50),
                           (0, 0, bg_width + 20, bg_height + 20), border_radius=15)
            self.screen.blit(glow_surface, (bg_rect.x - 10, bg_rect.y - 10))
            
            pygame.draw.rect(self.screen, (50, 50, 50, 200), bg_rect, border_radius=10)
            pygame.draw.rect(self.screen, (255, 255, 100), bg_rect, 2, border_radius=10)
            
            self.screen.blit(status_surface, status_rect)
            self.status_timer -= self.clock.get_time()

    def run(self):
        while self.running:
            self.handle_events()
            
            if self.client.polling and self.client.game_state_data:
                if self.client.game_state_data != self.last_processed_state:
                    self.process_game_state(self.client.game_state_data)
                    self.last_processed_state = self.client.game_state_data

            if self.state == GameState.MENU:
                self.draw_menu()
            elif self.state == GameState.LEVEL_SELECT:
                self.draw_level_select()
            elif self.state == GameState.WAITING:
                self.draw_waiting()
            elif self.state == GameState.PLAYING:
                self.draw_game()
            elif self.state == GameState.FINISHED:
                self.draw_finished()
            
            self.draw_status()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = MemoryCardGame()
    game.run()