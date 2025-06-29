import pygame
import socket
import json
import threading
import random  # Add this import for random.random()
import time
import sys
import math
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

pygame.init()

# Example: create your desired font
font = pygame.font.Font('SourGummy-VariableFont_wdth,wght.ttf', 30)

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
        
        # Animation properties
        self.flip_progress = 0.0  # 0.0 = face down, 1.0 = face up
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
        
        # Enhanced color palette with gradients
        self.colors = {
            'card_0': [(255, 120, 120), (220, 80, 80)],   # Red gradient
            'card_1': [(120, 255, 120), (80, 220, 80)],   # Green gradient
            'card_2': [(120, 120, 255), (80, 80, 220)],   # Blue gradient
            'card_3': [(255, 255, 120), (220, 220, 80)],  # Yellow gradient
            'card_4': [(255, 120, 255), (220, 80, 220)],  # Magenta gradient
            'card_5': [(120, 255, 255), (80, 220, 220)],  # Cyan gradient
            'card_6': [(255, 180, 120), (220, 140, 80)],  # Orange gradient
            'card_7': [(180, 120, 255), (140, 80, 220)],  # Purple gradient
        }
        
        # Card back gradient
        self.back_color = [(255, 210, 220), (255, 170, 190)]  # light pink gradient
    
    def update(self, card_data: Dict, dt: float):
        old_revealed = self.revealed
        old_matched = self.matched
        
        self.value = card_data.get('value')
        self.revealed = card_data.get('revealed', False)
        self.matched = card_data.get('matched', False)
        
        # Update flip animation
        if self.revealed or self.matched:
            self.target_flip = 1.0
        else:
            self.target_flip = 0.0
        
        # Smooth flip animation
        flip_speed = 8.0
        if abs(self.flip_progress - self.target_flip) > 0.01:
            if self.flip_progress < self.target_flip:
                self.flip_progress = min(1.0, self.flip_progress + flip_speed * dt)
            else:
                self.flip_progress = max(0.0, self.flip_progress - flip_speed * dt)
        
        # Bounce effect when revealed
        if self.revealed and not old_revealed:
            self.bounce_timer = 0.5
        
        if self.bounce_timer > 0:
            self.bounce_timer -= dt
            bounce_progress = 1.0 - (self.bounce_timer / 0.5)
            self.bounce_offset = math.sin(bounce_progress * math.pi * 3) * 10 * (1 - bounce_progress)
        else:
            self.bounce_offset = 0
        
        # Match celebration
        if self.matched and not old_matched:
            self.match_celebration_timer = 1.0
            self.target_scale = 1.2
        
        if self.match_celebration_timer > 0:
            self.match_celebration_timer -= dt
            if self.match_celebration_timer <= 0:
                self.target_scale = 1.0
        
        # Scale animation
        scale_speed = 5.0
        if abs(self.scale - self.target_scale) > 0.01:
            if self.scale < self.target_scale:
                self.scale = min(self.target_scale, self.scale + scale_speed * dt)
            else:
                self.scale = max(self.target_scale, self.scale - scale_speed * dt)
        
        # Shake effect for mismatched cards
        if self.shake_timer > 0:
            self.shake_timer -= dt
            shake_intensity = self.shake_timer / 0.3
            self.shake_offset_x = (random.random() - 0.5) * 10 * shake_intensity
            self.shake_offset_y = (random.random() - 0.5) * 10 * shake_intensity
        else:
            self.shake_offset_x = 0
            self.shake_offset_y = 0
        
        # Glow effect for current turn
        if self.glow_intensity > 0:
            self.glow_intensity = max(0, self.glow_intensity - dt * 2)
    
    def trigger_shake(self):
        self.shake_timer = 0.3
    
    def trigger_glow(self):
        self.glow_intensity = 1.0
    
    def draw_gradient_rect(self, surface, color1, color2, rect, corner_radius=15):
        """Draw a rounded rectangle with gradient"""
        # Create a temporary surface for the gradient
        temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        
        for y in range(rect.height):
            ratio = y / rect.height
            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            pygame.draw.line(temp_surface, (r, g, b), (0, y), (rect.width, y))
        
        # Create rounded rect mask
        mask_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(mask_surface, (255, 255, 255, 255), 
                        (0, 0, rect.width, rect.height), border_radius=corner_radius)
        
        # Apply mask to gradient
        temp_surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
        
        # Blit to main surface
        surface.blit(temp_surface, rect.topleft)
    
    def draw(self, screen):
        # Calculate animated position and size
        animated_x = self.x + self.shake_offset_x
        animated_y = self.y + self.shake_offset_y - self.bounce_offset
        
        # Calculate scaled dimensions
        scaled_width = int(self.width * self.scale)
        scaled_height = int(self.height * self.scale)
        scaled_x = animated_x + (self.width - scaled_width) // 2
        scaled_y = animated_y + (self.height - scaled_height) // 2
        
        animated_rect = pygame.Rect(scaled_x, scaled_y, scaled_width, scaled_height)
        
        # Draw glow effect
        if self.glow_intensity > 0:
            glow_surface = pygame.Surface((scaled_width + 20, scaled_height + 20), pygame.SRCALPHA)
            glow_color = (255, 255, 100, int(50 * self.glow_intensity))
            pygame.draw.rect(glow_surface, glow_color,
                           (0, 0, scaled_width + 20, scaled_height + 20), border_radius=25)
            screen.blit(glow_surface, (scaled_x - 10, scaled_y - 10))
        
        # Calculate flip effect (3D-like perspective)
        flip_scale_x = abs(math.cos(self.flip_progress * math.pi))
        if flip_scale_x < 0.1:
            flip_scale_x = 0.1
        
        flip_width = int(scaled_width * flip_scale_x)
        flip_x = scaled_x + (scaled_width - flip_width) // 2
        flip_rect = pygame.Rect(flip_x, scaled_y, flip_width, scaled_height)
        
        # Determine if we should show front or back
        show_front = self.flip_progress > 0.5
        
        if show_front and (self.revealed or self.matched):
            # Draw card front
            if self.value in self.colors:
                color1, color2 = self.colors[self.value]
            else:
                color1, color2 = (128, 128, 128), (100, 100, 100)
            
            self.draw_gradient_rect(screen, color1, color2, flip_rect, 15)
            
            # Draw border
            border_color = (255, 255, 255) if not self.matched else (0, 255, 0)
            pygame.draw.rect(screen, border_color, flip_rect, 3, border_radius=15)
            
            # Draw symbol in center
            center_x = flip_rect.centerx
            center_y = flip_rect.centery
            symbol_radius = min(20, flip_width // 4)
            
            # White circle background
            pygame.draw.circle(screen, (255, 255, 255), (center_x, center_y), symbol_radius + 5)
            pygame.draw.circle(screen, (0, 0, 0), (center_x, center_y), symbol_radius + 5, 2)
            
            # Draw value-specific symbol
            if self.value:
                symbol_color = color2  # Use darker gradient color
                pygame.draw.circle(screen, symbol_color, (center_x, center_y), symbol_radius)
            
            # Match checkmark
            if self.matched:
                pygame.draw.lines(screen, (0, 200, 0), False, 
                                [(center_x - 12, center_y), 
                                 (center_x - 6, center_y + 6), 
                                 (center_x + 12, center_y - 6)], 4)
        else:
            # Draw card back
            self.draw_gradient_rect(screen, self.back_color[0], self.back_color[1], flip_rect, 15)
            
            # Draw border
            pygame.draw.rect(screen, (100, 100, 255), flip_rect, 3, border_radius=15)
            
            # Draw decorative pattern on back
            center_x = flip_rect.centerx
            center_y = flip_rect.centery
            
            # Diamond pattern
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
                 color=(180, 70, 136), hover_color=None, text_color=(255, 255, 255),
                 font_path='SourGummy-VariableFont_wdth,wght.ttf', font_size=28):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = hover_color or (
            max(0, color[0] - 20),
            max(0, color[1] - 20),
            max(0, color[2] - 20)
        )
        self.text_color = text_color
        self.is_hovered = False
        self.scale = 1.0
        self.target_scale = 1.0

        # NEW: load font
        self.font = pygame.font.Font(font_path, font_size)

    def update(self, mouse_pos: Tuple[int, int], dt: float):
        was_hovered = self.is_hovered
        self.is_hovered = self.rect.collidepoint(mouse_pos)

        if self.is_hovered and not was_hovered:
            self.target_scale = 1.05
        elif not self.is_hovered and was_hovered:
            self.target_scale = 1.0

        # Smooth scale animation
        scale_speed = 8.0
        if abs(self.scale - self.target_scale) > 0.01:
            if self.scale < self.target_scale:
                self.scale = min(self.target_scale, self.scale + scale_speed * dt)
            else:
                self.scale = max(self.target_scale, self.scale - scale_speed * dt)

    def draw(self, screen):
        scaled_width = int(self.rect.width * self.scale)
        scaled_height = int(self.rect.height * self.scale)
        scaled_x = self.rect.x + (self.rect.width - scaled_width) // 2
        scaled_y = self.rect.y + (self.rect.height - scaled_height) // 2
        scaled_rect = pygame.Rect(scaled_x, scaled_y, scaled_width, scaled_height)

        current_color = self.hover_color if self.is_hovered else self.color
        darker_color = (138, 39, 128)
        # darker_colour_GR = (2, 150, 125)
        self.draw_gradient_rect(screen, current_color, darker_color, scaled_rect)

        border_color = (180, 180, 180) if self.is_hovered else (148, 62, 96)
        pygame.draw.rect(screen, border_color, scaled_rect, 2, border_radius=10)

        avg_color = sum(current_color) / 3
        text_color = (0, 0, 0) if avg_color > 160 else (255, 196, 220)

        text_surface = self.font.render(self.text, True, text_color)
        text_rect = text_surface.get_rect(center=scaled_rect.center)
        screen.blit(text_surface, text_rect)

    def draw_gradient_rect(self, surface, color1, color2, rect):
        temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        for y in range(rect.height):
            ratio = y / rect.height
            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            pygame.draw.line(temp_surface, (r, g, b), (0, y), (rect.width, y))
        mask_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(mask_surface, (255, 255, 255, 255),
                         (0, 0, rect.width, rect.height), border_radius=10)
        temp_surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(temp_surface, rect.topleft)

    def is_clicked(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    
    
class InputBox:
    def __init__(self, x: int, y: int, width: int, height: int, placeholder: str = ""):
        self.rect = pygame.Rect(x, y, width, height)
        self.color_inactive = (183, 126, 237)
        self.color_active = (199, 153, 242)
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
                    if len(self.text) < 10:  # Limit input length
                        self.text += event.unicode
    
    def update(self, dt: float):
        self.cursor_timer += dt
    
    def draw(self, screen, font):
        # Draw input box with rounded corners
        pygame.draw.rect(screen, self.color, self.rect, border_radius=8)
        pygame.draw.rect(screen, (200, 200, 200), self.rect, 2, border_radius=8)
        
        # Draw text or placeholder
        display_text = self.text if self.text else self.placeholder
        text_color = (105, 48, 156) if self.text else (105, 48, 156)
        text_surface = font.render(display_text, True, text_color)
        text_y = self.rect.y + (self.rect.height - text_surface.get_height()) // 2
        screen.blit(text_surface, (self.rect.x + 10, text_y))
        
        # Draw cursor when active
        if self.active and self.cursor_timer % 1.0 < 0.5:
            cursor_x = self.rect.x + 10 + font.size(self.text)[0]
            cursor_y = self.rect.y + 5
            pygame.draw.line(screen, (255, 255, 255), 
                           (cursor_x, cursor_y), (cursor_x, cursor_y + self.rect.height - 10), 2)

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
        
        self.font_large = pygame.font.Font('SourGummy-VariableFont_wdth,wght.ttf', 48)
        self.font_medium = pygame.font.Font('SourGummy-VariableFont_wdth,wght.ttf', 36)
        self.font_small = pygame.font.Font('SourGummy-VariableFont_wdth,wght.ttf', 24)
        
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
        
        # Background animation
        self.bg_time = 0
        
    def create_ui_elements(self):
        self.create_game_btn = Button(350, 250, 300, 60, "Create New Game", (240, 34, 171),
            font_path='SourGummy-VariableFont_wdth,wght.ttf', font_size=28)

        self.room_input = InputBox(350, 410, 300, 40, "Enter Room ID")

        self.join_room_btn = Button(350, 470, 300, 40, "Join Room", (103, 2, 163),
            font_path='SourGummy-VariableFont_wdth,wght.ttf', font_size=24)

        self.start_btn = Button(400, 500, 200, 50, "Start Game", (200, 255, 200),
            font_path='SourGummy-VariableFont_wdth,wght.ttf', font_size=26)

        self.back_btn = Button(50, 50, 100, 40, "Back", (240, 34, 171),
            font_path='SourGummy-VariableFont_wdth,wght.ttf', font_size=20)


        
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
                    # Trigger celebration on matched cards
                    for card in self.cards:
                        if card.revealed and card.matched:
                            card.match_celebration_timer = 1.0
                else:
                    self.show_status("No match. Turn switches.")
                    # Trigger shake on mismatched cards
                    for card in self.cards:
                        if card.revealed and not card.matched:
                            card.trigger_shake()
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
                self.cards[i].update(card_data, self.clock.get_time() / 1000.0)
        
        # Trigger glow effect for current player's turn
        if self.current_player == self.player_id:
            for card in self.cards:
                if not card.revealed and not card.matched:
                    card.trigger_glow()
        
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
        self.join_room_btn.update(mouse_pos, dt)
        self.start_btn.update(mouse_pos, dt)
        self.back_btn.update(mouse_pos, dt)
        
        if self.state == GameState.MENU:
            self.room_input.update(dt)
        
        # Update card animations
        for card in self.cards:
            card.update({'value': card.value, 'revealed': card.revealed, 'matched': card.matched}, dt)
    
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
    
    def draw_animated_background(self):
        self.bg_time += self.clock.get_time() / 1000.0

        # Define your 3 pastel target colours
        pink = (255, 200, 220)
        purple = (220, 180, 255)
        yellow = (255, 245, 200)

        # Animate blend factors
        t = (math.sin(self.bg_time * 0.5) + 1) / 2  # value between 0–1
        u = (math.cos(self.bg_time * 0.3) + 1) / 2

        # Blend between pink & purple, then blend result with yellow
        blended1 = (
            int(pink[0] * (1 - t) + purple[0] * t),
            int(pink[1] * (1 - t) + purple[1] * t),
            int(pink[2] * (1 - t) + purple[2] * t),
        )
        blended2 = (
            int(blended1[0] * (1 - u) + yellow[0] * u),
            int(blended1[1] * (1 - u) + yellow[1] * u),
            int(blended1[2] * (1 - u) + yellow[2] * u),
        )

        # Draw vertical gradient from blended2 (top) to pink (bottom)
        for y in range(self.height):
            ratio = y / self.height
            r = int(blended2[0] * (1 - ratio) + pink[0] * ratio)
            g = int(blended2[1] * (1 - ratio) + pink[1] * ratio)
            b = int(blended2[2] * (1 - ratio) + pink[2] * ratio)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (self.width, y))



    def draw_menu(self):
        # Title with glow effect
        title_text = "Memory Card Game"
        title_surface = self.font_large.render(title_text, True, (255, 100, 150))  # pinkish title
        title_rect = title_surface.get_rect(center=(self.width // 2, 150))
        
        # Draw title glow
        glow_surface = self.font_large.render(title_text, True, (255, 200, 220))
        for offset in [(2, 2), (-2, 2), (2, -2), (-2, -2)]:
            glow_rect = title_rect.copy()
            glow_rect.x += offset[0]
            glow_rect.y += offset[1]
            self.screen.blit(glow_surface, glow_rect)
        
        self.screen.blit(title_surface, title_rect)
        
        # Draw buttons
        self.create_game_btn.draw(self.screen)
        
        # Join room section
        join_text = self.font_medium.render("Join Existing Room:", True, (147, 72, 156))
        join_rect = join_text.get_rect(center=(self.width // 2, 370))
        self.screen.blit(join_text, join_rect)
        
        self.room_input.draw(self.screen, self.font_small)
        self.join_room_btn.draw(self.screen)
        
        # Instructions
        instructions = [
            "Create a new room or join an existing one",
            "Share the room ID with friends to play together",
            "Match pairs of cards to win!"
        ]
        
        for i, instruction in enumerate(instructions):
            text = self.font_small.render(instruction, True, (245, 140, 175))
            text_rect = text.get_rect(center=(self.width // 2, 550 + i * 25))
            self.screen.blit(text, text_rect)
    
    def draw_waiting_room(self):
        # Title
        title_text = "Waiting Room"
        title_surface = self.font_large.render(title_text, True, (201, 54, 113))
        title_rect = title_surface.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title_surface, title_rect)
        
        # Room ID
        if self.room_id:
            room_text = f"Room ID: {self.room_id}"
            room_surface = self.font_medium.render(room_text, True, (144, 84, 209))
            room_rect = room_surface.get_rect(center=(self.width // 2, 200))
            self.screen.blit(room_surface, room_rect)
        
        # Player list
        players_text = "Players:"
        players_surface = self.font_medium.render(players_text, True, (240, 108, 179))
        players_rect = players_surface.get_rect(center=(self.width // 2, 280))
        self.screen.blit(players_surface, players_rect)
        
        y_offset = 320
        for player_id, player_data in self.players.items():
            player_name = player_data.get('name', f'Player {player_id}')
            color = (164, 99, 207) if player_id == self.player_id else (200, 200, 200)
            player_surface = self.font_small.render(f"• {player_name}", True, color)
            player_rect = player_surface.get_rect(center=(self.width // 2, y_offset))
            self.screen.blit(player_surface, player_rect)
            y_offset += 30
        
        # Waiting message
        waiting_text = "Waiting for more players..."
        waiting_surface = self.font_small.render(waiting_text, True, (160, 111, 173))
        waiting_rect = waiting_surface.get_rect(center=(self.width // 2, 450))
        self.screen.blit(waiting_surface, waiting_rect)
        
        # Back button
        self.back_btn.draw(self.screen)
    
    def draw_game(self):
        # Draw cards
        for card in self.cards:
            card.draw(self.screen)
        
        # Draw game info
        info_y = 50
        
        # Current player indicator
        if self.current_player:
            current_player_name = self.players.get(self.current_player, {}).get('name', f'Player {self.current_player}')
            current_text = f"Current Turn: {current_player_name}"
            color = (240, 43, 148) if self.current_player == self.player_id else (168, 94, 134)
            current_surface = self.font_medium.render(current_text, True, color)
            self.screen.blit(current_surface, (330, 22))
        
        # Score display
        score_y = info_y + 40
        for i, (player_id, player_data) in enumerate(self.players.items()):
            player_name = player_data.get('name', f'Player {player_id}')
            score = player_data.get('score', 0)
            color = (255, 8, 189) if player_id == self.player_id else (160, 111, 173)
            score_text = f"{player_name}: {score}"
            score_surface = self.font_small.render(score_text, True, color)
            self.screen.blit(score_surface, (60, score_y + i * 25))
        
        # Back button
        self.back_btn.draw(self.screen)
        
        # Your turn indicator
        if self.current_player == self.player_id:
            turn_text = "Your Turn - Click a card!"
            turn_surface = self.font_medium.render(turn_text, True, (144, 84, 209))
            turn_rect = turn_surface.get_rect(center=(self.width // 2, 100))

            
            # Pulsing effect
            pulse = abs(math.sin(self.bg_time * 3))
            glow_color = (144, 84, 209, int(100 * pulse))
            glow_surface = pygame.Surface((turn_rect.width + 20, turn_rect.height + 10), pygame.SRCALPHA)
            pygame.draw.rect(glow_surface, glow_color, glow_surface.get_rect(), border_radius=10)
            self.screen.blit(glow_surface, (turn_rect.x - 10, turn_rect.y - 5))
            
            self.screen.blit(turn_surface, turn_rect)
    
    def draw_finished(self):
        # Title
        title_text = "Game Finished!"
        title_surface = self.font_large.render(title_text, True, (255, 255, 100))
        title_rect = title_surface.get_rect(center=(self.width // 2, 200))
        self.screen.blit(title_surface, title_rect)
        
        # Winner announcement
        if self.game_state_data:
            winner_id = self.game_state_data.get('winner')
            if winner_id:
                winner_name = self.players.get(winner_id, {}).get('name', f'Player {winner_id}')
                winner_text = f"Winner: {winner_name}!"
                color = (100, 255, 100) if winner_id == self.player_id else (255, 255, 255)
                winner_surface = self.font_medium.render(winner_text, True, color)
                winner_rect = winner_surface.get_rect(center=(self.width // 2, 280))
                self.screen.blit(winner_surface, winner_rect)
        
        # Final scores
        scores_text = "Final Scores:"
        scores_surface = self.font_medium.render(scores_text, True, (255, 255, 255))
        scores_rect = scores_surface.get_rect(center=(self.width // 2, 350))
        self.screen.blit(scores_surface, scores_rect)
        
        score_y = 390
        sorted_players = sorted(self.players.items(), 
                               key=lambda x: x[1].get('score', 0), reverse=True)
        
        for i, (player_id, player_data) in enumerate(sorted_players):
            player_name = player_data.get('name', f'Player {player_id}')
            score = player_data.get('score', 0)
            
            # Different colors for ranking
            if i == 0:
                color = (255, 215, 0)  # Gold
            elif i == 1:
                color = (192, 192, 192)  # Silver
            elif i == 2:
                color = (205, 127, 50)  # Bronze
            else:
                color = (200, 200, 200)
            
            rank_text = f"{i+1}. {player_name}: {score} points"
            rank_surface = self.font_small.render(rank_text, True, color)
            rank_rect = rank_surface.get_rect(center=(self.width // 2, score_y + i * 30))
            self.screen.blit(rank_surface, rank_rect)
        
        # Back button
        self.back_btn.draw(self.screen)
    
    def draw_status_message(self):
        if self.status_timer > 0:
            self.status_timer -= self.clock.get_time()
            
            # Create status message box
            status_surface = self.font_medium.render(self.status_message, True, (255, 255, 255))
            status_rect = status_surface.get_rect(center=(self.width // 2, 100))
            
            # Background box
            bg_rect = status_rect.inflate(40, 20)
            bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(bg_surface, (0, 0, 0, 180), bg_surface.get_rect(), border_radius=10)
            pygame.draw.rect(bg_surface, (255, 255, 255), bg_surface.get_rect(), 2, border_radius=10)
            
            self.screen.blit(bg_surface, bg_rect)
            self.screen.blit(status_surface, status_rect)
    
    def run(self):
        while self.running:
            self.handle_events()
            self.handle_server_messages()
            
            # Draw everything
            self.draw_animated_background()
            
            if self.state == GameState.MENU:
                self.draw_menu()
            elif self.state == GameState.WAITING:
                self.draw_waiting_room()
            elif self.state == GameState.PLAYING:
                self.draw_game()
            elif self.state == GameState.FINISHED:
                self.draw_finished()
            
            self.draw_status_message()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        # Cleanup
        if self.client.connected:
            self.client.disconnect()
        pygame.quit()
        sys.exit()

# Add missing import
import random

if __name__ == "__main__":
    game = MemoryCardGame()
    game.run()