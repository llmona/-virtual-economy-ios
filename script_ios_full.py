import pygame
import random
import sys
import math
import json
import os
import time
from pathlib import Path

# iOS/desktop compatibility -------------------------------------------------
# The old version used ctypes.windll solely to hide the Windows console.
# There is no reason to do that in a game build, and windll is Windows-only.
IS_IOS = (sys.platform == "ios" or os.environ.get("PYGAME_IOS") == "1")

pygame.init()
try:
    pygame.mixer.init()
    AUDIO_AVAILABLE = True
except pygame.error:
    # Audio may be unavailable on some iOS/device configurations.
    AUDIO_AVAILABLE = False

# ЕДИНЫЙ ЛОГИЧЕСКИЙ РАЗМЕР ДЛЯ ВСЕХ СЦЕН
WIDTH, HEIGHT = 1000, 700

def set_game_mode(width=WIDTH, height=HEIGHT, resizable=True):
    """Create the display in a way that works both on desktop and iOS."""
    if IS_IOS:
        # Keep the game's 1000x700 logical coordinate system while SDL scales
        # it to the device screen. iOS apps should not rely on a window frame.
        return pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
    flags = pygame.SCALED | (pygame.RESIZABLE if resizable else 0)
    return pygame.display.set_mode((width, height), flags)

screen = set_game_mode()
if not IS_IOS:
    pygame.display.set_caption("Virtual Economy Game")
clock = pygame.time.Clock()

def get_save_path():
    """Return a persistent, sandbox-safe save location on iOS."""
    if IS_IOS:
        # The iOS app's HOME is inside its sandbox. Documents is persistent
        # and is suitable for user-created game saves.
        save_dir = Path.home() / "Documents" / "VirtualEconomyGame"
    else:
        save_dir = Path.home() / ".virtual_economy_game"
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir / "save.json"


def get_input_events():
    """Normalize iPhone/iPad touch input to the mouse-style input used by the game.

    The game keeps a 1000x700 logical coordinate system. Pygame/SDL scales that
    logical surface to the actual iPhone display, while this adapter converts
    normalized FINGER events back into logical coordinates.
    """
    events = []
    touch_state = getattr(get_input_events, "_touch", None)
    if touch_state is None:
        touch_state = {"active": False, "start": (0, 0), "last": (0, 0), "moved": False}
        get_input_events._touch = touch_state

    for event in pygame.event.get():
        events.append(event)
        if event.type not in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            continue

        # FINGER coordinates are normalized 0..1. Convert to the game's logical
        # coordinate space rather than the physical Retina pixel dimensions.
        pos = (int(max(0.0, min(1.0, event.x)) * WIDTH),
               int(max(0.0, min(1.0, event.y)) * HEIGHT))

        if event.type == pygame.FINGERDOWN:
            touch_state.update(active=True, start=pos, last=pos, moved=False)
            events.append(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}))

        elif event.type == pygame.FINGERMOTION:
            last = touch_state["last"]
            dx, dy = pos[0] - last[0], pos[1] - last[1]
            if abs(pos[0] - touch_state["start"][0]) + abs(pos[1] - touch_state["start"][1]) > 12:
                touch_state["moved"] = True
            touch_state["last"] = pos
            events.append(pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": pos, "rel": (dx, dy), "buttons": (1, 0, 0)}))

            # A vertical finger drag also acts as a scroll wheel. This makes
            # the rules and boutique screens usable without a mouse wheel.
            if abs(dy) > 1:
                events.append(pygame.event.Event(
                    pygame.MOUSEWHEEL, {"y": int(-dy / 8), "x": 0, "flipped": False}))

        elif event.type == pygame.FINGERUP:
            touch_state["last"] = pos
            events.append(pygame.event.Event(
                pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1}))
            touch_state["active"] = False

    return events


def get_pointer_pos():
    """Mouse position on desktop; last touch position on iOS."""
    if IS_IOS:
        touch = getattr(get_input_events, "_touch", None)
        if touch and touch.get("active"):
            return touch.get("last", (WIDTH // 2, HEIGHT // 2))
    return pygame.mouse.get_pos()

# Цвета (общие для всех)
WHITE = (255, 255, 255)
BLACK = (5, 5, 5)
GRAY = (50, 50, 50)
LIGHT_GRAY = (180, 180, 180)
DARK_GRAY = (20, 20, 20)
GREEN = (0, 255, 0)
FOREST_GREEN = (0, 70, 0)
LIGHT_GREEN = (144, 238, 144)
RED = (255, 60, 60)
BRIGHT_RED = (255, 100, 100)
DARK_RED = (160, 20, 20)
GOLD = (255, 215, 0)
BRIGHT_GOLD = (255, 235, 100)
DARK_GOLD = (184, 134, 11)
BLUE = (52, 152, 219)
DARK_BLUE = (20, 20, 120)
PURPLE = (155, 89, 182)
BROWN = (139, 69, 19)
EMERALD = (46, 204, 113)
BRIGHT_EMERALD = (100, 255, 150)
TURQUOISE = (26, 188, 156)

def draw_gradient_background(surface, top_color, bottom_color):
    width, height = surface.get_size()
    for i in range(height):
        # Вычисляем плавный переход цвета
        factor = i / height
        r = int(top_color[0] * (1 - factor) + bottom_color[0] * factor)
        g = int(top_color[1] * (1 - factor) + bottom_color[1] * factor)
        b = int(top_color[2] * (1 - factor) + bottom_color[2] * factor)
        pygame.draw.line(surface, (r, g, b), (0, i), (width, i))

# Функция для форматирования больших чисел (с пробелами)
def format_money(amount):
    return f"{int(amount):,}".replace(",", " ")

class Button:
    def __init__(self, x, y, w, h, text, color, action=None, text_color=WHITE, corner_radius=15):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.action = action
        self.text_color = text_color
        self.corner_radius = corner_radius
        self.hover = False
        self.enabled = True
        self.highlight = False
        self.pulse = 0
        self.click_animation = 0
        self.shadow_offset = 6

    def draw(self, surface):
        if not self.enabled:
            main_color, t_color, border_color = (60, 60, 60), (120, 120, 120), (80, 80, 80)
        elif self.hover:
            main_color = tuple(min(c + 40, 255) for c in self.color)
            t_color, border_color = WHITE, GOLD
        else:
            main_color, t_color, border_color = self.color, self.text_color, DARK_GOLD

        if self.click_animation > 0:
            self.click_animation -= 1
            self.shadow_offset = 2
        else:
            self.shadow_offset = 6

        shadow_rect = self.rect.copy()
        shadow_rect.x += self.shadow_offset
        shadow_rect.y += self.shadow_offset
        pygame.draw.rect(surface, (0, 0, 0, 120), shadow_rect, border_radius=self.corner_radius)

        for i in range(self.rect.height):
            factor = 1 - (i / self.rect.height) * 0.3
            c = tuple(int(col * factor) for col in main_color)
            pygame.draw.line(surface, c, (self.rect.x, self.rect.y + i), (self.rect.x + self.rect.w, self.rect.y + i))

        pygame.draw.rect(surface, border_color, self.rect, 3, border_radius=self.corner_radius)
        text_surf = get_font(22, bold=True).render(self.text, True, t_color)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))

    def check_hover(self, pos):
        self.hover = self.rect.collidepoint(pos)
        return self.hover

    def update(self, pos):
        return self.check_hover(pos)

    def click(self, pos):
        # Invisible touch padding makes existing desktop-sized buttons easier to tap.
        hit_rect = self.rect.inflate(18, 18) if IS_IOS else self.rect
        if hit_rect.collidepoint(pos):
            self.click_animation = 5
            if self.action: self.action()
            return True
        return False

    def check_click(self, pos):
        return self.click(pos)

# ==============================================================================
# 2. ЭКОНОМИКА И СОХРАНЕНИЯ (Бывший economy.py)
# ==============================================================================
class Economy:
    def __init__(self):
        self.rubles = 1000
        self.usd = 0.0
        self.eur = 0.0
        self.usd_rate = 90.0
        self.eur_rate = 100.0
        self.usd_history = [90.0] * 20
        self.eur_history = [100.0] * 20

        self.dice_prices = {
            "Common": 1, "Uncommon": 3, "Rare": 15, "Epic": 50,
            "Mythic": 100, "Legendary": 500, "Divine": 17102026
        }
        self.dice_chances = {
            "Common": 20, "Uncommon": 15, "Rare": 15, "Epic": 15,
            "Mythic": 15, "Legendary": 19.5, "Divine": 0.5
        }
        self.dice_inventory = []

        # --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ БУТИКА И ИМПЕРИИ ---
        self.owned_items = []
        self.business_level = 0
        self.passive_income = 0
        # ---------------------------------------------

        self.game_day = 1
        self.tsar_dice = []
        self.tsar_last_day = 0

        self.save_file = str(get_save_path())
        self.load_game()
        self.check_tsar_update()

    def check_tsar_update(self):
        if self.game_day > self.tsar_last_day or not self.tsar_dice:
            all_dice = list(self.dice_prices.keys())
            new_dice = random.sample(all_dice, 4)
            if self.tsar_dice:
                while True:
                    if len(set(new_dice) & set(self.tsar_dice)) <= 2: break
                    new_dice = random.sample(all_dice, 4)
            self.tsar_dice = new_dice
            self.tsar_last_day = self.game_day
            self.save_game()

    def save_game(self):
        data = {
            "rubles": self.rubles, "usd": self.usd, "eur": self.eur,
            "usd_rate": self.usd_rate, "eur_rate": self.eur_rate,
            "usd_history": self.usd_history, "eur_history": self.eur_history,
            "dice_inventory": self.dice_inventory, "game_day": self.game_day,
            "tsar_dice": self.tsar_dice, "tsar_last_day": self.tsar_last_day,
            "owned_items": self.owned_items,
            "business_level": self.business_level,
            "passive_income": self.passive_income
        }
        save_path = Path(self.save_file)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = save_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, save_path)
        except OSError as e:
            # Do not crash the game if the filesystem is temporarily unavailable.
            print(f"Ошибка сохранения: {e}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def load_game(self):
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.rubles = data.get("rubles", 1000)
                    self.usd = data.get("usd", 0.0)
                    self.eur = data.get("eur", 0.0)
                    self.usd_rate = data.get("usd_rate", 90.0)
                    self.eur_rate = data.get("eur_rate", 100.0)
                    self.usd_history = data.get("usd_history", [90.0] * 20)
                    self.eur_history = data.get("eur_history", [100.0] * 20)
                    self.dice_inventory = data.get("dice_inventory", [])
                    self.game_day = data.get("game_day", 1)
                    self.tsar_dice = data.get("tsar_dice", [])
                    self.tsar_last_day = data.get("tsar_last_day", 0)

                    # Загружаем новые переменные
                    self.owned_items = data.get("owned_items", [])
                    self.business_level = data.get("business_level", 0)
                    self.passive_income = data.get("passive_income", 0)
            except Exception as e:
                print(f"Ошибка загрузки: {e}")

    def add_rubles(self, amount):
        self.rubles += amount;
        self.save_game()

    def spend_rubles(self, amount):
        if self.rubles >= amount: self.rubles -= amount; self.save_game(); return True
        return False

    def update_market(self):
        self.game_day += 1
        self.usd_rate = round(self.usd_rate * random.uniform(0.95, 1.05), 2)
        self.eur_rate = round(self.eur_rate * random.uniform(0.95, 1.05), 2)
        self.usd_history.append(self.usd_rate)
        self.eur_history.append(self.eur_rate)
        if len(self.usd_history) > 30: self.usd_history.pop(0)
        if len(self.eur_history) > 30: self.eur_history.pop(0)
        self.check_tsar_update()
        self.save_game()

    def convert_rub_to_usd(self, amount):
        if self.spend_rubles(amount): self.usd += amount / self.usd_rate; self.save_game(); return True
        return False

    def convert_rub_to_eur(self, amount):
        if self.spend_rubles(amount): self.eur += amount / self.eur_rate; self.save_game(); return True
        return False

    def sell_usd(self, amount):
        if self.usd >= amount: self.usd -= amount; self.rubles += amount * self.usd_rate; self.save_game(); return True
        return False

    def sell_eur(self, amount):
        if self.eur >= amount: self.eur -= amount; self.rubles += amount * self.eur_rate; self.save_game(); return True
        return False

    def buy_dice(self, dice_name):
        price = self.dice_prices.get(dice_name, 0)
        if self.spend_rubles(price): self.dice_inventory.append(dice_name); self.save_game(); return True
        return False

    def sell_dice(self, dice_name):
        if dice_name in self.dice_inventory:
            self.dice_inventory.remove(dice_name)
            self.add_rubles(self.dice_prices.get(dice_name, 0))
            return True
        return False

    def reset_all_but_divine(self):
        # Считаем, сколько у нас Divine
        divine_count = self.dice_inventory.count("Divine")

        # Сбрасываем ВСЁ
        self.rubles = 1000  # Оставляем 1000 рублей для старта, иначе игра сломается
        self.usd = 0.0
        self.eur = 0.0
        self.passive_income = 0
        self.business_level = 0
        self.owned_items = []

        # Оставляем только Divine
        self.dice_inventory = ["Divine"] * divine_count

        # Сбрасываем дни
        self.game_day = 1
        self.check_tsar_update()
        self.save_game()

economy = Economy()

# ==============================================================================
# 3. ОБЩИЕ UI ЭЛЕМЕНТЫ (Шрифты, Ползунок)
# ==============================================================================
font_cache = {}


def get_font(size, bold=False, italic=False):
    key = (size, bold, italic)
    if key in font_cache: return font_cache[key]
    font_names = ['Arial', 'Segoe UI', 'DejaVu Sans', 'FreeSans', 'Noto Sans']
    for font_name in font_names:
        try:
            if bold and italic:
                font = pygame.font.SysFont(font_name, size, bold=True, italic=True)
            elif bold:
                font = pygame.font.SysFont(font_name, size, bold=True)
            elif italic:
                font = pygame.font.SysFont(font_name, size, italic=True)
            else:
                font = pygame.font.SysFont(font_name, size)
            font_cache[key] = font
            return font
        except:
            continue
    return pygame.font.Font(None, size)


class Slider:
    def __init__(self, x, y, w, h, min_val, max_val, initial_val, color=GOLD):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.val = initial_val
        self.dragging = False
        self.color = color  # <--- ДОБАВЛЕНА ЭТА СТРОКА

    def update_max(self, new_max):
        self.max_val = max(self.min_val, new_max)
        if self.val > self.max_val:
            self.val = self.max_val
        elif self.val < self.min_val:
            self.val = self.min_val

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.inflate(40 if IS_IOS else 20, 40 if IS_IOS else 20).collidepoint(event.pos):
                self.dragging = True
                self._update_val(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_val(event.pos[0])
            return True
        return False

    def _update_val(self, mouse_x):
        if self.max_val <= self.min_val:
            self.val = self.min_val
            return
        rel_x = max(0, min(mouse_x - self.rect.x, self.rect.w))
        self.val = int(self.min_val + (rel_x / self.rect.w) * (self.max_val - self.min_val))

    def draw(self, surface):
        pygame.draw.rect(surface, (60, 60, 60), self.rect, border_radius=self.rect.h // 2)
        fill_w = ((self.val - self.min_val) / (self.max_val - self.min_val)) * self.rect.w if self.max_val > self.min_val else 0
        pygame.draw.rect(surface, self.color, (self.rect.x, self.rect.y, fill_w, self.rect.h), border_radius=self.rect.h // 2)
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(surface, WHITE, (int(knob_x), self.rect.centery), self.rect.h + 2)
        pygame.draw.circle(surface, self.color, (int(knob_x), self.rect.centery), self.rect.h - 2)


# ==============================================================================
# 4. ИГРА "ЛЕХА" (Бывший leha.py)
# ==============================================================================
class LehaGame:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("Депчик: Для Лехи")
        self.clock = pygame.time.Clock()
        self.running = True
        self.slider = Slider(300, 500, 400, 20, 0, max(1, int(economy.rubles)), 100)
        self.multiplier = 2.0
        self.is_spinning = False
        self.current_bet = 0
        self.spin_angle = 0;
        self.spin_timer = 0;
        self.start_spin_angle = 0;
        self.target_spin_angle = 0
        self.win = False
        self.result_text = "";
        self.result_timer = 0;
        self.result_color = WHITE
        self.font_main = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 20)

    def get_chance(self):
        return max(1, min(99, int(100 / self.multiplier)))

    def handle_click(self, pos):
        if self.is_spinning: return
        if pygame.Rect(20, 20, 120, 50).collidepoint(pos): self.running = False; return
        multipliers = [(1.5, 350), (2.0, 450), (3.0, 550), (5.0, 650), (10.0, 750)]
        for mult, x in multipliers:
            if pygame.Rect(x - 40, 400, 80, 40).collidepoint(pos): self.multiplier = mult; self.result_text = ""
        if pygame.Rect(400, 570, 200, 60).collidepoint(pos): self.start_spin()

    def start_spin(self):
        bet = self.slider.val
        if economy.rubles >= bet and bet > 0:
            self.current_bet = bet
            economy.spend_rubles(bet)
            self.is_spinning = True;
            self.spin_timer = 0;
            self.result_text = "Крутим...";
            self.result_color = WHITE
            chance = self.get_chance();
            self.win = random.random() * 100 < chance
            chance_angle = chance * 3.6
            target = random.uniform(-90 + 5, -90 + chance_angle - 5) if self.win else random.uniform(
                -90 + chance_angle + 5, 270 - 5)
            target = target % 360;
            current = self.spin_angle % 360;
            diff = (target - current) % 360
            self.start_spin_angle = self.spin_angle;
            self.target_spin_angle = self.spin_angle + 360 * 5 + diff
        else:
            self.result_text = "Недостаточно средств!" if bet > 0 else "Ставка не может быть 0!"
            self.result_color = RED;
            self.result_timer = 60

    def update(self):
        if self.is_spinning:
            self.spin_timer += 1;
            progress = self.spin_timer / 120.0
            if progress >= 1.0:
                self.spin_angle = self.target_spin_angle;
                self.is_spinning = False
                if self.win:
                    win_amount = int(self.current_bet * self.multiplier)
                    economy.add_rubles(win_amount)
                    self.result_text = f"ПОБЕДА! +{win_amount} RUB";
                    self.result_color = GREEN
                else:
                    self.result_text = f"ПРОИГРЫШ... -{self.current_bet} RUB";
                    self.result_color = RED
                self.result_timer = 120
            else:
                ease = 1 - (1 - progress) ** 3
                self.spin_angle = self.start_spin_angle + (self.target_spin_angle - self.start_spin_angle) * ease
        if self.result_timer > 0: self.result_timer -= 1

    def draw(self):
        draw_gradient_background(self.screen, (30, 20, 40), (10, 10, 15))
        self.slider.update_max(int(economy.rubles))
        self.screen.blit(self.font_main.render(f"Баланс: {int(economy.rubles)} RUB", True, WHITE), (20, 20))
        pygame.draw.rect(self.screen, GRAY, (20, 70, 120, 50), border_radius=10)
        self.screen.blit(self.font_small.render("НАЗАД", True, WHITE), (50, 85))

        center = (self.width // 2, 250);
        radius = 120;
        chance = self.get_chance()
        pygame.draw.circle(self.screen, (40, 40, 50), center, radius, 25)
        start_angle = math.pi / 2;
        end_angle = start_angle - (chance / 100) * 2 * math.pi
        if chance > 0:
            pygame.draw.arc(self.screen, GREEN,
                            pygame.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2), end_angle,
                            start_angle, 25)
        self.screen.blit(self.font_main.render(f"{chance}%", True, WHITE),
                         self.font_main.render(f"{chance}%", True, WHITE).get_rect(center=center))

        arrow_angle = math.radians(-self.spin_angle)
        tip_x, tip_y = center[0] + math.cos(arrow_angle) * 140, center[1] + math.sin(arrow_angle) * 140
        base1_x, base1_y = center[0] + math.cos(arrow_angle - 0.15) * 110, center[1] + math.sin(
            arrow_angle - 0.15) * 110
        base2_x, base2_y = center[0] + math.cos(arrow_angle + 0.15) * 110, center[1] + math.sin(
            arrow_angle + 0.15) * 110
        pygame.draw.polygon(self.screen, GOLD, [(tip_x, tip_y), (base1_x, base1_y), (base2_x, base2_y)])
        pygame.draw.circle(self.screen, (20, 20, 25), center, 20);
        pygame.draw.circle(self.screen, GOLD, center, 20, 3)

        multipliers = [(1.5, 350), (2.0, 450), (3.0, 550), (5.0, 650), (10.0, 750)]
        for mult, x in multipliers:
            color = GOLD if self.multiplier == mult else GRAY
            pygame.draw.rect(self.screen, color, (x - 40, 400, 80, 40), border_radius=10)
            self.screen.blit(self.font_small.render(f"x{mult}", True, BLACK if self.multiplier == mult else WHITE),
                             self.font_small.render(f"x{mult}", True, BLACK).get_rect(center=(x, 420)))

        self.slider.draw(self.screen)
        self.screen.blit(self.font_small.render(f"Ставка: {self.slider.val} RUB", True, WHITE),
                         self.font_small.render(f"Ставка: {self.slider.val} RUB", True, WHITE).get_rect(
                             center=(500, 540)))
        pygame.draw.rect(self.screen, GRAY if self.is_spinning else GOLD, (400, 570, 200, 60), border_radius=15)
        self.screen.blit(self.font_main.render("КРУТИТЬ", True, BLACK),
                         self.font_main.render("КРУТИТЬ", True, BLACK).get_rect(center=(500, 600)))
        if self.result_text and (self.result_timer > 0 or self.is_spinning):
            self.screen.blit(self.font_main.render(self.result_text, True, self.result_color),
                             self.font_main.render(self.result_text, True, self.result_color).get_rect(
                                 center=(self.width // 2, 360)))
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in get_input_events():
                if event.type == pygame.QUIT: self.running = False
                if not self.is_spinning and self.slider.handle_event(event):
                    continue
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: self.handle_click(event.pos)
            self.update()
            self.draw()
            self.clock.tick(60)


# ==============================================================================
# 5. БИРЖА И МАГАЗИН (Бывший market.py)
# ==============================================================================
class MarketScene:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("Биржа")
        self.clock = pygame.time.Clock()
        self.running = True
        self.font_main = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 18, bold=True)
        self.font_tiny = pygame.font.SysFont("Arial", 14)
        self.usd_slider = Slider(50, 480, 300, 15, 0, 100, 0)
        self.eur_slider = Slider(520, 480, 300, 15, 0, 100, 0)
        self.dice_slider = Slider(50, 620, 300, 15, 1, 10, 1, color=BLUE)
        self.message = "";
        self.message_timer = 0

    def draw_graph(self, rect, history, line_color, bg_color):
        pygame.draw.rect(self.screen, bg_color, rect, border_radius=15)
        pygame.draw.rect(self.screen, (60, 60, 70), rect, 2, border_radius=15)
        if len(history) < 2: return
        for i in range(1, 4):
            y = rect.y + (rect.height / 4) * i
            pygame.draw.line(self.screen, (50, 50, 60), (rect.x + 10, y), (rect.right - 10, y), 1)
        for i in range(1, 5):
            x = rect.x + (rect.width / 5) * i
            pygame.draw.line(self.screen, (50, 50, 60), (x, rect.y + 10), (x, rect.bottom - 10), 1)
        min_val = min(history) * 0.95;
        max_val = max(history) * 1.05
        if max_val == min_val: max_val += 1
        points = []
        for i, val in enumerate(history):
            x = rect.x + 10 + (i / (len(history) - 1)) * (rect.width - 20)
            y = rect.bottom - 10 - ((val - min_val) / (max_val - min_val)) * (rect.height - 20)
            points.append((x, y))
        polygon_points = points + [(rect.right - 10, rect.bottom - 10), (rect.x + 10, rect.bottom - 10)]
        fill_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.polygon(fill_surf, (*line_color, 50), [(p[0] - rect.x, p[1] - rect.y) for p in polygon_points])
        self.screen.blit(fill_surf, (rect.x, rect.y))
        pygame.draw.lines(self.screen, line_color, False, points, 3)
        if points: pygame.draw.circle(self.screen, line_color, (int(points[-1][0]), int(points[-1][1])), 4)

    def handle_click(self, pos):
        if pygame.Rect(20, 20, 120, 50).collidepoint(pos): self.running = False; return
        if pygame.Rect(50, 520, 140, 30).collidepoint(pos): economy.convert_rub_to_usd(100)
        if pygame.Rect(210, 520, 140, 30).collidepoint(pos): economy.sell_usd(self.usd_slider.val)
        if pygame.Rect(520, 520, 140, 30).collidepoint(pos): economy.convert_rub_to_eur(100)
        if pygame.Rect(680, 520, 140, 30).collidepoint(pos): economy.sell_eur(self.eur_slider.val)

        dice_positions = [(50, 500), (280, 500), (510, 500), (740, 500), (50, 600), (280, 600), (510, 600)]
        amount = self.dice_slider.val
        DICE_INFO = [("Common", (180, 180, 180)), ("Uncommon", (100, 255, 100)), ("Rare", (50, 150, 255)),
                     ("Epic", (150, 0, 200)), ("Mythic", (255, 100, 0)), ("Legendary", (255, 215, 0)),
                     ("Divine", (255, 255, 255))]

        for i, (name, color) in enumerate(DICE_INFO):
            if i >= len(dice_positions): break
            x, y = dice_positions[i]
            if pygame.Rect(x + 10, y + 45, 80, 25).collidepoint(pos):
                for _ in range(amount): economy.buy_dice(name)
            if pygame.Rect(x + 110, y + 45, 80, 25).collidepoint(pos):
                for _ in range(amount): economy.sell_dice(name)

    def draw(self):
        draw_gradient_background(self.screen, (20, 35, 25), (10, 10, 15))
        self.usd_slider.update_max(int(economy.usd))
        self.eur_slider.update_max(int(economy.eur))

        # Шапка
        self.screen.blit(
            self.font_main.render(f"Баланс: {int(economy.rubles)} RUB | {economy.usd:.2f} USD | {economy.eur:.2f} EUR",
                                  True, WHITE), (20, 20))

        pygame.draw.rect(self.screen, (60, 60, 60), (20, 80, 120, 50), border_radius=10)
        self.screen.blit(self.font_small.render("НАЗАД", True, WHITE), (50, 105))

        # Графики
        self.draw_graph(pygame.Rect(50, 150, 400, 150), economy.usd_history, (255, 60, 60), (35, 25, 25))
        self.screen.blit(self.font_main.render(f"USD: {economy.usd_rate:.2f} ₽", True, (255, 60, 60)), (50, 110))

        self.draw_graph(pygame.Rect(520, 150, 400, 150), economy.eur_history, (50, 150, 255), (25, 30, 35))
        self.screen.blit(self.font_main.render(f"EUR: {economy.eur_rate:.2f} ₽", True, (50, 150, 255)), (520, 110))

        # --- БЛОК USD ---
        self.usd_slider.draw(self.screen)
        self.screen.blit(self.font_tiny.render(f"Продать USD: {self.usd_slider.val}", True, WHITE), (50, 460))

        pygame.draw.rect(self.screen, GREEN, (50, 520, 180, 35), border_radius=5)
        self.screen.blit(self.font_small.render("КУПИТЬ 100Р", True, WHITE), (80, 528))

        pygame.draw.rect(self.screen, RED, (250, 520, 180, 35), border_radius=5)
        self.screen.blit(self.font_small.render("ПРОДАТЬ", True, WHITE), (300, 528))

        # --- БЛОК EUR ---
        self.eur_slider.draw(self.screen)
        self.screen.blit(self.font_tiny.render(f"Продать EUR: {self.eur_slider.val}", True, WHITE), (520, 460))

        pygame.draw.rect(self.screen, GREEN, (520, 520, 180, 35), border_radius=5)
        self.screen.blit(self.font_small.render("КУПИТЬ 100Р", True, WHITE), (550, 528))

        pygame.draw.rect(self.screen, RED, (720, 520, 180, 35), border_radius=5)
        self.screen.blit(self.font_small.render("ПРОДАТЬ", True, WHITE), (770, 528))

        # --- ДАЙСЫ ---
        dice_positions = [(50, 500), (280, 500), (510, 500), (740, 500), (50, 600), (280, 600), (510, 600)]
        self.dice_slider.draw(self.screen)
        self.screen.blit(self.font_tiny.render(f"Кол-во: {self.dice_slider.val}", True, WHITE), (50, 640))

        DICE_INFO = [("Common", (180, 180, 180)), ("Uncommon", (100, 255, 100)), ("Rare", (50, 150, 255)),
                     ("Epic", (150, 0, 200)), ("Mythic", (255, 100, 0)), ("Legendary", (255, 215, 0)),
                     ("Divine", (255, 255, 255))]

        for i, (name, color) in enumerate(DICE_INFO):
            if i >= len(dice_positions): break
            x, y = dice_positions[i]
            price = economy.dice_prices[name]
            count = economy.dice_inventory.count(name)

            pygame.draw.rect(self.screen, (40, 40, 45), (x, y, 200, 80), border_radius=10)
            pygame.draw.rect(self.screen, color, (x, y, 200, 80), 3, border_radius=10)

            self.screen.blit(self.font_small.render(name, True, color), (x + 10, y + 5))
            self.screen.blit(self.font_tiny.render(f"Цена: {price} RUB", True, WHITE), (x + 10, y + 25))
            self.screen.blit(self.font_tiny.render(f"В инв: {count}", True, GOLD), (x + 130, y + 5))

            pygame.draw.rect(self.screen, GREEN if economy.rubles >= price * self.dice_slider.val else GRAY,
                             (x + 10, y + 45, 80, 25), border_radius=5)
            self.screen.blit(self.font_tiny.render("КУПИТЬ", True, BLACK), (x + 25, y + 50))

            can_sell = count >= self.dice_slider.val
            pygame.draw.rect(self.screen, RED if can_sell else GRAY, (x + 110, y + 45, 80, 25), border_radius=5)
            self.screen.blit(self.font_tiny.render("ПРОДАТЬ", True, WHITE), (x + 120, y + 50))

        pygame.display.flip()

    def run(self):
        while self.running:
            for event in get_input_events():
                if event.type == pygame.QUIT: self.running = False
                if self.usd_slider.handle_event(event): continue
                if self.eur_slider.handle_event(event): continue
                if self.dice_slider.handle_event(event):
                    continue
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: self.handle_click(event.pos)
            self.draw()
            self.clock.tick(60)


# ==============================================================================
# 6. ЦАРЬ-ДЕПЧИК (Бывший tsar.py)
# ==============================================================================
class TsarGame:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("Царь-Депчик")
        self.clock = pygame.time.Clock()
        self.running = True
        self.cost = 100;
        self.is_spinning = False;
        self.spin_timer = 0;
        self.reveal_index = -1;
        self.won_dice = None
        self.result_text = "";
        self.result_color = WHITE;
        self.result_timer = 0
        self.font_main = pygame.font.SysFont("Arial", 36, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 22, bold=True)
        self.font_tiny = pygame.font.SysFont("Arial", 16)

    def handle_click(self, pos):
        if self.is_spinning: return
        if pygame.Rect(20, 20, 120, 50).collidepoint(pos): self.running = False; return
        if pygame.Rect(350, 580, 300, 70).collidepoint(pos): self.start_spin()

    def start_spin(self):
        if economy.rubles >= self.cost:
            economy.spend_rubles(self.cost)
            self.is_spinning = True;
            self.spin_timer = 0;
            self.reveal_index = 0;
            self.result_text = ""
            available_dice = economy.tsar_dice
            weights = [economy.dice_chances[d] for d in available_dice]
            self.won_dice = random.choices(available_dice, weights=weights, k=1)[0]
        else:
            self.result_text = "Недостаточно средств!";
            self.result_color = RED;
            self.result_timer = 60

    def update(self):
        if self.is_spinning:
            self.spin_timer += 1
            if self.spin_timer > 10 and self.spin_timer % 10 == 0: self.reveal_index += 1
            if self.reveal_index >= 4:
                self.is_spinning = False;
                self.reveal_index = -1
                economy.dice_inventory.append(self.won_dice);
                economy.save_game()
                self.result_text = f"ВЫПАЛ: {self.won_dice}!"
                # Простая проверка цвета для текста
                color_map = {"Common": (180, 180, 180), "Uncommon": (100, 255, 100), "Rare": (50, 150, 255),
                             "Epic": (150, 0, 200), "Mythic": (255, 100, 0), "Legendary": (255, 215, 0),
                             "Divine": (255, 255, 255)}
                self.result_color = color_map.get(self.won_dice, WHITE);
                self.result_timer = 180
        if self.result_timer > 0: self.result_timer -= 1

    def draw(self):
        self.screen.fill((20, 25, 20))
        self.screen.blit(self.font_main.render(f"Баланс: {int(economy.rubles)} RUB", True, WHITE), (20, 20))
        self.screen.blit(self.font_small.render(f"Игровой День: {economy.game_day}", True, GOLD),
                         (self.width - 250, 30))
        pygame.draw.rect(self.screen, GRAY, (20, 70, 120, 50), border_radius=10)
        self.screen.blit(self.font_small.render("НАЗАД", True, WHITE), (50, 85))
        self.screen.blit(self.font_main.render("ЦАРЬ-ДЕПЧИК", True, GOLD),
                         self.font_main.render("ЦАРЬ-ДЕПЧИК", True, GOLD).get_rect(center=(self.width // 2, 100)))

        start_x = 100;
        spacing = 200
        color_map = {"Common": (180, 180, 180), "Uncommon": (100, 255, 100), "Rare": (50, 150, 255),
                     "Epic": (150, 0, 200), "Mythic": (255, 100, 0), "Legendary": (255, 215, 0),
                     "Divine": (255, 255, 255)}

        for i, dice_name in enumerate(economy.tsar_dice):
            x = start_x + i * spacing;
            y = 250;
            rect = pygame.Rect(x, y, 160, 220)
            is_revealed = (not self.is_spinning and self.result_text != "") or (
                        self.is_spinning and i < self.reveal_index)
            is_winner = is_revealed and (self.won_dice == dice_name) and not self.is_spinning
            pygame.draw.rect(self.screen, (40, 40, 45), rect, border_radius=15)
            pygame.draw.rect(self.screen, color_map.get(dice_name, WHITE), rect, 4, border_radius=15)
            if self.is_spinning and i == self.reveal_index:
                pygame.draw.rect(self.screen, random.choice([WHITE, GOLD]), rect, 4, border_radius=15)
                self.screen.blit(self.font_main.render("?", True, WHITE),
                                 self.font_main.render("?", True, WHITE).get_rect(center=rect.center))
            elif is_revealed:
                self.screen.blit(self.font_small.render(dice_name, True, color_map.get(dice_name, WHITE)),
                                 self.font_small.render(dice_name, True, WHITE).get_rect(
                                     center=(rect.centerx, rect.y + 80)))
                self.screen.blit(self.font_tiny.render(f"Шанс: {economy.dice_chances[dice_name]}%", True, GRAY),
                                 self.font_tiny.render(f"Шанс: {economy.dice_chances[dice_name]}%", True,
                                                       GRAY).get_rect(center=(rect.centerx, rect.y + 120)))
                if is_winner:
                    pygame.draw.circle(self.screen, GOLD, rect.center, 50, 4)
            else:
                self.screen.blit(self.font_main.render("?", True, GRAY),
                                 self.font_main.render("?", True, GRAY).get_rect(center=rect.center))

        btn_rect = pygame.Rect(350, 580, 300, 70)
        pygame.draw.rect(self.screen, GOLD if economy.rubles >= self.cost and not self.is_spinning else GRAY, btn_rect,
                         border_radius=15)
        self.screen.blit(self.font_main.render(f"ОТКРЫТЬ ЗА {self.cost} RUB", True, BLACK),
                         self.font_main.render(f"ОТКРЫТЬ ЗА {self.cost} RUB", True, BLACK).get_rect(
                             center=btn_rect.center))
        if self.result_text and self.result_timer > 0:
            self.screen.blit(self.font_main.render(self.result_text, True, self.result_color),
                             self.font_main.render(self.result_text, True, self.result_color).get_rect(
                                 center=(self.width // 2, 520)))
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in get_input_events():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: self.handle_click(event.pos)
            self.update()
            self.draw()
            self.clock.tick(60)


# ==============================================================================
# 7. БУРА (Огромный код карточной игры, сокращенный до вызовов)
# ==============================================================================
# ВНИМАНИЕ: Сюда вставляется весь класс Game из твоего bura.py
# (вместе с Particle, Card, Button, TitleAnimation и т.д.)
# Чтобы сэкономить место в ответе, я пишу инструкцию, как это сделать в конце.

INITIAL_WIDTH, INITIAL_HEIGHT = 2000, 1000
FPS = 60
CARD_WIDTH, CARD_HEIGHT = 150, 220
ANIMATION_SPEED = 25


DARK_GREEN = (0, 40, 0); GREEN = (34, 139, 34); FOREST_GREEN = (0, 70, 0)
LIGHT_GREEN = (144, 238, 144); WHITE = (255, 255, 255); BLACK = (5, 5, 5)
DARK_GRAY = (20, 20, 20); RED = (255, 60, 60); BRIGHT_RED = (255, 100, 100)
DARK_RED = (160, 20, 20); GOLD = (255, 215, 0); BRIGHT_GOLD = (255, 235, 100)
DARK_GOLD = (184, 134, 11); BLUE = (52, 152, 219); DARK_BLUE = (20, 20, 120)
PURPLE = (155, 89, 182); ROYAL_PURPLE = (106, 13, 173); BROWN = (139, 69, 19)
LIGHT_BROWN = (160, 82, 45); GRAY = (100, 100, 100); LIGHT_GRAY = (180, 180, 180)
EMERALD = (46, 204, 113); BRIGHT_EMERALD = (100, 255, 150); TURQUOISE = (26, 188, 156)
SUNSET = (243, 156, 18); CRIMSON = (192, 57, 43); PEARL = (240, 240, 240)
IVORY = (255, 255, 240); PLATINUM = (229, 228, 226)

SUITS = ['♠', '♥', '♦', '♣']
SUIT_NAMES = {'♠': 'Пики', '♥': 'Черви', '♦': 'Бубны', '♣': 'Крести'}
SUIT_COLORS = {'♠': BLACK, '♥': RED, '♦': RED, '♣': BLACK}
RANKS = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
VALUES = {'6': 0, '7': 0, '8': 0, '9': 0, '10': 10, 'J': 2, 'Q': 3, 'K': 4, 'A': 11}

TRUMP_TITLES = {
    '♦': ["КОЗЫРИ БУБНЫ", "ТРУДОВИК ФИГАРИТ В БУБЕН"],
    '♥': ["ЧЕРВИ КОЗЫРИ У НАС", "ЧЕРВИ БЫЛИ В ПРОШЛЫЙ РАЗ"],
    '♣': ["КОЗЫРИ КРЕСТИ", "ДУРАКИ НА МЕСТЕ"],
    '♠': ["КОЗЫРИ ПИКИ", "ДУРАКИ ЗАИКИ"]
}

GAME_RULES = [
    "ПРАВИЛА ИГРЫ БУРА", "",
    "1. Игра ведется до 31 очка",
    "2. Достоинство карт:", "   6,7,8,9 - 0 очков",
    "   Валет - 2, Дама - 3", "   Король - 4, Туз - 11", "   10 - 10 очков", "",
    "3. Комбинации:", "   БУРА (3 козыря) - победа",
    "   МОСКВА (3 туза) - победа", "   ПАДИК (3 шестерки) +5 очков",
    "   ПИСЬМО (3 одной масти, не козырь):",
    "     • Если бот может побить ВСЕ 3 карты:",
    "       очки боту (карты игрока + карты бота)",
    "     • Если бот НЕ может побить хотя бы одну:",
    "       очки игроку, ВСЕ карты бота в скрытые", "",
    "4. Скрытые карты:", "   • Попадают только карты бота,",
    "     когда он не может побить", "   • Накапливаются до вскрытия",
    "   • Кнопка ВСКРЫТЬСЯ добавляет их в счет", "",
    "5. Выделение мышью:", "   • ЛКМ по карте - обычный ход",
    "   • Зажми ЛКМ и тяни - выделение",
    "   • 2 карты одной масти - автоматический сброс",
    "   • 3 карты - автоматическая комбинация", "",
    "6. Управление:", "   • ПРАВИЛА - открыть это окно",
    "   • НОВАЯ - новая игра", "   • ВЗЯТЬ - взять карту из колоды",
    "   • ВСКРЫТЬСЯ - добавить скрытые карты", "",
    "   Автор: Асадик не моросит", "   Версия: -2.0"
]

font_cache = {}


class Slider:
    def __init__(self, x, y, w, h, min_val, max_val, initial_val, color=GOLD):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.val = initial_val
        self.dragging = False
        self.color = color
    def update_max(self, new_max):
        self.max_val = max(0, new_max)
        if self.val > self.max_val: self.val = self.max_val
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.inflate(40 if IS_IOS else 20, 40 if IS_IOS else 20).collidepoint(event.pos):
                self.dragging = True; self._update_val(event.pos[0]); return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_val(event.pos[0]); return True
        return False
    def _update_val(self, mouse_x):
        if self.max_val <= self.min_val: self.val = self.min_val; return
        rel_x = max(0, min(mouse_x - self.rect.x, self.rect.w))
        self.val = int(self.min_val + (rel_x / self.rect.w) * (self.max_val - self.min_val))
    def draw(self, surface):
        pygame.draw.rect(surface, (60, 60, 60), self.rect, border_radius=self.rect.h//2)
        fill_w = ((self.val - self.min_val) / (self.max_val - self.min_val)) * self.rect.w if self.max_val > self.min_val else 0
        pygame.draw.rect(surface, self.color, (self.rect.x, self.rect.y, fill_w, self.rect.h), border_radius=self.rect.h//2)
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(surface, WHITE, (int(knob_x), self.rect.centery), self.rect.h + 2)
        pygame.draw.circle(surface, self.color, (int(knob_x), self.rect.centery), self.rect.h - 2)


def get_font(size, bold=False, italic=False):
    key = (size, bold, italic)
    if key in font_cache: return font_cache[key]
    font_names = ['Arial', 'Segoe UI', 'DejaVu Sans', 'FreeSans', 'Noto Sans',
                  'Times New Roman', 'Georgia', 'Palatino']
    for font_name in font_names:
        try:
            if bold and italic: font = pygame.font.SysFont(font_name, size, bold=True, italic=True)
            elif bold: font = pygame.font.SysFont(font_name, size, bold=True)
            elif italic: font = pygame.font.SysFont(font_name, size, italic=True)
            else: font = pygame.font.SysFont(font_name, size)
            font_cache[key] = font
            return font
        except: continue
    font = pygame.font.Font(None, size)
    font_cache[key] = font
    return font



class Particle:
    def __init__(self, x, y, color, velocity, lifetime, shape="circle"):
        self.x = x; self.y = y; self.color = color
        self.vx, self.vy = velocity
        self.lifetime = lifetime; self.max_lifetime = lifetime
        self.size = random.randint(2, 8); self.shape = shape
        self.rotation = random.randint(0, 360)
        self.rotation_speed = random.uniform(-3, 3)
    def update(self):
        self.x += self.vx; self.y += self.vy
        self.vy += 0.02; self.vx *= 0.99; self.vy *= 0.99
        self.rotation += self.rotation_speed; self.lifetime -= 1
        return self.lifetime > 0
    def draw(self, screen):
        alpha = int(255 * (self.lifetime / self.max_lifetime))
        size = int(self.size * (self.lifetime / self.max_lifetime))
        if size <= 0: return
        if self.shape == "circle":
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color, alpha), (size, size), size)
            screen.blit(surf, (self.x - size, self.y - size))
        elif self.shape == "square":
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.rect(surf, (*self.color, alpha), (0, 0, size * 2, size * 2))
            screen.blit(surf, (self.x - size, self.y - size))
        elif self.shape == "diamond":
            points = [(self.x, self.y - size), (self.x + size, self.y), (self.x, self.y + size), (self.x - size, self.y)]
            pygame.draw.polygon(screen, (*self.color, alpha), points)
        elif self.shape == "star":
            points = []
            for i in range(5):
                angle = self.rotation + i * 72
                rad = math.radians(angle)
                points.append((self.x + math.cos(rad) * size * 2, self.y + math.sin(rad) * size * 2))
            if len(points) >= 3: pygame.draw.polygon(screen, (*self.color, alpha), points, 1)

class GlowEffect:
    def __init__(self, x, y, color, radius, duration, pulse=True):
        self.x = x; self.y = y; self.color = color
        self.max_radius = radius; self.radius = 0
        self.duration = duration; self.timer = duration
        self.active = True; self.pulse = pulse
        self.pulse_offset = random.random() * math.pi * 2
    def update(self):
        self.timer -= 1
        if self.timer <= 0: self.active = False; return
        progress = 1 - (self.timer / self.duration)
        if self.pulse:
            pulse_factor = math.sin(pygame.time.get_ticks() * 0.01 + self.pulse_offset) * 0.15 + 0.85
            self.radius = self.max_radius * (1 - progress) * pulse_factor
        else: self.radius = self.max_radius * (1 - progress)
    def draw(self, screen):
        if not self.active: return
        alpha = int(150 * (self.timer / self.duration))
        for r in range(int(self.radius), 0, -3):
            layer_alpha = alpha - r * 2
            if layer_alpha > 0:
                surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*self.color, layer_alpha), (r, r), r)
                screen.blit(surf, (self.x - r, self.y - r))

class FloatingCard:
    def __init__(self, width, height):
        self.width = width; self.height = height
        self.suit = random.choice(SUITS); self.rank = random.choice(RANKS)
        self.x = random.randint(0, width); self.y = random.randint(0, height)
        self.vx = random.uniform(-0.08, 0.08); self.vy = random.uniform(-0.08, 0.08)
        self.rotation = random.randint(0, 360); self.rotation_speed = random.uniform(-0.15, 0.15)
        self.alpha = random.randint(5, 10); self.scale = random.uniform(0.25, 0.4)
    def update(self):
        self.x += self.vx; self.y += self.vy; self.rotation += self.rotation_speed
        if self.x < -150: self.x = self.width + 150
        elif self.x > self.width + 150: self.x = -150
        if self.y < -150: self.y = self.height + 150
        elif self.y > self.height + 150: self.y = -150
    def draw(self, screen):
        font = get_font(int(60 * self.scale), bold=True)
        color = SUIT_COLORS[self.suit]
        text = font.render(f"{self.rank}{self.suit}", True, (*color, self.alpha))
        rotated = pygame.transform.rotate(text, self.rotation)
        rect = rotated.get_rect(center=(self.x, self.y))
        screen.blit(rotated, rect)

class Card:
    def __init__(self, rank, suit):
        self.rank = rank; self.suit = suit; self.value = VALUES[rank]
        self.rect = pygame.Rect(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self.owner = None; self.selected = False; self.hover = False
    def __repr__(self): return f"{self.rank}{self.suit}"

class AnimatedCard:
    def __init__(self, card, start_pos, target_pos, owner=None, discarded=False, hidden_points=False):
        self.card = card; self.card.owner = owner
        self.x, self.y = start_pos
        self.target_x, self.target_y = target_pos
        self.owner = owner; self.discarded = discarded; self.hidden_points = hidden_points
        self.active = True; self.rotation = 0
        self.rotation_speed = random.randint(-8, 8) if discarded else random.randint(-3, 3)
        self.scale = 1.0; self.scale_speed = 0.97 if discarded else 1.0
        self.particles = []; self.trail = []; self.trail_length = 5; self.time = 0
        if discarded:
            for _ in range(20):
                self.particles.append(Particle(
                    self.x + CARD_WIDTH // 2, self.y + CARD_HEIGHT // 2,
                    random.choice([GOLD, RED, DARK_GOLD, EMERALD]),
                    (random.uniform(-4, 4), random.uniform(-6, -3)),
                    random.randint(20, 40), random.choice(["circle", "square", "diamond"])))
    def update(self):
        self.time += 1
        self.trail.append((self.x, self.y, self.rotation, self.scale))
        if len(self.trail) > self.trail_length: self.trail.pop(0)
        dx = self.target_x - self.x; dy = self.target_y - self.y
        dist = math.hypot(dx, dy)
        if dist < ANIMATION_SPEED:
            self.x, self.y = self.target_x, self.target_y; self.active = False
        else:
            factor = min(1.0, ANIMATION_SPEED / dist)
            self.x += dx * factor * 0.8; self.y += dy * factor * 0.8
        if self.discarded:
            self.rotation += self.rotation_speed; self.scale *= self.scale_speed
        self.particles = [p for p in self.particles if p.update()]
    def draw(self, screen):
        for i, (tx, ty, trot, tscale) in enumerate(self.trail):
            alpha = 50 * (i / len(self.trail))
            if alpha > 5:
                trail_surf = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
                pygame.draw.rect(trail_surf, (*GOLD, int(alpha)), (0, 0, CARD_WIDTH, CARD_HEIGHT), 2, border_radius=12)
                scaled_width, scaled_height = int(CARD_WIDTH * tscale), int(CARD_HEIGHT * tscale)
                scaled_surf = pygame.transform.scale(trail_surf, (scaled_width, scaled_height))
                rotated_trail = pygame.transform.rotate(scaled_surf, trot)
                trail_rect = rotated_trail.get_rect(center=(tx + CARD_WIDTH // 2, ty + CARD_HEIGHT // 2))
                screen.blit(rotated_trail, trail_rect)
        for p in self.particles: p.draw(screen)
        if self.discarded: self._draw_discarded_card(screen)
        else: self._draw_normal_card(screen)
    def _draw_normal_card(self, screen):
        card_surf = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
        for i in range(CARD_HEIGHT):
            pearl = 250 - i * 0.2
            pygame.draw.line(card_surf, (pearl, pearl, pearl), (0, i), (CARD_WIDTH, i))
        pygame.draw.rect(card_surf, DARK_GOLD, (0, 0, CARD_WIDTH, CARD_HEIGHT), 4, border_radius=15)
        pygame.draw.rect(card_surf, GOLD, pygame.Rect(4, 4, CARD_WIDTH - 8, CARD_HEIGHT - 8), 2, border_radius=12)
        color = SUIT_COLORS[self.card.suit]
        if self.card.suit in ['♥', '♦']: color = BRIGHT_RED
        font_small, font_big = get_font(38, bold=True), get_font(80, bold=True)
        rank_text, suit_text = font_small.render(self.card.rank, True, color), font_small.render(self.card.suit, True, color)
        card_surf.blit(rank_text, (12, 8)); card_surf.blit(suit_text, (12, 48))
        card_surf.blit(pygame.transform.rotate(rank_text, 180), (CARD_WIDTH - 50, CARD_HEIGHT - 85))
        card_surf.blit(pygame.transform.rotate(suit_text, 180), (CARD_WIDTH - 50, CARD_HEIGHT - 50))
        big_suit = font_big.render(self.card.suit, True, color); big_suit.set_alpha(120)
        card_surf.blit(big_suit, big_suit.get_rect(center=(CARD_WIDTH // 2, CARD_HEIGHT // 2)))
        scaled_width, scaled_height = int(CARD_WIDTH * self.scale), int(CARD_HEIGHT * self.scale)
        scaled_surf = pygame.transform.scale(card_surf, (scaled_width, scaled_height))
        rotated = pygame.transform.rotate(scaled_surf, self.rotation)
        rect = rotated.get_rect(center=(self.x + CARD_WIDTH // 2, self.y + CARD_HEIGHT // 2))
        screen.blit(rotated, rect)
    def _draw_discarded_card(self, screen):
        card_surf = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
        for i in range(CARD_HEIGHT):
            color_value = 60 + i * 0.3
            pygame.draw.line(card_surf, (color_value, color_value, color_value), (0, i), (CARD_WIDTH, i))
        pygame.draw.rect(card_surf, DARK_GOLD, (0, 0, CARD_WIDTH, CARD_HEIGHT), 4, border_radius=12)
        pygame.draw.line(card_surf, RED, (20, 20), (CARD_WIDTH - 20, CARD_HEIGHT - 20), 5)
        pygame.draw.line(card_surf, RED, (CARD_WIDTH - 20, 20), (20, CARD_HEIGHT - 20), 5)
        cx, cy = CARD_WIDTH // 2, CARD_HEIGHT // 2
        pygame.draw.circle(card_surf, DARK_GOLD, (cx, cy), 30, 2)
        for i in range(0, 360, 90):
            angle = math.radians(i)
            pygame.draw.line(card_surf, DARK_GOLD, (cx + math.cos(angle) * 40, cy + math.sin(angle) * 40),
                             (cx + math.cos(angle) * 50, cy + math.sin(angle) * 50), 2)
        if self.hidden_points:
            text = get_font(48, bold=True).render("?", True, GOLD)
            card_surf.blit(text, text.get_rect(center=(cx, cy)))
        scaled_width, scaled_height = int(CARD_WIDTH * self.scale), int(CARD_HEIGHT * self.scale)
        scaled_surf = pygame.transform.scale(card_surf, (scaled_width, scaled_height))
        rotated = pygame.transform.rotate(scaled_surf, self.rotation)
        rect = rotated.get_rect(center=(self.x + CARD_WIDTH // 2, self.y + CARD_HEIGHT // 2))
        screen.blit(rotated, rect)


def draw_card(screen, card, x, y, back=False, highlight=False, selected=False, glow=False, animated=False):
    shadow_surf = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, 180), (0, 0, CARD_WIDTH, CARD_HEIGHT), border_radius=15)
    screen.blit(shadow_surf, (x + 6, y + 6))
    card_rect = pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT)
    if selected or highlight or glow:
        glow_surf = pygame.Surface((CARD_WIDTH + 20, CARD_HEIGHT + 20), pygame.SRCALPHA)
        glow_color = GOLD if highlight or selected else (GOLD if glow else DARK_GOLD)
        for r in range(10, 0, -2):
            alpha = 100 - r * 5
            pygame.draw.rect(glow_surf, (*glow_color, alpha), (10 - r, 10 - r, CARD_WIDTH + r * 2, CARD_HEIGHT + r * 2), border_radius=15)
        screen.blit(glow_surf, (x - 10, y - 10))
    if back:
        for i in range(CARD_HEIGHT):
            color_value = 30 + i * 0.5
            r = min(color_value, 70); g = min(color_value + 20, 90); b = min(color_value + 40, 130)
            pygame.draw.line(screen, (r, g, b), (x, y + i), (x + CARD_WIDTH, y + i))
        pygame.draw.rect(screen, GOLD, card_rect, 4, border_radius=15)
        center_x, center_y = x + CARD_WIDTH // 2, y + CARD_HEIGHT // 2
        pygame.draw.circle(screen, GOLD, (center_x, center_y), 35, 2)
        pygame.draw.circle(screen, DARK_GOLD, (center_x, center_y), 25, 2)
        pygame.draw.circle(screen, GOLD, (center_x, center_y), 15, 2)
        for i in range(0, 360, 30):
            angle = math.radians(i)
            pygame.draw.line(screen, GOLD, (center_x + math.cos(angle) * 40, center_y + math.sin(angle) * 40),
                             (center_x + math.cos(angle) * 55, center_y + math.sin(angle) * 55), 2)
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            cx, cy = center_x + dx * 50, center_y + dy * 60
            pygame.draw.polygon(screen, GOLD, [(cx, cy - 8), (cx + 8, cy), (cx, cy + 8), (cx - 8, cy)], 2)
        for cx, cy in [(x + 12, y + 12), (x + CARD_WIDTH - 12, y + 12), (x + 12, y + CARD_HEIGHT - 12), (x + CARD_WIDTH - 12, y + CARD_HEIGHT - 12)]:
            pygame.draw.circle(screen, GOLD, (cx, cy), 5, 2)
    else:
        for i in range(CARD_HEIGHT):
            pearl = 250 - i * 0.2
            pygame.draw.line(screen, (pearl, pearl, pearl), (x, y + i), (x + CARD_WIDTH, y + i))
        border_color = GOLD if highlight else (DARK_GOLD if selected else DARK_GOLD)
        pygame.draw.rect(screen, border_color, card_rect, 4, border_radius=15)
        pygame.draw.rect(screen, GOLD if highlight else DARK_GOLD, card_rect.inflate(-8, -8), 2, border_radius=12)
        color = SUIT_COLORS[card.suit]
        if card.suit in ['♥', '♦']: color = BRIGHT_RED
        font_small, font_big = get_font(38, bold=True), get_font(80, bold=True)
        rank_text, suit_text = font_small.render(card.rank, True, color), font_small.render(card.suit, True, color)
        screen.blit(rank_text, (x + 12, y + 8)); screen.blit(suit_text, (x + 12, y + 48))
        screen.blit(pygame.transform.rotate(rank_text, 180), (x + CARD_WIDTH - 50, y + CARD_HEIGHT - 85))
        screen.blit(pygame.transform.rotate(suit_text, 180), (x + CARD_WIDTH - 50, y + CARD_HEIGHT - 50))
        big_suit = font_big.render(card.suit, True, color); big_suit.set_alpha(120)
        screen.blit(big_suit, big_suit.get_rect(center=(x + CARD_WIDTH // 2, y + CARD_HEIGHT // 2)))


def draw_text(screen, text, x, y, size=36, color=WHITE, center=True, bold=False, shadow=True, glow=False, alpha=255):
    font = get_font(size, bold)
    if glow:
        for offset in range(8, 16, 2):
            glow_surf = font.render(str(text), True, (*color, 100 - offset * 5))
            rect = glow_surf.get_rect(center=(x, y)) if center else glow_surf.get_rect(topleft=(x, y))
            screen.blit(glow_surf, rect)
    if shadow:
        shadow_surf = font.render(str(text), True, (0, 0, 0))
        rect = shadow_surf.get_rect(center=(x + 3, y + 3)) if center else shadow_surf.get_rect(topleft=(x + 3, y + 3))
        screen.blit(shadow_surf, rect)
    surf = font.render(str(text), True, color)
    if alpha < 255: surf.set_alpha(alpha)
    rect = surf.get_rect(center=(x, y)) if center else surf.get_rect(topleft=(x, y))
    screen.blit(surf, rect)


# ============================================================
# UI КОМПОНЕНТЫ
# ============================================================



class TitleAnimation:
    def __init__(self, trump_suit, width, height):
        self.lines = TRUMP_TITLES[trump_suit]; self.alpha = 255; self.active = True
        self.timer = 200; self.y_offset = 0; self.particles = []
        self.floating_cards = [FloatingCard(width, height) for _ in range(20)]
        self.width = width; self.height = height; self.scale = 1.0
        self.colors = {'♠': [DARK_GRAY, GOLD], '♣': [FOREST_GREEN, BRIGHT_EMERALD], '♥': [BRIGHT_RED, GOLD], '♦': [GOLD, DARK_GOLD]}
        for _ in range(40):
            self.particles.append(Particle(
                random.randint(0, width), random.randint(0, height),
                random.choice([GOLD, RED, DARK_GOLD]), (random.uniform(-1, 1), random.uniform(-2, -1)),
                random.randint(40, 70), random.choice(["circle", "diamond"])))
    def update(self):
        self.timer -= 1
        if self.timer <= 0: self.active = False; return
        for card in self.floating_cards: card.update()
        if random.random() < 0.6:
            self.particles.append(Particle(
                random.randint(0, self.width), random.randint(0, self.height),
                random.choice([GOLD, RED, DARK_GOLD]), (random.uniform(-2, 2), random.uniform(-2, 2)),
                random.randint(40, 70), random.choice(["circle", "diamond"])))
        self.particles = [p for p in self.particles if p.update()]
        self.scale = 1.0 + math.sin(pygame.time.get_ticks() * 0.003) * 0.03
        if self.timer > 170: self.alpha = 255
        elif self.timer < 30: self.alpha = int(255 * (self.timer / 30))
        else: self.alpha = 255
        self.y_offset = math.sin(pygame.time.get_ticks() * 0.003) * 15
    def draw(self, screen, trump_suit):
        if not self.active: return
        for card in self.floating_cards: card.draw(screen)
        for p in self.particles: p.draw(screen)
        overlay = pygame.Surface((self.width, self.height)); overlay.set_alpha(200); overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        colors = self.colors[trump_suit]
        for i, line in enumerate(self.lines):
            y = self.height // 2 - 100 + i * 120 + self.y_offset
            size = int(100 * self.scale) if i == 0 else int(72 * self.scale)
            color = colors[i % len(colors)]
            for offset in range(12, 0, -2):
                shadow_surf = get_font(size, bold=True).render(line, True, (0, 0, 0))
                shadow_surf.set_alpha(self.alpha // 2)
                screen.blit(shadow_surf, shadow_surf.get_rect(center=(self.width // 2 + offset * 2, y + offset * 2)))
            text_surf = get_font(size, bold=True).render(line, True, color)
            text_surf.set_alpha(self.alpha)
            screen.blit(text_surf, text_surf.get_rect(center=(self.width // 2, y)))
        for i in range(0, 360, 45):
            angle = math.radians(i)
            pygame.draw.line(screen, GOLD, (self.width // 2 + math.cos(angle) * 200, self.height // 2 + math.sin(angle) * 150),
                             (self.width // 2 + math.cos(angle) * 250, self.height // 2 + math.sin(angle) * 200), 2)


class VictoryAnimation:
    def __init__(self, winner, text, width, height):
        self.winner = winner; self.text = text; self.alpha = 255; self.active = True
        self.timer = 300; self.particles = []; self.glow_radius = 0; self.glow_growth = 3
        self.width = width; self.height = height; self.scale = 1.0; self.scale_direction = 1
        self.rotation = 0; self.decorative_elements = []
        particle_count = 150 if winner == "player" else 100
        colors = [GOLD, BRIGHT_GOLD, EMERALD] if winner == "player" else [RED, DARK_RED, GRAY]
        for _ in range(particle_count):
            self.particles.append(Particle(
                random.randint(0, width), random.randint(0, height),
                random.choice(colors), (random.uniform(-4, 4), random.uniform(-4, 4)),
                random.randint(100, 180), random.choice(["circle", "square", "diamond", "star"])))
        for i in range(20):
            angle = random.uniform(0, 2 * math.pi); radius = random.randint(100, 300)
            self.decorative_elements.append({
                'x': width // 2 + math.cos(angle) * radius, 'y': height // 2 + math.sin(angle) * radius * 0.6,
                'angle': angle, 'radius': radius, 'phase': random.uniform(0, 2 * math.pi)})
    def update(self):
        self.timer -= 1
        if self.timer <= 0: self.active = False; return
        self.glow_radius += self.glow_growth
        if self.glow_radius > 250 or self.glow_radius < 0: self.glow_growth *= -1
        self.scale += 0.005 * self.scale_direction
        if self.scale > 1.1 or self.scale < 0.9: self.scale_direction *= -1
        self.rotation += 0.1
        if random.random() < 0.5:
            self.particles.append(Particle(
                random.randint(0, self.width), random.randint(0, self.height),
                random.choice([GOLD, RED, EMERALD]), (random.uniform(-3, 3), random.uniform(-3, 3)),
                random.randint(60, 100), random.choice(["circle", "diamond"])))
        self.particles = [p for p in self.particles if p.update()]
        if self.timer > 250: self.alpha = 255
        elif self.timer < 50: self.alpha = int(255 * (self.timer / 50))
    def draw(self, screen):
        if not self.active: return
        for elem in self.decorative_elements:
            pulse = math.sin(pygame.time.get_ticks() * 0.002 + elem['phase']) * 0.3 + 0.7
            x, y, alpha, size = elem['x'], elem['y'], int(40 * pulse), 15
            pygame.draw.polygon(screen, (*GOLD, alpha), [(x, y - size), (x + size, y), (x, y + size), (x - size, y)], 2)
        for p in self.particles: p.draw(screen)
        for r in range(int(self.glow_radius), 0, -15):
            alpha = 60 - r // 4
            if alpha > 0:
                glow_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                color = GOLD if self.winner == "player" else RED
                pygame.draw.circle(glow_surf, (*color, alpha), (self.width // 2, self.height // 2 - 80), r)
                screen.blit(glow_surf, (0, 0))
        overlay = pygame.Surface((self.width, self.height)); overlay.set_alpha(200); overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        y = self.height // 2 - 80; color = GOLD if self.winner == "player" else RED
        for offset in range(15, 0, -2):
            shadow_surf = get_font(int(120 * self.scale), bold=True).render(self.text, True, (0, 0, 0))
            shadow_surf.set_alpha(self.alpha // 2)
            screen.blit(shadow_surf, shadow_surf.get_rect(center=(self.width // 2 + offset * 2, y + offset * 2)))
        text_surf = get_font(int(120 * self.scale), bold=True).render(self.text, True, color)
        text_surf.set_alpha(self.alpha)
        screen.blit(text_surf, text_surf.get_rect(center=(self.width // 2, y)))
        for i in range(8):
            angle = self.rotation + i * 45; rad = math.radians(angle)
            pygame.draw.line(screen, color,
                             (self.width // 2 + math.cos(rad) * 200, self.height // 2 - 80 + math.sin(rad) * 150),
                             (self.width // 2 + math.cos(rad) * 300, self.height // 2 - 80 + math.sin(rad) * 250), 2)


class RulesWindow:
    def __init__(self, width, height):
        self.width = width; self.height = height; self.active = False
        self.alpha = 0; self.target_alpha = 0; self.scroll_y = 0
        self.max_scroll = max(0, len(GAME_RULES) * 35 - 450)
        self.close_button = Button(width // 2 + 250, height // 2 - 200, 40, 40, "X", DARK_RED, corner_radius=20)
        self.scrollbar_rect = pygame.Rect(0, 0, 20, 100); self.scrollbar_dragging = False
    def reset(self):
        self.active = False; self.alpha = 0; self.target_alpha = 0; self.scroll_y = 0; self.scrollbar_dragging = False
    def toggle(self):
        self.active = not self.active; self.target_alpha = 255 if self.active else 0
    def update(self):
        if self.alpha < self.target_alpha: self.alpha = min(self.alpha + 15, self.target_alpha)
        elif self.alpha > self.target_alpha: self.alpha = max(self.alpha - 15, self.target_alpha)
        if self.active:
            self.close_button.rect.x = self.width // 2 + 250
            self.close_button.rect.y = self.height // 2 - 200
    def handle_scroll(self, y):
        self.scroll_y = max(0, min(self.scroll_y + y, self.max_scroll))
    def handle_click(self, pos):
        if self.active and self.close_button.click(pos): self.toggle(); return True
        if self.active:
            ww, wh = 600, 500
            wx, wy = (self.width - ww) // 2, (self.height - wh) // 2
            sy = wy + 60 + (self.scroll_y / self.max_scroll) * (wh - 120) if self.max_scroll > 0 else wy + 60
            self.scrollbar_rect.x, self.scrollbar_rect.y = wx + ww - 30, sy
            if self.scrollbar_rect.collidepoint(pos): self.scrollbar_dragging = True; return True
        return False
    def handle_mouse_move(self, pos):
        if self.scrollbar_dragging and self.active:
            ww, wh = 600, 500
            wx, wy = (self.width - ww) // 2, (self.height - wh) // 2
            relative_y = pos[1] - (wy + 60); scroll_range = wh - 120
            if scroll_range > 0: self.scroll_y = max(0, min(1, relative_y / scroll_range)) * self.max_scroll
    def handle_mouse_up(self): self.scrollbar_dragging = False
    def draw(self, screen):
        if self.alpha <= 0: return
        overlay = pygame.Surface((self.width, self.height)); overlay.set_alpha(int(self.alpha * 0.7)); overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        ww, wh = 600, 500
        wx, wy = (self.width - ww) // 2, (self.height - wh) // 2
        window_surf = pygame.Surface((ww, wh), pygame.SRCALPHA)
        for i in range(wh):
            alpha = int(self.alpha * 0.9)
            pygame.draw.line(window_surf, (int(20 + i * 0.1), int(20 + i * 0.05), int(40 + i * 0.2), alpha), (0, i), (ww, i))
        pygame.draw.rect(window_surf, (*GOLD, self.alpha), (0, 0, ww, wh), 4, border_radius=20)
        for x, y in [(0, 0), (ww, 0), (0, wh), (ww, wh)]: pygame.draw.circle(window_surf, (*GOLD, self.alpha), (x, y), 10, 2)
        title_surf = get_font(36, bold=True).render("ПРАВИЛА ИГРЫ", True, (*BRIGHT_GOLD, self.alpha))
        window_surf.blit(title_surf, title_surf.get_rect(center=(ww // 2, 40)))
        y_offset = 80 - self.scroll_y; line_height = 30
        for line in GAME_RULES:
            if y_offset + line_height > 0 and y_offset < wh - 40:
                if line and line[0].isdigit(): color = BRIGHT_EMERALD
                elif any(w in line for w in ["ПИСЬМО", "БУРА", "МОСКВА", "ПАДИК"]): color = BRIGHT_GOLD
                elif "•" in line: color = LIGHT_GRAY
                elif line == "": color = GRAY
                else: color = GOLD
                font = get_font(18, bold=bool(line and (line[0].isdigit() or "ПИСЬМО" in line)))
                text_surf = font.render(line, True, (*color, self.alpha))
                window_surf.blit(text_surf, text_surf.get_rect(center=(ww // 2, y_offset + line_height // 2)))
            y_offset += line_height
        screen.blit(window_surf, (wx, wy))
        if self.max_scroll > 0:
            pygame.draw.rect(screen, (*GRAY, self.alpha), pygame.Rect(wx + ww - 25, wy + 50, 10, wh - 100), border_radius=5)
            sy = wy + 50 + (self.scroll_y / self.max_scroll) * (wh - 100)
            self.scrollbar_rect = pygame.Rect(wx + ww - 27, sy, 14, 40)
            pygame.draw.rect(screen, (*GOLD, self.alpha), self.scrollbar_rect, border_radius=7)
        self.close_button.rect.x, self.close_button.rect.y = wx + ww - 30, wy + 10
        self.close_button.draw(screen)


class Player:
    def __init__(self, name, is_bot=False):
        self.name = name; self.is_bot = is_bot; self.hand = []; self.points = 0
        self.taken = []; self.selected_cards = []; self.hidden_cards = []
    def add_card(self, card):
        self.hand.append(card)
        self.hand.sort(key=lambda c: (SUITS.index(c.suit), RANKS.index(c.rank)))
    def play_card(self, index):
        if 0 <= index < len(self.hand):
            card = self.hand.pop(index); card.selected = False; return card
        return None
    def clear_selection(self):
        for card in self.selected_cards: card.selected = False
        self.selected_cards = []
    def can_beat(self, card_to_beat, my_card, trump):
        if my_card.suit == trump and card_to_beat.suit != trump: return True
        if my_card.suit == card_to_beat.suit: return my_card.value > card_to_beat.value
        return False
    def check_combinations(self, trump):
        if len(self.hand) < 3: return None
        ranks = [c.rank for c in self.hand]; suits = [c.suit for c in self.hand]
        if ranks.count('6') >= 3: return "ПАДИК", EMERALD, "padik", 5
        for suit in SUITS:
            if suit != trump and suits.count(suit) >= 3:
                cards = [c for c in self.hand if c.suit == suit][:3]
                return "ПИСЬМО", BROWN, "pismo", sum(c.value for c in cards)
        if ranks.count('A') >= 3: return "МОСКВА", PURPLE, "moskva", 0
        if suits.count(trump) >= 3: return "БУРА", RED, "bura", 0
        return None


# ============================================================
# ГЛАВНЫЙ КЛАСС ИГРЫ (ПОЛНЫЙ)
# ============================================================
class Game:
    def __init__(self):
        self.width = INITIAL_WIDTH; self.height = INITIAL_HEIGHT
        self.screen = set_game_mode(self.width, self.height, resizable=True)
        if not IS_IOS:
            pygame.display.set_caption("БУРА")
        try:
            icon = pygame.Surface((64, 64)); icon.fill(FOREST_GREEN)
            for i in range(4):
                angle = math.radians(i * 90)
                x, y = 32 + math.cos(angle) * 20, 32 + math.sin(angle) * 20
                pygame.draw.polygon(icon, GOLD, [(x, y - 8), (x + 8, y), (x, y + 8), (x - 8, y)], 2)
            pygame.display.set_icon(icon)
        except: pass
        self.clock = pygame.time.Clock()
        self.title_animation = None; self.victory_animation = None
        self.rules_window = RulesWindow(self.width, self.height)
        self.glow_effects = []
        self.floating_cards = [FloatingCard(self.width, self.height) for _ in range(30)]
        self.ambient_particles = [Particle(
            random.randint(0, self.width), random.randint(0, self.height),
            random.choice([GOLD, RED, DARK_GOLD, EMERALD, TURQUOISE]),
            (random.uniform(-0.15, 0.15), random.uniform(-0.15, 0.15)),
            random.randint(250, 350), random.choice(["circle", "diamond"])) for _ in range(50)]
        self.message = ""; self.message_timer = 0; self.message_color = WHITE
        self.selection_active = False; self.selection_start = (0, 0)
        self.selection_rect = None; self.selected_indices = set()
        # СОСТОЯНИЕ СТАВКИ
        self.state = "BETTING"
        self.slider = Slider(self.width // 2 - 200, 320, 400, 20, 0, 1000, 100) # <-- ДОБАВИТЬ ЭТО
        self.current_bet = 0  # <--- ДОБАВИТЬ ЭТО (запоминает ставку)
        self.payout_done = False
        self.running = True
        self.payout_done = False; self.running = True
        self.turn = None  # Инициализируем как None для безопасности
        self.player = None; self.bot = None
        self.create_buttons()

    def draw_betting_screen(self):
        self.screen.fill((20, 30, 20))
        self.slider.update_max(int(economy.rubles))

        title = get_font(64, bold=True).render("СДЕЛАЙТЕ СТАВКУ", True, GOLD)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 80))
        bal = get_font(36, bold=True).render(f"Баланс: {int(economy.rubles)} RUB", True, WHITE)
        self.screen.blit(bal, (self.width // 2 - bal.get_width() // 2, 160))

        # Ползунок
        self.slider.draw(self.screen)

        bet_text = get_font(48, bold=True).render(f"Ставка: {self.slider.val} RUB", True, BRIGHT_GOLD)
        self.screen.blit(bet_text, (self.width // 2 - bet_text.get_width() // 2, 360))

        btn_play = Button(self.width // 2 - 150, 440, 300, 70, "ИГРАТЬ", GOLD, corner_radius=20)
        btn_back = Button(20, 20, 120, 50, "НАЗАД", DARK_BLUE, corner_radius=12)

        for b in [btn_play, btn_back]:
            b.check_hover(get_pointer_pos())
            b.draw(self.screen)

    def setup_game(self):
        self.deck = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self.deck)
        self.trump = self.deck[-1].suit
        self.player = Player("Игрок"); self.bot = Player("Бот", True)
        self.title_animation = TitleAnimation(self.trump, self.width, self.height)
        for _ in range(3):
            self.player.add_card(self.deck.pop()); self.bot.add_card(self.deck.pop())
        self.table = []; self.animations = []; self.discard_pile = []; self.hidden_discard_pile = []
        self.turn = "player"; self.first_in_trick = None
        self.game_over = False; self.winner = None
        self.padik_used = False; self.pismo_used = False
        self.message = ""; self.message_timer = 0
        self.selection_active = False; self.selection_rect = None
        self.selected_indices.clear(); self.victory_animation = None
        self.rules_window.reset()
        self.show_message("Новая игра! Ваш ход", GOLD, 60)

    def create_buttons(self):
        bw, bh, sp = 150, 60, 15
        self.rules_button = Button(20, 20, 120, 50, "ПРАВИЛА", DARK_BLUE, corner_radius=12)
        start_x = self.width // 2 - (bw * 2 + sp) // 2
        self.buttons = [
            Button(start_x, 30, bw, bh, "НОВАЯ", DARK_BLUE, corner_radius=15),
            Button(start_x + bw + sp, 30, bw, bh, "ВЗЯТЬ", FOREST_GREEN, corner_radius=15)]
        self.buttons.append(Button(self.width // 2 - bw // 2, 110, bw, bh, "ВСКРЫТЬСЯ", DARK_GOLD, corner_radius=15))

    def update_buttons(self):
        if self.state != "PLAYING" or self.player is None: return
        for btn in self.buttons:
            if btn.text == "ВСКРЫТЬСЯ":
                btn.enabled = (len(self.player.hidden_cards) > 0 and self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation)
                btn.highlight = btn.enabled
            elif btn.text == "ВЗЯТЬ":
                btn.enabled = (len(self.player.hand) < 3 and len(self.deck) > 0 and self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation)
            elif btn.text == "НОВАЯ":
                btn.enabled = True

    def show_message(self, text, color=GOLD, duration=60):
        self.message = text; self.message_timer = duration; self.message_color = color

    def get_cards_in_rect(self, rect):
        indices = []
        for i, card in enumerate(self.player.hand):
            if rect.colliderect(pygame.Rect(50 + i * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70, CARD_WIDTH, CARD_HEIGHT)):
                indices.append(i)
        return indices

    def process_selection(self):
        if len(self.selected_indices) == 0: return
        selected_cards = [self.player.hand[i] for i in sorted(self.selected_indices)]
        self.selected_indices.clear()
        if len(selected_cards) == 3:
            self.player.selected_cards = selected_cards
            if self.player.check_combinations(self.trump): self.try_combo()
            else: self.player.clear_selection(); self.show_message("Нет комбинации", RED, 30)
        elif len(selected_cards) == 2:
            if selected_cards[0].suit == selected_cards[1].suit:
                self.player.selected_cards = selected_cards; self.discard_selected_cards()
            else: self.player.clear_selection(); self.show_message("Карты должны быть одной масти", RED, 30)
        else: self.player.clear_selection(); self.show_message("Выделите 2 или 3 карты", LIGHT_GRAY, 30)

    def handle_click(self, pos):
        # === ОБРАБОТКА ЭКРАНА СТАВКИ ===
        if self.state == "BETTING":
            btn_play = Button(self.width // 2 - 150, 440, 300, 70, "ИГРАТЬ", GOLD)
            btn_back = Button(20, 20, 120, 50, "НАЗАД", DARK_BLUE)

            if btn_play.rect.collidepoint(pos):
                bet = self.slider.val
                if bet > 0 and economy.spend_rubles(bet):
                    self.current_bet = bet  # <--- ЗАПОМИНАЕМ СТАВКУ
                    self.state = "PLAYING"
                    self.payout_done = False
                    self.setup_game()
                    self.create_buttons()
                    self.show_message(f"Ставка {bet} RUB принята!", GOLD, 60)
                else:
                    self.show_message("Недостаточно средств или ставка 0!", RED, 60)
            elif btn_back.rect.collidepoint(pos):
                self.running = False
            return  # <--- Важно! Выходим, чтобы не кликать по картам

        # === ОБЫЧНАЯ ИГРОВАЯ ЛОГИКА ===
        if self.rules_button.click(pos):
            self.rules_window.toggle()
            return

        if self.rules_window.active:
            if self.rules_window.handle_click(pos): return

        for btn in self.buttons:
            if btn.click(pos):
                if not btn.enabled: return
                if btn.text == "НОВАЯ":
                    self.setup_game()
                    self.create_buttons()
                    return
                elif btn.text == "ВЗЯТЬ":
                    self.take_card()
                    return
                elif btn.text == "ВСКРЫТЬСЯ":
                    self.reveal_hidden_points()
                    return

        if self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation:
            for i, card in enumerate(self.player.hand):
                if pygame.Rect(50 + i * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70, CARD_WIDTH,
                               CARD_HEIGHT).collidepoint(pos):
                    if self.selection_active: return
                    self.play_card(i)
                    return
            self.selection_active = True
            self.selection_start = pos
            self.selection_rect = pygame.Rect(pos[0], pos[1], 0, 0)
            self.selected_indices.clear()

    def discard_selected_cards(self):
        if len(self.player.selected_cards) != 2: self.show_message("Нужно выбрать 2 карты", RED, 30); return False
        if self.player.selected_cards[0].suit != self.player.selected_cards[1].suit:
            self.player.clear_selection(); self.show_message("Карты должны быть одной масти", RED, 30); return False
        suit = self.player.selected_cards[0].suit
        cards_to_discard = self.player.selected_cards.copy()
        current_table_len = len(self.table)
        for i, card in enumerate(cards_to_discard):
            idx = self.player.hand.index(card)
            card = self.player.play_card(idx); card.owner = "player"
            self.animations.append(AnimatedCard(card,
                (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                (self.width // 2 - CARD_WIDTH // 2 + (current_table_len + i) * 30, self.height // 2 - CARD_HEIGHT // 2 - 50), "player"))
            self.table.append(card)
        self.player.clear_selection(); self.turn = "bot"; self.first_in_trick = "player"
        self.show_message(f"Две {SUIT_NAMES[suit]} на столе", EMERALD, 30)
        for _ in range(30):
            self.glow_effects.append(GlowEffect(self.width // 2, self.height // 2, GOLD, 200, 30, pulse=True))
        return True

    def reveal_hidden_points(self):
        if len(self.player.hidden_cards) > 0:
            total_points = sum(card.value for card in self.player.hidden_cards)
            self.player.points += total_points
            hidden_count = len(self.player.hidden_cards)
            self.player.hidden_cards = []
            self.show_message(f"ВСКРЫТИЕ! +{total_points} очков ({hidden_count} карт)", GOLD, 90)
            for _ in range(60):
                self.glow_effects.append(GlowEffect(
                    random.randint(0, self.width), random.randint(0, self.height),
                    GOLD, random.randint(80, 200), random.randint(25, 40), pulse=True))
                self.ambient_particles.append(Particle(
                    random.randint(0, self.width), random.randint(0, self.height),
                    GOLD, (random.uniform(-3, 3), random.uniform(-4, -2)), random.randint(50, 80),
                    random.choice(["circle", "diamond", "star"])))
            self.game_over = True
            if self.player.points >= 31:
                self.winner = "player"; self.victory_animation = VictoryAnimation("player", "ПОБЕДА", self.width, self.height)
            else:
                self.winner = "bot"; self.victory_animation = VictoryAnimation("bot", "ПОРАЖЕНИЕ", self.width, self.height)

    def play_card(self, idx):
        if self.game_over or self.turn != "player" or self.title_animation or self.victory_animation: return
        card = self.player.play_card(idx)
        if self.table:
            last_card = self.table[-1]
            if last_card.owner == "player": self.player.hand.insert(idx, card); return
            if self.player.can_beat(last_card, card, self.trump):
                card.owner = "player"
                self.animations.append(AnimatedCard(card,
                    (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                    (self.width // 2 - CARD_WIDTH // 2 + len(self.table) * 25, self.height // 2 - CARD_HEIGHT // 2 - 50), "player"))
                self.table.append(card)
                if len(self.table) == 2:
                    points = sum(c.value for c in self.table)
                    self.player.points += points
                    self.player.taken.extend(self.table)
                    for c in self.table: self.discard_pile.append(c)
                    self.table = []; self.first_in_trick = None; self.turn = "player"
                    self.refill_hands()
                    self.show_message(f"Вы взяли взятку! +{points}", EMERALD, 30)
                else: self.turn = "bot"
            else:
                bot_card = last_card; points = bot_card.value
                self.bot.points += points; self.bot.taken.append(bot_card)
                card.owner = "discard"
                self.animations.append(AnimatedCard(card,
                    (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                    (250 + len(self.discard_pile) * 6, self.height - 350),
                    "discard", discarded=True, hidden_points=False))
                self.discard_pile.extend([bot_card, card])
                self.table = []; self.first_in_trick = None; self.turn = "bot"
                self.refill_hands()
                self.show_message(f"Не побил! Бот получает +{points}", DARK_GOLD, 45)
                if self.bot.points >= 31:
                    self.game_over = True; self.winner = "bot"
                    self.victory_animation = VictoryAnimation("bot", "ПОРАЖЕНИЕ", self.width, self.height)
                return
        else:
            card.owner = "player"
            self.animations.append(AnimatedCard(card,
                (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                (self.width // 2 - CARD_WIDTH // 2 + len(self.table) * 25, self.height // 2 - CARD_HEIGHT // 2 - 50), "player"))
            self.table.append(card); self.first_in_trick = "player"; self.turn = "bot"

    def try_combo(self):
        combo = self.player.check_combinations(self.trump)
        if not combo: return
        name, color, ctype, points = combo
        if ctype in ["bura", "moskva"]:
            self.game_over = True; self.winner = "player"
            self.victory_animation = VictoryAnimation("player", f"{name}! ПОБЕДА", self.width, self.height); return
        elif ctype == "padik" and not self.padik_used:
            cards_to_remove = []
            for card in self.player.hand[:]:
                if card.rank == '6' and len(cards_to_remove) < 3: cards_to_remove.append(card)
            for card in cards_to_remove:
                idx = self.player.hand.index(card); card = self.player.play_card(idx)
                self.animations.append(AnimatedCard(card,
                    (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                    (240 + len(self.discard_pile) * 6, self.height - 320 + len(self.discard_pile) * 6),
                    "discard", discarded=True, hidden_points=False))
                self.discard_pile.append(card)
            self.player.points += points; self.padik_used = True
            self.show_message(f"{name}! +{points} очков", color, 45)
            if self.player.points >= 31:
                self.game_over = True; self.winner = "player"
                self.victory_animation = VictoryAnimation("player", "ПОБЕДА", self.width, self.height)
            return
        elif ctype == "pismo" and not self.pismo_used:
            cards_to_discard = [c for c in self.player.hand if c.suit != self.trump][:3]
            player_cards = cards_to_discard.copy()
            player_points = sum(card.value for card in player_cards)
            for card in cards_to_discard:
                idx = self.player.hand.index(card); card = self.player.play_card(idx)
                self.animations.append(AnimatedCard(card,
                    (50 + idx * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70),
                    (self.width // 2 - CARD_WIDTH // 2 + len(self.table) * 25, self.height // 2 - CARD_HEIGHT // 2 - 50), "player"))
                self.table.append(card)
            temp_hand = self.bot.hand.copy(); all_beat = True; cards_needed = []
            for player_card in player_cards:
                found = False
                for i, bot_card in enumerate(temp_hand):
                    if self.bot.can_beat(player_card, bot_card, self.trump):
                        cards_needed.append(bot_card); temp_hand.pop(i); found = True; break
                if not found: all_beat = False; break
            if all_beat and len(cards_needed) == 3:
                bot_points = sum(card.value for card in cards_needed)
                self.bot.points += player_points + bot_points
                self.show_message(f"Бот побил письмо! +{player_points + bot_points} очков", RED, 45)
                for bc in cards_needed:
                    if bc in self.bot.hand: self.bot.hand.remove(bc)
            else:
                self.player.points += player_points
                self.show_message(f"{name}! +{player_points} очков", color, 45)
                for bc in self.bot.hand[:]:
                    self.player.hidden_cards.append(bc); self.hidden_discard_pile.append(bc)
                self.bot.hand.clear()
            self.pismo_used = True
            for card in self.table: self.discard_pile.append(card)
            self.table = []
            for _ in range(3):
                if self.deck: self.player.add_card(self.deck.pop())
                if self.deck: self.bot.add_card(self.deck.pop())
            if len(self.deck) < 6 and self.discard_pile:
                self.deck.extend(self.discard_pile); random.shuffle(self.deck); self.discard_pile = []
            if self.player.points >= 31:
                self.game_over = True; self.winner = "player"
                self.victory_animation = VictoryAnimation("player", "ПОБЕДА", self.width, self.height)
            elif self.bot.points >= 31:
                self.game_over = True; self.winner = "bot"
                self.victory_animation = VictoryAnimation("bot", "ПОРАЖЕНИЕ", self.width, self.height)
            return

    def take_card(self):
        if self.game_over or self.turn != "player" or self.title_animation or self.victory_animation: return
        if len(self.player.hand) < 3 and self.deck:
            card = self.deck.pop(); self.player.add_card(card)
            self.show_message(f"Взята {card.rank}{card.suit}", EMERALD, 30)
            for _ in range(10):
                self.glow_effects.append(GlowEffect(self.width - 400, self.height // 2 - 100, GOLD, 100, 15, pulse=True))
        else: self.show_message("Нельзя взять карту", RED, 30)

    def bot_turn(self):
        if not self.bot.hand or self.game_over or self.title_animation or self.victory_animation or self.animations: return
        if len(self.table) == 2:
            player_cards = self.table.copy()
            player_points = sum(card.value for card in player_cards)
            temp_hand = self.bot.hand.copy(); can_beat_both = True; cards_needed = []
            for pc in player_cards:
                found = False
                for i, bc in enumerate(temp_hand):
                    if self.bot.can_beat(pc, bc, self.trump):
                        cards_needed.append(bc); temp_hand.pop(i); found = True; break
                if not found: can_beat_both = False; break
            if can_beat_both and len(cards_needed) == 2:
                bot_points = sum(card.value for card in cards_needed)
                self.bot.points += player_points + bot_points
                self.show_message(f"Бот побил карты! +{player_points + bot_points} очков", RED, 30)
                for bc in cards_needed:
                    if bc in self.bot.hand: self.bot.hand.remove(bc)
                for c in player_cards: self.discard_pile.append(c)
                self.table = []; self.first_in_trick = None; self.turn = "bot"
            else:
                self.player.points += player_points
                self.show_message(f"Бот не побил! +{player_points} игроку, карты бота в скрытые", EMERALD, 30)
                cards_to_hide = []
                for _ in range(min(2, len(self.bot.hand))):
                    if self.bot.hand:
                        bc = min(self.bot.hand, key=lambda c: c.value)
                        cards_to_hide.append(bc); self.bot.hand.remove(bc)
                for bc in cards_to_hide:
                    self.player.hidden_cards.append(bc)
                    self.animations.append(AnimatedCard(bc, (self.width - 180, 60),
                        (400 + len(self.hidden_discard_pile) * 5, self.height - 250 + len(self.hidden_discard_pile) * 5),
                        "hidden", discarded=True, hidden_points=True))
                    self.hidden_discard_pile.append(bc)
                for c in player_cards: self.discard_pile.append(c)
                self.table = []; self.first_in_trick = None; self.turn = "player"
            self.refill_hands()
        elif len(self.table) == 1:
            last_card = self.table[-1]
            if self.first_in_trick == "player":
                beat_card = None; beat_idx = -1
                for i, c in enumerate(self.bot.hand):
                    if self.bot.can_beat(last_card, c, self.trump):
                        if not beat_card or c.value < beat_card.value: beat_card = c; beat_idx = i
                if beat_card:
                    card = self.bot.play_card(beat_idx); card.owner = "bot"
                    self.animations.append(AnimatedCard(card,
                        (self.width - 180 - beat_idx * (CARD_WIDTH + 30), 60),
                        (self.width // 2 - CARD_WIDTH // 2 + len(self.table) * 25, self.height // 2 - CARD_HEIGHT // 2 - 50), "bot"))
                    self.table.append(card)
                    self.show_message(f"Бот бьет {card.rank}{card.suit}", RED, 30)
                    if len(self.table) == 2:
                        points = sum(c.value for c in self.table)
                        self.bot.points += points; self.bot.taken.extend(self.table)
                        for c in self.table: self.discard_pile.append(c)
                        self.table = []; self.first_in_trick = None; self.turn = "bot"
                        self.refill_hands()
                        self.show_message(f"Бот взял взятку! +{points}", RED, 30)
                else:
                    player_points = last_card.value
                    self.player.points += player_points; self.player.taken.append(last_card)
                    if self.bot.hand:
                        bc = min(self.bot.hand, key=lambda c: c.value)
                        idx = self.bot.hand.index(bc); bc = self.bot.play_card(idx)
                        self.player.hidden_cards.append(bc)
                        self.animations.append(AnimatedCard(bc, (self.width - 180 - idx * (CARD_WIDTH + 30), 60),
                            (400 + len(self.hidden_discard_pile) * 5, self.height - 250 + len(self.hidden_discard_pile) * 5),
                            "hidden", discarded=True, hidden_points=True))
                        self.hidden_discard_pile.append(bc)
                        self.show_message(f"Бот не побил! +{player_points} игроку, карта бота в скрытые", DARK_GOLD, 45)
                    else: self.show_message(f"Бот не побил! +{player_points} игроку", DARK_GOLD, 45)
                    self.discard_pile.append(last_card); self.table = []; self.first_in_trick = None
                    self.turn = "player"; self.refill_hands()
            else: self.turn = "player"
        else:
            min_card = min(self.bot.hand, key=lambda c: (c.suit != self.trump, c.value))
            idx = self.bot.hand.index(min_card); card = self.bot.play_card(idx); card.owner = "bot"
            self.animations.append(AnimatedCard(card,
                (self.width - 180 - idx * (CARD_WIDTH + 30), 60),
                (self.width // 2 - CARD_WIDTH // 2, self.height // 2 - CARD_HEIGHT // 2 - 50), "bot"))
            self.table.append(card); self.first_in_trick = "bot"; self.turn = "player"
            self.show_message(f"Бот: {card.rank}{card.suit}", RED, 30)
        if self.player.points >= 31:
            self.game_over = True; self.winner = "player"
            self.victory_animation = VictoryAnimation("player", "ПОБЕДА", self.width, self.height)
        elif self.bot.points >= 31:
            self.game_over = True; self.winner = "bot"
            self.victory_animation = VictoryAnimation("bot", "ПОРАЖЕНИЕ", self.width, self.height)

    def refill_hands(self):
        while len(self.player.hand) < 3 and self.deck: self.player.add_card(self.deck.pop())
        while len(self.bot.hand) < 3 and self.deck: self.bot.add_card(self.deck.pop())

    def draw_score(self):
        px, py, pw, ph = self.width - 400, self.height - 280, 360, 240
        panel_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for i in range(ph):
            alpha = 200 - i // 2
            pygame.draw.line(panel_surf, (0, max(60 - i // 10, 20), 0, alpha), (0, i), (pw, i))
        self.screen.blit(panel_surf, (px, py))
        pygame.draw.rect(self.screen, GOLD, (px, py, pw, ph), 4, border_radius=20)
        pygame.draw.rect(self.screen, DARK_GOLD, (px + 2, py + 2, pw - 4, ph - 4), 2, border_radius=18)
        for x, y in [(px, py), (px + pw, py), (px, py + ph), (px + pw, py + ph)]:
            pygame.draw.circle(self.screen, GOLD, (x, y), 6, 2)
        draw_text(self.screen, "СЧЕТ", px + pw // 2, py + 40, 42, GOLD, bold=True, glow=True)
        p_col = GOLD if self.turn == "player" else WHITE
        b_col = GOLD if self.turn == "bot" else WHITE
        draw_text(self.screen, "ИГРОК", px + 100, py + 90, 30, p_col, False, bold=True)
        draw_text(self.screen, str(self.player.points), px + 110, py + 130, 48, p_col, False, bold=True, glow=True)
        draw_text(self.screen, "БОТ", px + 230, py + 90, 30, b_col, False, bold=True)
        draw_text(self.screen, str(self.bot.points), px + 240, py + 130, 48, b_col, False, bold=True, glow=True)
        bar_y = py + 210
        pygame.draw.rect(self.screen, (40, 40, 40), (px + 45, bar_y, 120, 12), border_radius=6)
        pygame.draw.rect(self.screen, EMERALD, (px + 45, bar_y, min(120 * self.player.points / 31, 120), 12), border_radius=6)
        pygame.draw.rect(self.screen, (40, 40, 40), (px + 190, bar_y, 120, 12), border_radius=6)
        pygame.draw.rect(self.screen, RED, (px + 190, bar_y, min(120 * self.bot.points / 31, 120), 12), border_radius=6)
        draw_text(self.screen, "31", px + pw // 2, bar_y + 20, 20, GOLD, bold=True)

    def draw_table_ornament(self, cx, cy):
        for i in range(0, 360, 30):
            angle = math.radians(i)
            pygame.draw.line(self.screen, DARK_GOLD,
                (cx + math.cos(angle) * 300, cy + math.sin(angle) * 150),
                (cx + math.cos(angle) * 330, cy + math.sin(angle) * 165), 2)
        for i in range(12):
            angle = math.radians(i * 30)
            x, y = cx + math.cos(angle) * 280, cy + math.sin(angle) * 140
            pygame.draw.polygon(self.screen, GOLD, [(x, y - 12), (x + 12, y), (x, y + 12), (x - 12, y)], 2)
            pygame.draw.circle(self.screen, GOLD, (int(x), int(y)), 4, 1)
        for i in range(8):
            angle = math.radians(i * 45)
            pygame.draw.circle(self.screen, GOLD, (int(cx + math.cos(angle) * 200), int(cy + math.sin(angle) * 100)), 10, 1)
#economy.add_rubles(self.bet_amount * 2)
    def draw(self):
        if self.state == "BETTING":
            self.draw_betting_screen()
            return
        for i in range(self.height):
            factor = 1 - i / self.height * 0.4
            pygame.draw.line(self.screen, (max(5, int(20 * factor)), max(20, int(70 * factor)), max(10, int(35 * factor))), (0, i), (self.width, i))
        for card in self.floating_cards: card.update(); card.draw(self.screen)
        self.ambient_particles = [p for p in self.ambient_particles if p.update()]
        for p in self.ambient_particles: p.draw(self.screen)
        while len(self.ambient_particles) < 50:
            self.ambient_particles.append(Particle(
                random.randint(0, self.width), random.randint(0, self.height),
                random.choice([GOLD, RED, DARK_GOLD, EMERALD, TURQUOISE]),
                (random.uniform(-0.15, 0.15), random.uniform(-0.15, 0.15)),
                random.randint(250, 350), random.choice(["circle", "diamond"])))
        cx, cy = self.width // 2, self.height // 2
        table_rect = pygame.Rect(cx - 350, cy - 180, 700, 360)
        for i in range(5):
            offset = i * 2; shadow_rect = table_rect.copy()
            shadow_rect.x += offset; shadow_rect.y += offset
            alpha = 40 - i * 8
            if alpha > 0: pygame.draw.ellipse(self.screen, (0, 0, 0, alpha), shadow_rect)
        table_surf = pygame.Surface((700, 360), pygame.SRCALPHA)
        for i in range(360):
            pygame.draw.ellipse(table_surf, (0, 80 + i * 0.2, 0, 200 - i * 0.4), (0, 0, 700, 360 - i), 1)
        pygame.draw.ellipse(table_surf, GOLD, (0, 0, 700, 360), 4)
        self.screen.blit(table_surf, (cx - 350, cy - 180))
        self.draw_table_ornament(cx, cy)
        if self.hidden_discard_pile:
            for i, card in enumerate(self.hidden_discard_pile[-4:]):
                draw_card(self.screen, card, 400 + i * 5, self.height - 250 + i * 5, back=True)
            pygame.draw.rect(self.screen, DARK_GOLD, (390, self.height - 260, 170, 140), 4, border_radius=12)
        if self.discard_pile:
            for i, card in enumerate(self.discard_pile[-4:]):
                draw_card(self.screen, card, 240 + i * 6, self.height - 320 + i * 6)
            pygame.draw.rect(self.screen, BROWN, (230, self.height - 330, 200, 160), 4, border_radius=12)
            draw_text(self.screen, f"СБРОС: {len(self.discard_pile)}", 330, self.height - 250, 22, LIGHT_GRAY, bold=True)
        for i, card in enumerate(self.player.hand):
            draw_card(self.screen, card, 50 + i * (CARD_WIDTH + 30), self.height - CARD_HEIGHT - 70,
                highlight=(self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation),
                selected=card in self.player.selected_cards)
        for i in range(len(self.bot.hand)):
            draw_card(self.screen, None, self.width - 180 - i * (CARD_WIDTH + 30), 60, back=True)
        cards_in_animation = set(anim.card for anim in self.animations if hasattr(anim, 'card') and anim.card and anim.active)
        for i, card in enumerate(self.table):
            if card not in cards_in_animation and not hasattr(card, 'instant_added'):
                draw_card(self.screen, card, cx - CARD_WIDTH // 2 + i * 30, cy - CARD_HEIGHT // 2 - 50, glow=True)
        for anim in self.animations[:]:
            anim.update(); anim.draw(self.screen)
            if not anim.active:
                if hasattr(anim, 'card') and anim.card and hasattr(anim.card, 'instant_added'):
                    delattr(anim.card, 'instant_added')
                self.animations.remove(anim)
        for glow in self.glow_effects[:]:
            glow.update(); glow.draw(self.screen)
            if not glow.active: self.glow_effects.remove(glow)
        trump_x, trump_y = self.width - 280, cy - 150
        pygame.draw.rect(self.screen, (0, 50, 0), (trump_x - 5, trump_y - 5, 170, 230), border_radius=15)
        draw_card(self.screen, Card('A', self.trump), trump_x, trump_y, glow=True)
        draw_text(self.screen, "КОЗЫРЬ", trump_x + 80, trump_y - 30, 24, GOLD, bold=True, glow=True)
        draw_text(self.screen, SUIT_NAMES[self.trump], trump_x + 80, trump_y + 200, 20, GOLD, bold=True)
        if self.deck:
            deck_x, deck_y = self.width - 480, cy - 150
            pygame.draw.rect(self.screen, (0, 40, 0), (deck_x - 5, deck_y - 5, 170, 230), border_radius=12)
            draw_card(self.screen, None, deck_x, deck_y, back=True)
            draw_text(self.screen, str(len(self.deck)), deck_x + 75, deck_y + 210, 26, WHITE, bold=True)
        self.draw_score()
        self.rules_button.check_hover(get_pointer_pos()); self.rules_button.draw(self.screen)
        for btn in self.buttons: btn.check_hover(get_pointer_pos()); btn.draw(self.screen)
        self.rules_window.update(); self.rules_window.draw(self.screen)
        if self.selection_active and self.selection_rect:
            surf = pygame.Surface((self.selection_rect.width, self.selection_rect.height), pygame.SRCALPHA)
            surf.fill((0, 120, 255, 40))
            self.screen.blit(surf, (self.selection_rect.x, self.selection_rect.y))
            pygame.draw.rect(self.screen, (0, 160, 255), self.selection_rect, 2)
        combo = self.player.check_combinations(self.trump)
        if combo and self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation:
            name, color, ctype, points = combo
            bonus = "ПОБЕДА" if ctype in ["bura", "moskva"] else (f"+{points} ОЧКОВ" if ctype in ["padik", "pismo"] else "")
            draw_text(self.screen, f"{name}! {bonus}", self.width // 2, 210, 34, color, bold=True, glow=True)
        if self.turn == "player" and not self.game_over and not self.title_animation and not self.victory_animation:
            draw_text(self.screen, "ВАШ ХОД", self.width // 2, 260, 42, GOLD, bold=True, glow=True)
        elif self.turn == "bot" and not self.game_over and not self.title_animation and not self.victory_animation:
            draw_text(self.screen, "ХОД БОТА", self.width // 2, 260, 42, RED, bold=True, glow=True)
        if self.message and self.message_timer > 0:
            self.message_timer -= 1
            draw_text(self.screen, self.message, self.width // 2, self.height - 110, 38, self.message_color, bold=True, glow=True)
        if self.title_animation:
            self.title_animation.update(); self.title_animation.draw(self.screen, self.trump)
            if not self.title_animation.active: self.title_animation = None
        if self.victory_animation:
            self.victory_animation.update(); self.victory_animation.draw(self.screen)
            if self.victory_animation.active:
                btn = Button(self.width // 2 - 150, self.height // 2 + 150, 300, 75, "СЫГРАТЬ СНОВА", DARK_GOLD, corner_radius=20)
                btn.check_hover(get_pointer_pos()); btn.draw(self.screen)
                if btn.rect.collidepoint(get_pointer_pos()) and pygame.mouse.get_pressed()[0]:
                    if self.winner == "player" and not self.payout_done:
                        economy.add_rubles(self.current_bet * 2)
                        self.payout_done = True
                    self.state = "BETTING"; self.bet_amount = 100
                    self.payout_done = False; self.victory_animation = None

    def run(self):
        self.running = True
        bot_timer = 0
        while self.running:
            dt = self.clock.tick(FPS) / 1000
            for event in get_input_events():
                if event.type == pygame.QUIT:
                    self.running = False

                # 1. Сначала отдаем событие ползунку (только для мыши и только на экране ставки)
                if self.state == "BETTING" and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                                                              pygame.MOUSEMOTION):
                    if self.slider.handle_event(event):
                        continue  # Если ползунок обработал, пропускаем остальное

                # 2. Обработка остальных событий
                if event.type == pygame.VIDEORESIZE and not IS_IOS:
                    self.width, self.height = event.w, event.h
                    self.screen = set_game_mode(self.width, self.height, resizable=True)
                    self.create_buttons()
                    self.rules_window.width, self.rules_window.height = self.width, self.height
                    for card in self.floating_cards:
                        card.width, card.height = self.width, self.height

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_click(event.pos)
                    elif event.button == 4:
                        self.rules_window.handle_scroll(-20)
                    elif event.button == 5:
                        self.rules_window.handle_scroll(20)

                    if self.victory_animation and self.victory_animation.active:
                        btn_rect = pygame.Rect(self.width // 2 - 150, self.height // 2 + 150, 300, 75)
                        if btn_rect.collidepoint(event.pos):
                            if self.winner == "player" and not self.payout_done:
                                economy.add_rubles(self.current_bet * 2)  # <--- ИСПОЛЬЗУЕМ CURRENT_BET
                                self.payout_done = True
                            self.state = "BETTING"
                            self.payout_done = False
                            self.victory_animation = None
                            continue

                elif event.type == pygame.MOUSEWHEEL:
                    if self.rules_window.active:
                        self.rules_window.handle_scroll(-event.y * 20)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and self.selection_active:
                        self.selection_active = False
                        if self.selection_rect and self.selection_rect.width > 10 and self.selection_rect.height > 10:
                            self.selected_indices = set(self.get_cards_in_rect(self.selection_rect))
                            self.process_selection()
                        self.selection_rect = None
                    self.rules_window.handle_mouse_up()

                elif event.type == pygame.MOUSEMOTION:
                    if self.selection_active:
                        x1, y1 = self.selection_start
                        x2, y2 = event.pos
                        self.selection_rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                    self.rules_window.handle_mouse_move(event.pos)

            if self.state == "PLAYING" and self.turn == "bot" and not self.animations and not self.game_over and not self.title_animation and not self.victory_animation:
                bot_timer += dt
                if bot_timer > 0.5:
                    self.bot_turn()
                    bot_timer = 0
            else:
                bot_timer = 0

            if self.state == "PLAYING":
                self.update_buttons()

            self.draw()
            pygame.display.flip()


# ==============================================================================
# 8. ГЛАВНОЕ МЕНЮ
# ==============================================================================
# ==============================================================================
# 9. СИНДИКАТ (ПУШКА ДЛЯ МИЛЛИАРДЕРОВ)
# ==============================================================================
class SyndicateGame:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("СИНДИКАТ: Алтарь Богатства")
        self.clock = pygame.time.Clock()
        self.running = True

        self.min_bet = 1000000
        self.max_bet = 17102026000  # 1000 Divine
        self.slider = Slider(150, 550, 600, 20, self.min_bet, self.max_bet, self.min_bet)

        self.is_buying = False
        self.shake_timer = 0
        self.flash_timer = 0
        self.particles = []
        self.won_text = ""
        self.won_timer = 0

        self.font_main = pygame.font.SysFont("Arial", 36, bold=True)
        self.font_big = pygame.font.SysFont("Arial", 64, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 20)
        self.font_huge = pygame.font.SysFont("Arial", 80, bold=True)

    def handle_click(self, pos):
        if self.is_buying: return
        if pygame.Rect(20, 20, 120, 50).collidepoint(pos): self.running = False; return

        if pygame.Rect(770, 540, 100, 40).collidepoint(pos):
            self.slider.val = min(int(economy.rubles), self.slider.max_val)
            self.slider.val = max(self.slider.val, self.slider.min_val)

        if pygame.Rect(300, 600, 400, 70).collidepoint(pos):
            self.buy()

    def buy(self):
        bet = self.slider.val
        if economy.rubles >= bet:
            economy.spend_rubles(bet)
            exact_divine = bet / 17102026.0
            divine_amount = int(exact_divine)
            if random.random() < (exact_divine - divine_amount):
                divine_amount += 1
            if divine_amount > 0:
                for _ in range(divine_amount):
                    economy.dice_inventory.append("Divine")
                economy.save_game()

            self.is_buying = True
            self.shake_timer = 60
            self.flash_timer = 30
            self.won_text = f"+{divine_amount} DIVINE!"
            self.won_timer = 180

            for _ in range(250):
                self.particles.append(Particle(
                    self.width // 2, self.height // 2,
                    random.choice([GOLD, BRIGHT_GOLD, WHITE]),
                    (random.uniform(-18, 18), random.uniform(-18, 18)),
                    random.randint(60, 140),
                    random.choice(["circle", "diamond", "star"])
                ))
        else:
            self.won_text = "НЕДОСТАТОЧНО СРЕДСТВ!"
            self.won_timer = 60

    def update(self):
        if self.shake_timer > 0: self.shake_timer -= 1
        if self.flash_timer > 0: self.flash_timer -= 1
        if self.won_timer > 0: self.won_timer -= 1
        if self.won_timer == 0: self.is_buying = False
        self.particles = [p for p in self.particles if p.update()]

    def draw(self):
        offset_x = random.randint(-15, 15) if self.shake_timer > 0 else 0
        offset_y = random.randint(-15, 15) if self.shake_timer > 0 else 0
        draw_gradient_background(self.screen, (20, 0, 0), (5, 5, 5))

        self.screen.blit(self.font_main.render(f"Баланс: {int(economy.rubles)} RUB", True, WHITE), (20, 20))
        pygame.draw.rect(self.screen, GRAY, (20, 70, 120, 50), border_radius=10)
        self.screen.blit(self.font_small.render("НАЗАД", True, WHITE), (50, 85))

        title = self.font_huge.render("СИНДИКАТ", True, GOLD)
        self.screen.blit(title, title.get_rect(center=(self.width // 2 + offset_x, 100 + offset_y)))

        self.slider.update_max(int(economy.rubles))
        self.slider.draw(self.screen)

        bet_amount = self.slider.val
        exact_divine = bet_amount / 17102026.0
        divine_to_get = int(exact_divine)
        chance = int((exact_divine - divine_to_get) * 100)

        bet_str = f"{bet_amount:,}".replace(",", " ")

        bet_text = self.font_main.render(f"Ставка: {bet_str} RUB", True, WHITE)
        self.screen.blit(bet_text, bet_text.get_rect(center=(self.width // 2 + offset_x, 480 + offset_y)))

        get_text = self.font_main.render(f"Вы получите: {divine_to_get} DIVINE (+{chance}% шанс на 1)", True, GOLD)
        self.screen.blit(get_text, get_text.get_rect(center=(self.width // 2 + offset_x, 520 + offset_y)))

        pygame.draw.rect(self.screen, BLUE, (770, 540, 100, 40), border_radius=5)
        self.screen.blit(self.font_small.render("МАКС", True, WHITE), (800, 550))

        pygame.draw.rect(self.screen, GOLD, (300 + offset_x, 600 + offset_y, 400, 70), border_radius=15)
        btn_text = self.font_main.render("ВЛОЖИТЬ ВСЁ", True, BLACK)
        self.screen.blit(btn_text, btn_text.get_rect(center=(500 + offset_x, 635 + offset_y)))

        if self.won_timer > 0:
            res_surf = self.font_big.render(self.won_text, True, GOLD)
            for dx, dy in [(-4, -4), (4, -4), (-4, 4), (4, 4)]:
                self.screen.blit(res_surf, res_surf.get_rect(center=(self.width // 2 + dx, 300 + dy)))
            self.screen.blit(res_surf, res_surf.get_rect(center=(self.width // 2, 300)))

        if self.flash_timer > 0:
            flash_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            alpha = int((self.flash_timer / 30) * 255)
            flash_surf.fill((255, 255, 255, alpha))
            self.screen.blit(flash_surf, (0, 0))

        for p in self.particles: p.draw(self.screen)
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in get_input_events():
                if event.type == pygame.QUIT: self.running = False
                if self.slider.handle_event(event): continue
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: self.handle_click(event.pos)
            self.update()
            self.draw()
            self.clock.tick(60)


# ==============================================================================
# 10. ФУНКЦИЯ РИСОВАНИЯ ПЕРСОНАЖА (ДЕТАЛИЗИРОВАННАЯ)
# ==============================================================================
def draw_rich_guy(surface, cx, cy, owned_items):
    # Ноги (Джинсы/Брюки)
    pygame.draw.rect(surface, (20, 20, 30), (cx - 25, cy + 30, 20, 60), border_radius=5)
    pygame.draw.rect(surface, (20, 20, 30), (cx + 5, cy + 30, 20, 60), border_radius=5)

    # Обувь (Кроссовки/Туфли)
    if "sneakers" in owned_items:
        pygame.draw.ellipse(surface, (255, 255, 255), (cx - 35, cy + 80, 35, 20))
        pygame.draw.ellipse(surface, (255, 255, 255), (cx, cy + 80, 35, 20))
        pygame.draw.ellipse(surface, RED, (cx - 25, cy + 85, 15, 5))
        pygame.draw.ellipse(surface, RED, (cx + 10, cy + 85, 15, 5))
    else:
        pygame.draw.ellipse(surface, (0, 0, 0), (cx - 30, cy + 85, 30, 15))
        pygame.draw.ellipse(surface, (0, 0, 0), (cx, cy + 85, 30, 15))

    # Руки
    pygame.draw.rect(surface, (255, 200, 150), (cx - 55, cy - 10, 15, 50), border_radius=5)
    pygame.draw.rect(surface, (255, 200, 150), (cx + 40, cy - 10, 15, 50), border_radius=5)

    # Часы на руке
    if "watch" in owned_items:
        pygame.draw.rect(surface, GOLD, (cx + 40, cy + 20, 15, 10), border_radius=2)
        pygame.draw.circle(surface, WHITE, (cx + 47, cy + 25), 3)

    # Торс (Одежда)
    if "suit" in owned_items:
        # Золотой костюм
        pygame.draw.rect(surface, (218, 165, 32), (cx - 40, cy - 20, 80, 60), border_radius=10)
        pygame.draw.polygon(surface, WHITE, [(cx - 15, cy - 20), (cx + 15, cy - 20), (cx, cy + 10)])  # Рубашка
        pygame.draw.polygon(surface, BLACK, [(cx - 5, cy - 20), (cx + 5, cy - 20), (cx, cy + 10)])  # Галстук
    elif "jacket" in owned_items:
        # Кожаная куртка
        pygame.draw.rect(surface, (80, 40, 20), (cx - 40, cy - 20, 80, 60), border_radius=10)
        pygame.draw.line(surface, (200, 200, 200), (cx, cy - 20), (cx, cy + 40), 3)  # Молния
    else:
        # Обычная футболка
        pygame.draw.rect(surface, (50, 50, 70), (cx - 40, cy - 20, 80, 60), border_radius=10)

    # Голова
    pygame.draw.circle(surface, (255, 200, 150), (cx, cy - 50), 30)

    # Волосы
    pygame.draw.arc(surface, (40, 20, 10), (cx - 32, cy - 82, 64, 60), 0, math.pi, 10)

    # Глаза (смотрят в сторону)
    pygame.draw.circle(surface, BLACK, (cx - 8, cy - 55), 3)
    pygame.draw.circle(surface, BLACK, (cx + 12, cy - 55), 3)

    # Улыбка
    pygame.draw.arc(surface, (200, 50, 50), (cx - 10, cy - 40, 20, 15), math.pi, 2 * math.pi, 2)

    # Очки
    if "glasses" in owned_items:
        pygame.draw.rect(surface, BLACK, (cx - 25, cy - 65, 20, 15), border_radius=3)
        pygame.draw.rect(surface, BLACK, (cx + 5, cy - 65, 20, 15), border_radius=3)
        pygame.draw.line(surface, BLACK, (cx - 5, cy - 55), (cx + 5, cy - 55), 2)

    # Цепь
    if "chain" in owned_items:
        pygame.draw.arc(surface, GOLD, (cx - 30, cy - 15, 60, 40), math.pi, 2 * math.pi, 5)
        pygame.draw.circle(surface, GOLD, (cx, cy + 20), 8)

    # Корона
    if "crown" in owned_items:
        pygame.draw.polygon(surface, GOLD, [
            (cx - 35, cy - 75), (cx - 20, cy - 100), (cx, cy - 80), (cx + 20, cy - 100), (cx + 35, cy - 75)
        ])
        pygame.draw.circle(surface, RED, (cx - 20, cy - 100), 5)
        pygame.draw.circle(surface, BLUE, (cx, cy - 80), 5)
        pygame.draw.circle(surface, RED, (cx + 20, cy - 100), 5)

    # Крылья (сзади)
    if "wings" in owned_items:
        pygame.draw.polygon(surface, WHITE,
                            [(cx - 40, cy - 10), (cx - 130, cy - 70), (cx - 100, cy + 40), (cx - 40, cy + 40)])
        pygame.draw.polygon(surface, WHITE,
                            [(cx + 40, cy - 10), (cx + 130, cy - 70), (cx + 100, cy + 40), (cx + 40, cy + 40)])

    # Нимб
    if "halo" in owned_items:
        pygame.draw.ellipse(surface, GOLD, (cx - 30, cy - 110, 60, 15), 4)
        pygame.draw.ellipse(surface, BRIGHT_GOLD, (cx - 28, cy - 108, 56, 11), 2)

    # Джетпак
    if "jetpack" in owned_items:
        pygame.draw.rect(surface, (150, 150, 150), (cx - 60, cy - 10, 20, 50), border_radius=5)
        pygame.draw.rect(surface, (150, 150, 150), (cx + 40, cy - 10, 20, 50), border_radius=5)
        pygame.draw.polygon(surface, ORANGE if 'ORANGE' in globals() else (255, 100, 0),
                            [(cx - 55, cy + 40), (cx - 45, cy + 40), (cx - 50, cy + 70)])
        pygame.draw.polygon(surface, ORANGE if 'ORANGE' in globals() else (255, 100, 0),
                            [(cx + 45, cy + 40), (cx + 55, cy + 40), (cx + 50, cy + 70)])


# ==============================================================================
# 11. ИМПЕРИЯ И БУТИК (С ПРОКРУТКОЙ И РЕСТАРТОМ)
# ==============================================================================
class EmpireBoutiqueGame:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("Империя и Бутик")
        self.clock = pygame.time.Clock()
        self.running = True
        self.tab = "EMPIRE"
        self.scroll_offset = 0

        # Кнопки
        self.btn_back = Button(20, 20, 120, 50, "НАЗАД", GRAY, action=lambda: setattr(self, 'running', False),
                               text_color=WHITE)
        self.btn_tab1 = Button(150, 20, 200, 50, "БИЗНЕС", GOLD, action=lambda: setattr(self, 'tab', 'EMPIRE'))
        self.btn_tab2 = Button(370, 20, 200, 50, "ШМОТКИ", GOLD, action=lambda: setattr(self, 'tab', 'BOUTIQUE'))

        # Кнопка рестарта
        self.btn_reset = Button(820, 20, 160, 50, "РЕСТАРТ", RED, action=self.trigger_reset, text_color=WHITE)
        self.reset_confirm = False  # Флаг для подтверждения

        self.businesses = [
            ("Ларёк с шаурмой", 1000000, 500),
            ("Завод по печати денег", 10000000, 5000),
            ("Нефтяная вышка", 100000000, 50000),
            ("Космодром", 1000000000, 500000),
            ("Орбитальная станция", 10000000000, 5000000)
        ]

        self.items = [
            ("glasses", "Очки Мажора", 100_000),
            ("chain", "Золотая Цепь", 1_000_000),
            ("jacket", "Кожаная Куртка", 5_000_000),
            ("sneakers", "Кроссовки за 50 Лямов", 50_000_000),
            ("crown", "Корона Императора", 500_000_000),
            ("watch", "Часы Rolex", 2_000_000_000),
            ("suit", "Золотой Костюм", 10_000_000_000),
            ("wings", "Крылья Ангела", 50_000_000_000),
            ("halo", "Нимб Святого", 100_000_000_000),
            ("jetpack", "Джетпак Илона", 500_000_000_000),
        ]

        self.tick_timer = 0
        self.font_main = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 20)
        self.font_tiny = pygame.font.SysFont("Arial", 16)

    def trigger_reset(self):
        # Если нажали "РЕСТАРТ", показываем подтверждение
        self.reset_confirm = True

    def run(self):
        while self.running:
            draw_gradient_background(self.screen, (25, 20, 40), (10, 10, 15))
            mouse = get_pointer_pos()

            self.tick_timer += self.clock.get_time()
            if self.tick_timer >= 1000:
                economy.add_rubles(economy.passive_income)
                self.tick_timer = 0

            for e in get_input_events():
                if e.type == pygame.QUIT: self.running = False

                if e.type == pygame.MOUSEWHEEL:
                    if self.tab == "BOUTIQUE":
                        self.scroll_offset -= e.y * 30
                        max_scroll = max(0, len(self.items) * 70 - 500)
                        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    # Обработка подтверждения рестарта
                    if self.reset_confirm:
                        if pygame.Rect(800, 80, 180, 50).collidepoint(e.pos):
                            # ПОДТВЕРЖДЕНО! Сбрасываем
                            economy.reset_all_but_divine()
                            self.reset_confirm = False
                            print("СБРОС ВЫПОЛНЕН!")
                        else:
                            # Кликнули мимо - отменяем
                            self.reset_confirm = False
                        continue  # Пропускаем остальные клики

                    self.btn_back.check_click(e.pos)
                    self.btn_tab1.check_click(e.pos)
                    self.btn_tab2.check_click(e.pos)
                    self.btn_reset.check_click(e.pos)

                    if self.tab == "EMPIRE" and economy.business_level < len(self.businesses):
                        if pygame.Rect(350, 550, 300, 60).collidepoint(e.pos):
                            name, cost, inc = self.businesses[economy.business_level]
                            if economy.spend_rubles(cost):
                                economy.passive_income += inc
                                economy.business_level += 1
                                economy.save_game()

                    if self.tab == "BOUTIQUE":
                        for i, (iid, name, cost) in enumerate(self.items):
                            btn_rect = pygame.Rect(730, 120 + i * 70 - self.scroll_offset, 100, 40)
                            if btn_rect.collidepoint(e.pos) and iid not in economy.owned_items:
                                if economy.spend_rubles(cost):
                                    economy.owned_items.append(iid)
                                    economy.save_game()

            self.screen.blit(self.font_main.render(f"Баланс: {format_money(economy.rubles)}", True, WHITE), (20, 80))
            self.screen.blit(self.font_small.render(f"Доход: +{format_money(economy.passive_income)}/сек", True, GREEN),
                             (20, 120))

            # Отрисовка кнопок
            self.btn_back.check_hover(mouse);
            self.btn_back.draw(self.screen)
            self.btn_tab1.check_hover(mouse);
            self.btn_tab1.draw(self.screen)
            self.btn_tab2.check_hover(mouse);
            self.btn_tab2.draw(self.screen)
            self.btn_reset.check_hover(mouse);
            self.btn_reset.draw(self.screen)

            # Окно подтверждения рестарта
            if self.reset_confirm:
                pygame.draw.rect(self.screen, (60, 0, 0), (700, 80, 280, 100), border_radius=10)
                pygame.draw.rect(self.screen, RED, (700, 80, 280, 100), 2, border_radius=10)
                self.screen.blit(self.font_small.render("Сбросить ВСЁ, кроме Divine?", True, WHITE), (710, 90))

                # Кнопка ДА
                pygame.draw.rect(self.screen, GREEN, (800, 120, 160, 40), border_radius=5)
                self.screen.blit(self.font_tiny.render("ДА, НАЧАТЬ ЗАНОВО", True, BLACK),
                                 self.font_tiny.render("ДА, НАЧАТЬ ЗАНОВО", True, BLACK).get_rect(center=(880, 140)))

            if self.tab == "EMPIRE":
                if economy.business_level < len(self.businesses):
                    name, cost, inc = self.businesses[economy.business_level]
                    r = pygame.Rect(250, 350, 500, 150)
                    pygame.draw.rect(self.screen, (40, 45, 50), r, border_radius=15)
                    pygame.draw.rect(self.screen, GOLD, r, 2, border_radius=15)
                    self.screen.blit(self.font_small.render(f"Купить: {name}", True, WHITE), (270, 370))
                    self.screen.blit(
                        self.font_tiny.render(f"Цена: {format_money(cost)} | Доход: +{format_money(inc)}/сек", True,
                                              GOLD), (270, 420))

                    pygame.draw.rect(self.screen, GREEN if economy.rubles >= cost else GRAY, (350, 550, 300, 60),
                                     border_radius=15)
                    self.screen.blit(self.font_small.render("КУПИТЬ", True, BLACK),
                                     self.font_small.render("КУПИТЬ", True, BLACK).get_rect(center=(500, 580)))
                else:
                    self.screen.blit(self.font_main.render("ВЫ КУПИЛИ ВСЁ!", True, GOLD), (350, 400))
            else:
                draw_rich_guy(self.screen, 200, 350, economy.owned_items)

                for i, (iid, name, cost) in enumerate(self.items):
                    item_y = 200 + i * 70 - self.scroll_offset
                    if item_y < 150 or item_y > 650: continue

                    r = pygame.Rect(400, item_y, 450, 60)
                    owned = iid in economy.owned_items

                    pygame.draw.rect(self.screen, (40, 40, 40) if owned else (60, 60, 60), r, border_radius=10)
                    pygame.draw.rect(self.screen, GREEN if owned else GOLD, r, 2, border_radius=10)

                    self.screen.blit(self.font_small.render(name, True, WHITE), (420, item_y + 10))
                    self.screen.blit(
                        self.font_tiny.render(f"Цена: {format_money(cost)}", True, GREEN if owned else GOLD),
                        (420, item_y + 35))

                    btn_rect = pygame.Rect(730, item_y + 10, 100, 40)
                    pygame.draw.rect(self.screen, GRAY if owned or economy.rubles < cost else EMERALD, btn_rect,
                                     border_radius=5)
                    self.screen.blit(self.font_tiny.render("КУПЛЕНО" if owned else "КУПИТЬ", True, BLACK),
                                     self.font_tiny.render("КУПЛЕНО" if owned else "КУПИТЬ", True, BLACK).get_rect(
                                         center=btn_rect.center))

                # Скроллбар
                pygame.draw.rect(self.screen, (40, 40, 40), (880, 150, 10, 500), border_radius=5)
                scroll_ratio = len(self.items) * 70 / 500
                if scroll_ratio > 1:
                    bar_h = 500 / scroll_ratio
                    bar_y = 150 + (self.scroll_offset / (len(self.items) * 70 - 500)) * (500 - bar_h)
                    pygame.draw.rect(self.screen, GOLD, (880, bar_y, 10, bar_h), border_radius=5)

            pygame.display.flip()
            self.clock.tick(60)


# ==============================================================================
# 12. ПРОФИЛЬ (ПРОСМОТР ПЕРСОНАЖА)
# ==============================================================================
class ProfileScene:
    def __init__(self):
        self.width, self.height = 1000, 700
        self.screen = set_game_mode(self.width, self.height, resizable=False)
        if not IS_IOS:
            pygame.display.set_caption("Мой Профиль")
        self.clock = pygame.time.Clock()
        self.running = True
        self.btn_back = Button(20, 20, 120, 50, "НАЗАД", GRAY, action=lambda: setattr(self, 'running', False),
                               text_color=WHITE)
        self.font_main = pygame.font.SysFont("Arial", 40, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 24)

    def run(self):
        while self.running:
            draw_gradient_background(self.screen, (30, 20, 30), (10, 10, 10))
            mouse = get_pointer_pos()

            for e in get_input_events():
                if e.type == pygame.QUIT: self.running = False
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.btn_back.check_click(e.pos)

            self.screen.blit(self.font_main.render("МОЙ ПЕРСОНАЖ", True, GOLD), (350, 50))
            self.screen.blit(self.font_small.render(f"Всего куплено шмоток: {len(economy.owned_items)}", True, WHITE),
                             (380, 100))

            # Рисуем персонажа в центре
            draw_rich_guy(self.screen, 500, 400, economy.owned_items)

            self.btn_back.check_hover(mouse);
            self.btn_back.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(60)


# ==============================================================================
# 13. ГЛАВНОЕ МЕНЮ
# ==============================================================================
class MainMenu:
    def __init__(self):
        self.running = True
        self.current_scene = "MAIN_MENU"
        self.admin_mode = False
        self.keys_pressed = {"L": False, "P": False}
        self.last_income_time = pygame.time.get_ticks()
        self.particles = [Particle(random.randint(0, WIDTH), random.randint(0, HEIGHT), GOLD,
                                   (random.uniform(-0.5, 0.5), random.uniform(-1, -0.2)), 200) for _ in range(50)]
#SCALED
    def handle_click(self, pos):
        if self.admin_mode:
            if pygame.Rect(350, 200, 300, 50).collidepoint(pos):
                economy.add_rubles(100000000)
            if pygame.Rect(350, 270, 300, 50).collidepoint(pos):
                economy.update_market()
            return

        if self.current_scene == "MAIN_MENU":
            if pygame.Rect(350, 200, 300, 60).collidepoint(pos):
                self.current_scene = "DEPCHIK_MENU"
            if pygame.Rect(350, 300, 300, 60).collidepoint(pos):
                bura_game = Game()
                bura_game.run()
                # Просто возвращаем размер, без SCALED
                set_game_mode(WIDTH, HEIGHT, resizable=False)
            # НОВАЯ КНОПКА ПРОФИЛЯ
            if pygame.Rect(350, 400, 300, 60).collidepoint(pos):
                ProfileScene().run()

        elif self.current_scene == "DEPCHIK_MENU":
            if pygame.Rect(30, 30, 120, 50).collidepoint(pos):
                self.current_scene = "MAIN_MENU"
            if pygame.Rect(300, 120, 400, 60).collidepoint(pos):
                LehaGame().run()
            if pygame.Rect(300, 200, 400, 60).collidepoint(pos):
                TsarGame().run()
            if pygame.Rect(300, 280, 400, 60).collidepoint(pos):
                MarketScene().run()
            if pygame.Rect(300, 360, 400, 60).collidepoint(pos):
                SyndicateGame().run()
            if pygame.Rect(300, 440, 400, 60).collidepoint(pos):
                EmpireBoutiqueGame().run()

    def draw(self):
        draw_gradient_background(screen, (25, 30, 45), (10, 10, 15))

        for p in self.particles[:]:
            if not p.update(): self.particles.remove(p)
            p.draw(screen)
            if len(self.particles) < 50:
                self.particles.append(Particle(random.randint(0, WIDTH), HEIGHT, GOLD,
                                               (random.uniform(-0.5, 0.5), random.uniform(-1, -0.2)), 200))

        if self.current_scene == "MAIN_MENU":
            bal_text = get_font(36, True).render(
                f"Баланс: {format_money(economy.rubles)} RUB | {economy.usd:.2f} USD | {economy.eur:.2f} EUR", True,
                WHITE)
            screen.blit(bal_text, (30, 30))

            rect_dep = pygame.Rect(350, 200, 300, 60)
            pygame.draw.rect(screen, GREEN, rect_dep, border_radius=10)
            pygame.draw.rect(screen, WHITE, rect_dep, 2, border_radius=10)
            text_dep = get_font(32, True).render("Депчик", True, BLACK)
            screen.blit(text_dep, text_dep.get_rect(center=rect_dep.center))

            rect_bura = pygame.Rect(350, 300, 300, 60)
            pygame.draw.rect(screen, RED, rect_bura, border_radius=10)
            pygame.draw.rect(screen, WHITE, rect_bura, 2, border_radius=10)
            text_bura = get_font(32, True).render("Бураа", True, BLACK)
            screen.blit(text_bura, text_bura.get_rect(center=rect_bura.center))

            # Кнопка Профиля
            rect_prof = pygame.Rect(350, 400, 300, 60)
            pygame.draw.rect(screen, GOLD, rect_prof, border_radius=10)
            pygame.draw.rect(screen, WHITE, rect_prof, 2, border_radius=10)
            text_prof = get_font(32, True).render("МОЙ ПЕРСОНАЖ", True, BLACK)
            screen.blit(text_prof, text_prof.get_rect(center=rect_prof.center))

        elif self.current_scene == "DEPCHIK_MENU":
            rect_back = pygame.Rect(30, 30, 120, 50)
            pygame.draw.rect(screen, WHITE, rect_back, border_radius=10)
            text_back = get_font(24, True).render("Назад", True, BLACK)
            screen.blit(text_back, text_back.get_rect(center=rect_back.center))

            buttons = [
                ("Для Лехи", GOLD, 120),
                ("Царь-Депчик", GOLD, 200),
                ("БИРЖА", EMERALD, 280),
                ("СИНДИКАТ (1М+)", PURPLE, 360),
                ("ИМПЕРИЯ & БУТИК", (200, 50, 150), 440)
            ]
            for text, color, y in buttons:
                rect = pygame.Rect(300, y, 400, 60)
                pygame.draw.rect(screen, color, rect, border_radius=10)
                pygame.draw.rect(screen, WHITE, rect, 2, border_radius=10)
                text_color = WHITE if color == PURPLE else BLACK
                surf = get_font(28, True).render(text, True, text_color)
                screen.blit(surf, surf.get_rect(center=rect.center))

        if self.admin_mode:
            s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            s.fill((0, 0, 0, 200))
            screen.blit(s, (0, 0))

            admin_title = get_font(40, True).render("ADMIN MENU", True, RED)
            screen.blit(admin_title, admin_title.get_rect(center=(WIDTH // 2, 120)))

            rect_add = pygame.Rect(350, 200, 300, 50)
            pygame.draw.rect(screen, GREEN, rect_add, border_radius=10)
            pygame.draw.rect(screen, WHITE, rect_add, 2, border_radius=10)
            text_add = get_font(24, True).render("+ 100 000 000 RUB", True, BLACK)
            screen.blit(text_add, text_add.get_rect(center=rect_add.center))

            rect_skip = pygame.Rect(350, 270, 300, 50)
            pygame.draw.rect(screen, BLUE, rect_skip, border_radius=10)
            pygame.draw.rect(screen, WHITE, rect_skip, 2, border_radius=10)
            text_skip = get_font(24, True).render("Скипнуть 24ч", True, BLACK)
            screen.blit(text_skip, text_skip.get_rect(center=rect_skip.center))

            hint = get_font(20).render("Нажмите L+P или ESC, чтобы закрыть", True, WHITE)
            screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 360)))

    def run(self):
        while self.running:
            for event in get_input_events():
                if event.type == pygame.QUIT: self.running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_l: self.keys_pressed["L"] = True
                    if event.key == pygame.K_p: self.keys_pressed["P"] = True
                    if self.keys_pressed["L"] and self.keys_pressed["P"]:
                        self.admin_mode = not self.admin_mode
                        self.keys_pressed["L"] = False
                        self.keys_pressed["P"] = False
                    if event.key == pygame.K_ESCAPE and self.admin_mode: self.admin_mode = False
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1: self.handle_click(event.pos)

            current_time = pygame.time.get_ticks()
            if current_time - self.last_income_time >= 1000:
                if economy.passive_income > 0:
                    economy.rubles += economy.passive_income
                    if current_time % 5000 < 1000: economy.save_game()
                self.last_income_time = current_time

            self.draw()
            pygame.display.flip()
            clock.tick(60)


if __name__ == "__main__":
    menu = MainMenu()
    menu.run()
    pygame.quit()
    sys.exit()
