# main.py
# ILI9486 + XPT2046 + Accessible UI + MIC badge
# + NeoPixel breathing (GP10) synced to Grounding screen (non-blocking + HARD throttled writes)
# + School Timetable screen (data in timetable.py)
#
# Wiring:
#   NeoPixels: DIN -> GP10 (recommend 330Ω series resistor), 5V -> VBUS/5V (or external 5V), GND -> GND (shared)
#   MIC: OUT -> GP26 (ADC0), VCC -> 3V3, GND -> GND
#
# Files you need on Pico:
#   main.py
#   mic_level.py   (the robust version)
#   timetable.py   (TIMETABLE dict)
#   ili9486.py, xpt2046.py, touch_cal.py, ui.py

from machine import Pin, SPI
import time
import math
import json

from ili9486 import ILI9486
from xpt2046 import XPT2046
from touch_cal import CAL
from ui import Button, Battery

from app_config import (
    TIMETABLE,
    FAV_CARDS, CAT_NEEDS, CAT_SENSORY, CAT_RESPONSES, CAT_FEELINGS, CAT_STATUS,
    CONTACT_TEXT,
    MIC_QUIET_THRESH, MIC_HYSTERESIS, MIC_QUIET_HOLD_MS,
    NEO_QUIET_COLOR, NEO_ACTIVE_COLOR,
    BATTERY_POLL_MS,
)

# ============================================================
# Debug options
# ============================================================
DEBUG_TOUCH_DOT = False

# ============================================================
# NeoPixel Breathing (HARD throttled writes)
# ============================================================
NEOPIXELS_ENABLED = True
NEO_PIN = 10
NEO_COUNT = 10

class BreathingPixels:
    """
    Breathing cycle with HARD throttling so np.write() can't dominate the loop.
    """
    def __init__(
        self,
        pin=10,
        n=10,
        color=(0, 120, 255),
        max_brightness=0.22,
        inhale_s=4.0,
        hold_s=1.0,
        exhale_s=6.0,
        rest_s=1.0,
        rest_brightness=0.0,
        gamma=2.2,
        write_ms=60,          # max ~16fps
        min_delta=2           # only write when RGB changes enough
    ):
        import neopixel
        self.np = neopixel.NeoPixel(Pin(pin), n)
        self.n = n

        self.color = (int(color[0]), int(color[1]), int(color[2]))
        self.max_brightness = float(max_brightness)

        self.inhale_s = float(inhale_s)
        self.hold_s = float(hold_s)
        self.exhale_s = float(exhale_s)
        self.rest_s = float(rest_s)
        self.rest_brightness = float(rest_brightness)

        self.gamma = float(gamma)
        self.write_ms = int(write_ms)
        self.min_delta = int(min_delta)

        self.enabled = False
        self._t0 = time.ticks_ms()
        self._last_write = 0
        self._last_sent = (0, 0, 0)

    def set_color(self, rgb):
        self.color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))

    def set_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self._t0 = time.ticks_ms()
        if not self.enabled:
            self.off()

    def off(self):
        for i in range(self.n):
            self.np[i] = (0, 0, 0)
        self.np.write()
        self._last_sent = (0, 0, 0)
        self._last_write = time.ticks_ms()

    def _apply_gamma(self, x):
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        return x ** self.gamma

    def _maybe_write(self, rgb):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_write) < self.write_ms:
            return

        lr, lg, lb = self._last_sent
        r, g, b = rgb
        if (abs(r - lr) < self.min_delta and
            abs(g - lg) < self.min_delta and
            abs(b - lb) < self.min_delta):
            return

        for i in range(self.n):
            self.np[i] = rgb
        self.np.write()

        self._last_sent = rgb
        self._last_write = now

    def tick(self):
        if not self.enabled:
            return

        inhale_ms = int(self.inhale_s * 1000)
        hold_ms   = int(self.hold_s   * 1000)
        exhale_ms = int(self.exhale_s * 1000)
        rest_ms   = int(self.rest_s   * 1000)
        total_ms = inhale_ms + hold_ms + exhale_ms + rest_ms
        if total_ms <= 0:
            return

        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._t0) % total_ms

        if dt < inhale_ms:
            t = dt / inhale_ms if inhale_ms else 1.0
            level = 0.5 - 0.5 * math.cos(math.pi * t)  # 0->1
        elif dt < inhale_ms + hold_ms:
            level = 1.0
        elif dt < inhale_ms + hold_ms + exhale_ms:
            t = (dt - inhale_ms - hold_ms) / exhale_ms if exhale_ms else 1.0
            level = 0.5 + 0.5 * math.cos(math.pi * t)  # 1->0
        else:
            level = self.rest_brightness

        lvl = self._apply_gamma(max(0.0, min(1.0, level))) * self.max_brightness
        r, g, b = self.color
        rgb = (int(r * lvl), int(g * lvl), int(b * lvl))
        self._maybe_write(rgb)

# Create breather
breather = None
try:
    if NEOPIXELS_ENABLED:
        breather = BreathingPixels(
            pin=NEO_PIN,
            n=NEO_COUNT,
            color=(0, 120, 255),      # calm teal-blue
            max_brightness=0.22,
            inhale_s=4.0,
            hold_s=1.0,
            exhale_s=6.0,
            rest_s=1.0,
            rest_brightness=0.00,
            write_ms=60,
            min_delta=2
        )
except Exception as e:
    print("NeoPixel init failed:", e)
    breather = None

# ============================================================
# MIC (analog) quiet detector
# ============================================================
MIC_ENABLED = True
MIC_ADC_PIN = 26  # GP26 / ADC0

MIC_SAMPLE_COUNT   = 120
MIC_SAMPLE_US      = 80
MIC_EMA_ALPHA      = 0.15
# MIC_QUIET_THRESH, MIC_HYSTERESIS, MIC_QUIET_HOLD_MS loaded from app_config / config.json

MIC_POLL_MS        = 400
MIC_DRAW_THROTTLE  = 250

try:
    if MIC_ENABLED:
        from mic_level import MicLevel
        mic = MicLevel(
            adc_pin=MIC_ADC_PIN,
            sample_count=MIC_SAMPLE_COUNT,
            sample_us=MIC_SAMPLE_US,
            ema_alpha=MIC_EMA_ALPHA,
            quiet_threshold=MIC_QUIET_THRESH,
            hysteresis=MIC_HYSTERESIS,
            quiet_hold_ms=MIC_QUIET_HOLD_MS,
            max_read_ms=12,
            yield_every=25
        )
        print("Mic initialized with threshold:", MIC_QUIET_THRESH)
    else:
        mic = None
        print("Mic disabled")
except Exception as e:
    print("Mic init failed:", e)
    mic = None

mic_quiet = False
mic_rms = 0.0
_last_mic_poll = 0
_last_badge_draw = 0
_last_badge_state = None

# ============================================================
# Battery (Pimoroni Pico LiPo)
# ============================================================
BATTERY_ENABLED = True

try:
    if BATTERY_ENABLED:
        battery = Battery()
    else:
        battery = None
except Exception as e:
    print("Battery init failed:", e)
    battery = None

battery_percentage = 0
battery_is_charging = False
_last_battery_poll = 0
_last_battery_draw = 0

# ============================================================
# Hardware + display config
# ============================================================
SPI_ID = 0
SCK, MOSI, MISO = 18, 19, 16
LCD_CS, LCD_DC, LCD_RST, LCD_BL = 17, 20, 21, 22
TP_CS, TP_IRQ = 15, 14

MADCTL = 0x48
BGR = True
X_OFFSET = 0
Y_OFFSET = 0

# --- colours (RGB565) ---
BLACK = 0x0000
WHITE = 0xFFFF
GREY  = 0x7BEF
DARK  = 0x39E7
YELL  = 0xFFE0
RED   = 0xF800
GREEN = 0x07E0
BLUE  = 0x001F
CYAN  = 0x07FF
MAG   = 0xF81F
ORNG  = 0xFD20

W = CAL.get("W", 480)
H = CAL.get("H", 320)

Pin(LCD_BL, Pin.OUT).value(1)

spi = SPI(SPI_ID, baudrate=2_000_000, polarity=0, phase=0,
          sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))

lcd = ILI9486(
    spi,
    cs=LCD_CS,
    dc=LCD_DC,
    rst=LCD_RST,
    width=W,
    height=H,
    madctl=MADCTL,
    bgr=BGR,
    x_offset=X_OFFSET,
    y_offset=Y_OFFSET
)

tp = XPT2046(spi, cs_pin=TP_CS, irq_pin=TP_IRQ)

# ============================================================
# Touch mapping (manual)
# ============================================================
def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def map_linear(raw, raw_min, raw_max, out_min, out_max):
    if raw_max == raw_min:
        return out_min
    v = (raw - raw_min) * (out_max - out_min) // (raw_max - raw_min) + out_min
    return clamp(v, min(out_min, out_max), max(out_min, out_max))

def raw_to_screen(rx, ry):
    c = CAL
    if c.get("SWAP_XY", False):
        rx, ry = ry, rx
    if c.get("FLIP_X", False):
        rx = 3800 - rx
    if c.get("FLIP_Y", False):
        ry = 3800 - ry

    x = map_linear(rx, c["RAW_X_LEFT"], c["RAW_X_RIGHT"], 0, W - 1)
    y = map_linear(ry, c["RAW_Y_TOP"],  c["RAW_Y_BOT"],   0, H - 1)
    return x, y

def debug_dot(x, y):
    lcd.fill_rect(x - 2, y - 2, 5, 5, RED)

# ============================================================
# Accessible Theme system (Settings)
# ============================================================
THEMES = [
    # name         title_bg  title_fg  screen_bg box_bg   box_bdr  btn_bg   btn_fg   accent

    # High‑contrast modern dark
    ("NEON_DARK",   0x0000,   0x07FF,   0x0000,   0x0000,  0x07FF,  0x07E0,  0x0000,  0xF81F),

    # Soft, warm, paper‑like light mode
    ("CREAM",       0xF79E,   0x0000,   0xFFFF,   0xFFFF,  0x0000,  0xF79E,  0x0000,  0x07E0),

    # Cool, icy blue UI
    ("GLACIER",     0x07FF,   0x0000,   0xCFFF,   0xCFFF,  0x001F,  0x07FF,  0x0000,  0x001F),

    # Retro terminal green
    ("TERMINAL",    0x0000,   0x07E0,   0x0000,   0x0000,  0x07E0,  0x0320,  0x07E0,  0x07E0),

    # Sunset orange theme
    ("SUNSET",      0xFC00,   0xFFFF,   0xFD20,   0xFD20,  0xF800,  0xFC00,  0xFFFF,  0xF81F),

    # Steel grey industrial UI
    ("STEEL",       0x4208,   0xFFFF,   0x8410,   0x8410,  0xFFFF,  0x4208,  0xFFFF,  0x07FF),

    # Pastel lavender aesthetic
    ("LAVENDER",    0xB81F,   0xFFFF,   0xE81F,   0xE81F,  0x780F,  0xB81F,  0xFFFF,  0x07FF),

    # High‑contrast monochrome
    ("MONO",        0xFFFF,   0x0000,   0x8410,   0x8410,  0xFFFF,  0x0000,  0xFFFF,  0xFFFF),
]

theme_index = 0

def th():
    (name,
     title_bg, title_fg,
     screen_bg,
     box_bg, box_border,
     btn_bg, btn_fg,
     accent) = THEMES[theme_index]
    return {
        "name": name,
        "title_bg": title_bg,
        "title_fg": title_fg,
        "screen_bg": screen_bg,
        "box_bg": box_bg,
        "box_border": box_border,
        "btn_bg": btn_bg,
        "btn_fg": btn_fg,
        "accent": accent,
    }

# ============================================================
# Drawing helpers
# ============================================================
def draw_border(x, y, w, h, c):
    lcd.fill_rect(x, y, w, 1, c)
    lcd.fill_rect(x, y+h-1, w, 1, c)
    lcd.fill_rect(x, y, 1, h, c)
    lcd.fill_rect(x+w-1, y, 1, h, c)

def draw_mic_badge(force=False):
    global _last_badge_draw, _last_badge_state
    if mic is None:
        return

    now = time.ticks_ms()
    if (not force) and time.ticks_diff(now, _last_badge_draw) < MIC_DRAW_THROTTLE:
        return

    state = mic_quiet
    if (not force) and state == _last_badge_state:
        _last_badge_draw = now
        return

    t = th()
    # Position on left side of title bar, after title text
    bx = 160
    by = 10
    bw = 90
    bh = 28

    if state:
        bg = GREEN
        fg = BLACK
        label = "QUIET OK"
    else:
        bg = MAG
        fg = WHITE
        label = "LOUD"

    lcd.fill_rect(bx, by, bw, bh, bg)
    draw_border(bx, by, bw, bh, t["box_border"])

    scale = 1
    tw = len(label) * 8 * scale
    tx = bx + (bw - tw) // 2
    ty = by + (bh - 8) // 2
    lcd.text(label, tx, ty, fg, bg, scale=scale)

    _last_badge_state = state
    _last_badge_draw = now

def draw_battery_icon(x, y, size, percentage, color):
    """Draw a simple 5-segment battery icon."""
    segment_h = size // 5
    segment_w = size // 3
    filled = (percentage // 20)  # 0-5 segments
    
    for i in range(5):
        seg_y = y + i * segment_h
        if i < filled:
            lcd.fill_rect(x, seg_y, segment_w, segment_h - 1, color)
        else:
            draw_border(x, seg_y, segment_w, segment_h - 1, color)

def draw_battery_display(force=False):
    """Draw battery percentage in top-right corner - simple, clean."""
    global _last_battery_draw, battery_percentage, battery_is_charging
    if battery is None:
        return
    
    now = time.ticks_ms()
    if (not force) and time.ticks_diff(now, _last_battery_draw) < 500:
        return
    _last_battery_draw = now
    
    t = th()
    color = battery.get_battery_color()
    percent_text = "{}%".format(battery_percentage)
    
    # Draw at top-right, padded from edge
    scale = 1
    tw = len(percent_text) * 8 * scale
    tx = W - tw - 12
    ty = 14
    
    lcd.text(percent_text, tx, ty, color, t["title_bg"], scale=scale)

def draw_title_bar(title):
    global _last_badge_state
    _last_badge_state = None  # force fresh badge draw on every screen transition
    t = th()
    lcd.fill_rect(0, 0, W, 48, t["title_bg"])
    lcd.text(title, 12, 14, t["title_fg"], t["title_bg"], scale=2)
    
    # Draw mic badge on left side (after title)
    draw_mic_badge(force=True)
    
    # Draw battery on right side
    draw_battery_display(force=True)

def wrap_text(s, max_chars):
    words = s.split(" ")
    lines = []
    cur = ""
    for w_ in words:
        if "\n" in w_:
            parts = w_.split("\n")
            for i, p in enumerate(parts):
                if p:
                    if len(cur) + (1 if cur else 0) + len(p) <= max_chars:
                        cur = (cur + " " + p).strip()
                    else:
                        if cur: lines.append(cur)
                        cur = p
                if i != len(parts)-1:
                    if cur: lines.append(cur)
                    cur = ""
            continue

        if len(cur) + (1 if cur else 0) + len(w_) <= max_chars:
            cur = (cur + " " + w_).strip()
        else:
            if cur: lines.append(cur)
            cur = w_
    if cur: lines.append(cur)
    return lines

def draw_button(btn: Button, pressed=False):
    t = th()
    bg_default = t["btn_bg"]
    fg_default = t["btn_fg"]
    border = t["box_border"]

    bg = getattr(btn, "bg", bg_default)
    fg = getattr(btn, "fg", fg_default)

    if pressed:
        bg, fg = fg, bg

    lcd.fill_rect(btn.x, btn.y, btn.w, btn.h, bg)
    draw_border(btn.x, btn.y, btn.w, btn.h, border)

    scale = 2
    text_w = len(btn.label) * 8 * scale
    tx = btn.x + (btn.w - text_w) // 2
    ty = btn.y + (btn.h - 16) // 2
    lcd.text(btn.label, tx, ty, fg, bg, scale=scale)

def make_btn(x, y, w, h, label, on_press, bg=None, fg=None):
    b = Button(x, y, w, h, label, on_press)
    if bg is not None: b.bg = bg
    if fg is not None: b.fg = fg
    return b

def draw_text_box(text, x, y, w, h, prefer_scale=2):
    t = th()
    lcd.fill_rect(x, y, w, h, t["box_bg"])
    draw_border(x, y, w, h, t["box_border"])

    for scale in (prefer_scale, 1):
        max_chars = (w - 16) // (8 * scale)
        lines = wrap_text(text, max_chars)
        line_h = 8 * scale + 2
        max_lines = (h - 16) // line_h

        if len(lines) <= max_lines or scale == 1:
            tx = x + 8
            ty = y + 8
            shown = 0
            for line in lines:
                if shown >= max_lines:
                    break
                fg = WHITE if t["box_bg"] == BLACK else BLACK
                lcd.text(line, tx, ty, fg, t["box_bg"], scale=scale)
                ty += line_h
                shown += 1
            return

# ============================================================
# Screens
# ============================================================
SCREEN_DASHBOARD = "dashboard"
SCREEN_GROUND    = "grounding"
SCREEN_TIMETABLE = "timetable"
SCREEN_CONTACTS  = "contacts"
SCREEN_SETTINGS  = "settings"
SCREEN_COMM_MENU = "comm_menu"
SCREEN_COMM_CARD = "comm_card"
current_screen = SCREEN_DASHBOARD

def set_breathing_active(active: bool):
    if breather is None:
        return
    breather.set_enabled(bool(active))
    if not active:
        try:
            breather.off()
        except Exception:
            pass

# ============================================================
# Shared bottom nav layout
# ============================================================
NAV_H = 80
NAV_Y = H - (NAV_H + 20)
NAV_X0 = 20
NAV_GAP = 12
NAV_W = (W - 40 - 2*NAV_GAP) // 3

def draw_indicator(text):
    t = th()
    scale = 2
    tw = len(text) * 8 * scale
    reserve = 140 if mic is not None else 0
    x = W - reserve - tw - 12
    lcd.text(text, x, 14, t["title_fg"], t["title_bg"], scale=scale)

# ============================================================
# Grounding
# ============================================================
GROUNDING_PAGES = [
    "5-4-3-2-1 Senses\n\n"
    "Name:\n"
    "5 things you can SEE\n"
    "4 things you can FEEL\n"
    "3 things you can HEAR\n"
    "2 things you can SMELL\n"
    "1 thing you can TASTE",

    "Box Breathing (4-4-4-4)\n\n"
    "Inhale 4\n"
    "Hold   4\n"
    "Exhale 4\n"
    "Hold   4\n\n"
    "Repeat 4 times.",

    "Feet + Body Scan\n\n"
    "Press feet into floor.\n"
    "Notice pressure + texture.\n"
    "Relax jaw, drop shoulders.\n"
    "Unclench hands.\n"
    "Slow exhale.",

    "Progressive Muscle Relax\n\n"
    "Tense each group 5 sec,\n"
    "then fully release.\n"
    "Work up: feet, calves,\n"
    "thighs, stomach, arms,\n"
    "shoulders, face.",

    "Safe Place\n\n"
    "Close your eyes.\n"
    "Picture somewhere safe\n"
    "and calm. Notice the\n"
    "colours, sounds, smells,\n"
    "textures. Stay 1 minute."
]
page_index = 0

btn_ground_prev = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_ground_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)
btn_ground_next = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)

def draw_grounding():
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("GROUNDING")

    box_x = 16
    box_y = 60
    box_w = W - 32
    box_h = H - 60 - (NAV_H + 30)

    indicator = f"{page_index+1}/{len(GROUNDING_PAGES)}"
    draw_indicator(indicator)

    draw_text_box(GROUNDING_PAGES[page_index], box_x, box_y, box_w, box_h, prefer_scale=2)

    draw_button(btn_ground_prev)
    draw_button(btn_ground_menu)
    draw_button(btn_ground_next)

def show_grounding():
    global current_screen
    current_screen = SCREEN_GROUND
    set_breathing_active(True)
    draw_grounding()

def grounding_prev():
    global page_index
    if page_index > 0:
        page_index -= 1
        draw_grounding()

def grounding_next():
    global page_index
    if page_index < len(GROUNDING_PAGES) - 1:
        page_index += 1
        draw_grounding()

btn_ground_prev.on_press = grounding_prev
btn_ground_next.on_press = grounding_next

# ============================================================
# Timetable (data in timetable.py)
# ============================================================
TT_DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
tt_day_index = 0
tt_page = 0
TT_ITEMS_PER_PAGE = 3

btn_tt_prev = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_tt_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)
btn_tt_next = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)

# placeholders so screen_buttons() never hits None
btn_tt_mon = Button(0, 0, 1, 1, "M", lambda: None)
btn_tt_tue = Button(0, 0, 1, 1, "T", lambda: None)
btn_tt_wed = Button(0, 0, 1, 1, "W", lambda: None)
btn_tt_thu = Button(0, 0, 1, 1, "T", lambda: None)
btn_tt_fri = Button(0, 0, 1, 1, "F", lambda: None)

def tt_current_day():
    return TT_DAYS[tt_day_index]

def tt_day_items(day):
    return TIMETABLE.get(day, [])

def tt_total_pages(day):
    items = tt_day_items(day)
    if not items:
        return 1
    return (len(items) + TT_ITEMS_PER_PAGE - 1) // TT_ITEMS_PER_PAGE

def tt_set_day(idx):
    global tt_day_index, tt_page
    tt_day_index = idx
    tt_page = 0
    draw_timetable()

def tt_prev():
    global tt_page
    if tt_page > 0:
        tt_page -= 1
        draw_timetable()

def tt_next():
    global tt_page
    day = tt_current_day()
    if tt_page < tt_total_pages(day) - 1:
        tt_page += 1
        draw_timetable()

btn_tt_prev.on_press = tt_prev
btn_tt_next.on_press = tt_next

def draw_timetable():
    global btn_tt_mon, btn_tt_tue, btn_tt_wed, btn_tt_thu, btn_tt_fri

    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("TIMETABLE")
    set_breathing_active(False)

    # Day row buttons
    days_y = 56
    days_h = 44
    x0 = 16
    gap = 8
    bw = (W - 2*x0 - 4*gap) // 5

    def mk_day_btn(label, idx, x):
        if idx == tt_day_index:
            bg = th()["accent"]
            fg = BLACK if bg != BLACK else WHITE
        else:
            bg = th()["btn_bg"]
            fg = th()["btn_fg"]
        return make_btn(x, days_y, bw, days_h, label, lambda: tt_set_day(idx), bg=bg, fg=fg)

    btn_tt_mon = mk_day_btn("MON", 0, x0 + 0*(bw+gap))
    btn_tt_tue = mk_day_btn("TUE", 1, x0 + 1*(bw+gap))
    btn_tt_wed = mk_day_btn("WED", 2, x0 + 2*(bw+gap))
    btn_tt_thu = mk_day_btn("THU", 3, x0 + 3*(bw+gap))
    btn_tt_fri = mk_day_btn("FRI", 4, x0 + 4*(bw+gap))

    for b in [btn_tt_mon, btn_tt_tue, btn_tt_wed, btn_tt_thu, btn_tt_fri]:
        draw_button(b)

    day = tt_current_day()
    items = tt_day_items(day)

    box_x = 16
    box_y = days_y + days_h + 10
    box_w = W - 32
    box_h = H - box_y - (NAV_H + 30)

    pages = tt_total_pages(day)
    indicator = f"{day}  {tt_page+1}/{pages}"
    draw_indicator(indicator)

    if not items:
        draw_text_box("No lessons saved for this day yet.", box_x, box_y, box_w, box_h, prefer_scale=2)
    else:
        start = tt_page * TT_ITEMS_PER_PAGE
        end = min(start + TT_ITEMS_PER_PAGE, len(items))
        chunk = items[start:end]

        lines = []
        for p in chunk:
            time_str = (p.get("time", "") or "").strip()
            title = (p.get("title", "") or "").strip()
            room = (p.get("room", "") or "").strip()
            note = (p.get("note", "") or "").strip()

            header = f"{time_str}  {title}".strip()
            if room:
                header += f"  ({room})"
            lines.append(header)
            if note:
                lines.append(f"- {note}")
            lines.append("")

        text = "\n".join(lines).strip()
        draw_text_box(text, box_x, box_y, box_w, box_h, prefer_scale=2)

    draw_button(btn_tt_prev)
    draw_button(btn_tt_menu)
    draw_button(btn_tt_next)

def show_timetable():
    global current_screen
    current_screen = SCREEN_TIMETABLE
    set_breathing_active(False)
    draw_timetable()

# ============================================================
# Contacts
# ============================================================
# CONTACT_TEXT loaded from app_config / config.json

btn_contacts_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)

def show_contacts():
    global current_screen
    t = th()
    current_screen = SCREEN_CONTACTS
    set_breathing_active(False)
    lcd.fill(t["screen_bg"])
    draw_title_bar("CONTACTS")

    box_x = 16
    box_y = 60
    box_w = W - 32
    box_h = H - 60 - (NAV_H + 30)

    draw_text_box(CONTACT_TEXT, box_x, box_y, box_w, box_h, prefer_scale=2)
    draw_button(btn_contacts_menu)

# ============================================================
# Settings (themes + sensor & neo tabs)
# ============================================================
settings_buttons  = []
settings_page     = 0        # 0 = THEMES  1 = SENSOR & NEO
mic_thresh_live   = MIC_QUIET_THRESH
neo_quiet_color   = NEO_QUIET_COLOR
neo_active_color  = NEO_ACTIVE_COLOR
neo_preset_index  = -1       # -1 = custom

# NeoPixel presets: (label, RGB565-swatch, quiet-RGB, active-RGB)
NEO_PRESETS = [
    ("OCEAN",  0x041F, (  0, 100, 255), (100,   0, 255)),
    ("FOREST", 0x07C0, (  0, 200,  60), (200, 100,   0)),
    ("SUNSET", 0xFD20, (255, 100,   0), (255,   0,  80)),
    ("GALAXY", 0x780F, (100,   0, 200), (  0, 200, 200)),
    ("ROSE",   0xF813, (255,   0, 120), (100,   0, 200)),
    ("ARCTIC", 0x07FF, (  0, 220, 200), (  0, 100, 255)),
    ("FIRE",   0xF800, (255,  30,   0), (255, 180,   0)),
    ("CALM",   0xC618, (160, 160, 160), (  0, 100, 255)),
]

btn_settings_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)
btn_settings_tab0 = Button(20,  60, 210, 30, "THEMES",       lambda: None)
btn_settings_tab1 = Button(250, 60, 210, 30, "SENSOR & NEO", lambda: None)

def save_config_partial(**kwargs):
    try:
        with open("config.json") as f:
            cfg = json.load(f)
        for k, v in kwargs.items():
            cfg[k] = v
        with open("config.json", "w") as f:
            json.dump(cfg, f)
    except Exception as e:
        print("config save:", e)

def apply_theme(idx):
    global theme_index
    theme_index = idx
    show_settings()

def set_settings_page(page):
    global settings_page
    settings_page = page
    show_settings()

def apply_neo_preset(idx):
    global neo_quiet_color, neo_active_color, neo_preset_index, _last_quiet_for_color
    neo_preset_index = idx
    _, _, qc, ac = NEO_PRESETS[idx]
    neo_quiet_color  = qc
    neo_active_color = ac
    _last_quiet_for_color = None   # force sync_breather to update colour immediately
    save_config_partial(neo_quiet_color=list(qc), neo_active_color=list(ac))
    show_settings()

def adjust_mic_thresh(delta):
    global mic_thresh_live
    # Useful RMS range on Pico ADC mic: ~0.002 – 0.08
    mic_thresh_live = round(max(0.002, min(0.08, mic_thresh_live + delta)), 3)
    if mic is not None:
        mic.quiet_threshold = mic_thresh_live
    save_config_partial(mic_quiet_thresh=mic_thresh_live)
    _redraw_sensor_content()

def _redraw_sensor_content():
    global settings_buttons
    t = th()
    lcd.fill_rect(0, 96, W, H - 96 - (NAV_H + 22), t["screen_bg"])
    settings_buttons = [btn_settings_tab0, btn_settings_tab1]

    # NeoPixel colour row
    lcd.text("NEOPIXEL COLOUR", 22, 98, t["box_border"], t["screen_bg"], scale=2)
    nb_y, nb_h, nb_gap = 120, 34, 4
    nb_w = (W - 44 - (len(NEO_PRESETS) - 1) * nb_gap) // len(NEO_PRESETS)
    for i, (_, col565, qc, ac) in enumerate(NEO_PRESETS):
        bx = 22 + i * (nb_w + nb_gap)
        lcd.fill_rect(bx, nb_y, nb_w, nb_h, col565)
        if i == neo_preset_index:
            draw_border(bx,   nb_y,   nb_w,   nb_h,   WHITE)
            draw_border(bx+1, nb_y+1, nb_w-2, nb_h-2, WHITE)
        else:
            draw_border(bx, nb_y, nb_w, nb_h, t["box_border"])
        def _neo_fn(idx=i):
            return lambda: apply_neo_preset(idx)
        settings_buttons.append(Button(bx, nb_y, nb_w, nb_h, "", _neo_fn()))

    # Mic sensitivity row
    lcd.text("MIC SENSITIVITY", 22, 163, t["box_border"], t["screen_bg"], scale=2)
    mt_y, mt_h = 183, 32
    btn_m = make_btn(22,  mt_y, 58, mt_h, "-", lambda: adjust_mic_thresh(-0.002))
    btn_p = make_btn(400, mt_y, 58, mt_h, "+", lambda: adjust_mic_thresh(+0.002))
    settings_buttons += [btn_m, btn_p]
    draw_button(btn_m)
    draw_button(btn_p)
    
    # Show current threshold
    thresh_text = "Threshold: {:.3f}".format(mic_thresh_live)
    lcd.text(thresh_text, 88, 170, t["box_border"], t["screen_bg"], scale=1)
    
    # Show current RMS reading
    rms_text = "Current RMS: {:.3f}".format(mic_rms)
    lcd.text(rms_text, 88, 185, GREEN if mic_quiet else RED, t["screen_bg"], scale=1)
    
    # Status indicator
    status_text = "QUIET" if mic_quiet else "LOUD"
    status_color = GREEN if mic_quiet else RED
    lcd.text(status_text, 88, 200, status_color, t["screen_bg"], scale=1)

def show_settings():
    global current_screen, settings_buttons, btn_settings_tab0, btn_settings_tab1
    t = th()
    current_screen = SCREEN_SETTINGS
    set_breathing_active(False)
    lcd.fill(t["screen_bg"])
    draw_title_bar("SETTINGS")

    t0_bg = t["accent"] if settings_page == 0 else t["btn_bg"]
    t0_fg = BLACK       if settings_page == 0 else t["btn_fg"]
    t1_bg = t["accent"] if settings_page == 1 else t["btn_bg"]
    t1_fg = BLACK       if settings_page == 1 else t["btn_fg"]
    btn_settings_tab0 = make_btn(20,  60, 210, 30, "THEMES",       lambda: set_settings_page(0), bg=t0_bg, fg=t0_fg)
    btn_settings_tab1 = make_btn(250, 60, 210, 30, "SENSOR & NEO", lambda: set_settings_page(1), bg=t1_bg, fg=t1_fg)
    draw_button(btn_settings_tab0)
    draw_button(btn_settings_tab1)
    settings_buttons = [btn_settings_tab0, btn_settings_tab1]

    if settings_page == 0:
        # 3-column theme grid
        gx, gy = 20, 98
        gw, gh = W - 40, H - 98 - (NAV_H + 30)
        cols = 3
        rows = (len(THEMES) + cols - 1) // cols
        gapx, gapy = 8, 8
        bw = (gw - (cols - 1) * gapx) // cols
        bh = (gh - (rows - 1) * gapy) // rows
        for i, theme_row in enumerate(THEMES):
            tbg, tfg = theme_row[1], theme_row[2]
            c, r = i % cols, i // cols
            x = gx + c * (bw + gapx)
            y = gy + r * (bh + gapy)
            def _theme_fn(idx=i):
                return lambda: apply_theme(idx)
            b = make_btn(x, y, bw, bh, theme_row[0], _theme_fn(), bg=tbg, fg=tfg)
            draw_button(b)
            if i == theme_index:
                draw_border(x,   y,   bw,   bh,   t["accent"])
                draw_border(x+1, y+1, bw-2, bh-2, t["accent"])
            settings_buttons.append(b)
    else:
        _redraw_sensor_content()

    draw_button(btn_settings_menu)

# ============================================================
# Communication Cards
# ============================================================
def speak(text):
    print("SPEAK:", text)

# FAV_CARDS, CAT_NEEDS, CAT_SENSORY, CAT_RESPONSES, CAT_FEELINGS, CAT_STATUS
# all loaded from app_config / config.json

COMM_CATEGORIES = [
    ("FAVOURITES", FAV_CARDS,    YELL,  BLACK),
    ("NEEDS",      CAT_NEEDS,    GREEN, BLACK),
    ("SENSORY",    CAT_SENSORY,  MAG,   WHITE),
    ("RESPONSES",  CAT_RESPONSES, CYAN, BLACK),
    ("FEELINGS",   CAT_FEELINGS, ORNG,  BLACK),
    ("STATUS",     CAT_STATUS,   GREY,  WHITE),
]

comm_menu_buttons = []
comm_cards = FAV_CARDS
comm_cat_name = "FAVOURITES"
comm_card_index = 0

btn_commmenu_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)

def open_category(idx):
    global comm_cards, comm_cat_name, comm_card_index
    comm_cat_name, comm_cards, _, _ = COMM_CATEGORIES[idx]
    comm_card_index = 0
    show_comm_card()

def build_comm_menu_buttons():
    global comm_menu_buttons
    comm_menu_buttons = []

    cols = 2
    rows = (len(COMM_CATEGORIES) + 1) // 2

    grid_x = 20
    grid_y = 70
    grid_w = W - 40
    grid_h = H - 70 - (NAV_H + 30)

    gapx = 12
    gapy = 12
    bw = (grid_w - gapx) // 2
    bh = (grid_h - (rows-1)*gapy) // rows

    for i, (name, cards, bg, fg) in enumerate(COMM_CATEGORIES):
        c = i % cols
        r = i // cols
        x = grid_x + c * (bw + gapx)
        y = grid_y + r * (bh + gapy)

        def make_open(idx=i):
            def _open():
                open_category(idx)
            return _open

        b = make_btn(x, y, bw, bh, name, make_open(), bg=bg, fg=fg)
        comm_menu_buttons.append(b)

def show_comm_menu():
    global current_screen
    t = th()
    current_screen = SCREEN_COMM_MENU
    set_breathing_active(False)
    lcd.fill(t["screen_bg"])
    draw_title_bar("COMM CARDS")
    build_comm_menu_buttons()
    for b in comm_menu_buttons:
        draw_button(b)
    draw_button(btn_commmenu_menu)

btn_comm_prev = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_comm_cats = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "CATS", lambda: None)
btn_comm_next = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)

ACT_H = 44
ACT_Y = 48 + 8
ACT_X0 = 20
ACT_GAP = 12
ACT_W = (W - 40 - ACT_GAP) // 2

btn_comm_speak = make_btn(ACT_X0, ACT_Y, ACT_W, ACT_H, "SPEAK", lambda: None, bg=BLUE, fg=WHITE)
btn_comm_menu  = make_btn(ACT_X0 + ACT_W + ACT_GAP, ACT_Y, ACT_W, ACT_H, "MENU", lambda: None)

def draw_comm_card():
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar(comm_cat_name)

    draw_button(btn_comm_speak)
    draw_button(btn_comm_menu)

    card_x = 16
    card_y = ACT_Y + ACT_H + 10
    card_w = W - 32
    card_h = H - card_y - (NAV_H + 30)

    icon, phrase, bg, fg = comm_cards[comm_card_index]

    lcd.fill_rect(card_x, card_y, card_w, card_h, bg)
    draw_border(card_x, card_y, card_w, card_h, t["box_border"])

    indicator = f"{comm_card_index+1}/{len(comm_cards)}"
    draw_indicator(indicator)

    icon_scale = 4
    icon_w = len(icon) * 8 * icon_scale
    ix = card_x + (card_w - icon_w) // 2
    iy = card_y + 18
    lcd.text(icon, ix, iy, fg, bg, scale=icon_scale)

    scale = 3
    max_chars = (card_w - 20) // (8 * scale)
    if max_chars < 6:
        scale = 2
        max_chars = (card_w - 20) // (8 * scale)
    if max_chars < 6:
        scale = 1
        max_chars = (card_w - 20) // (8 * scale)

    lines = wrap_text(phrase, max_chars)
    line_h = 8 * scale + 6
    total_h = len(lines) * line_h

    start_y = iy + 8*icon_scale + 18
    rem_h = (card_y + card_h) - start_y - 12
    y = start_y + (rem_h - total_h) // 2

    for line in lines:
        text_w = len(line) * 8 * scale
        x = card_x + (card_w - text_w) // 2
        lcd.text(line, x, y, fg, bg, scale=scale)
        y += line_h

    draw_button(btn_comm_prev)
    draw_button(btn_comm_cats)
    draw_button(btn_comm_next)

def show_comm_card():
    global current_screen
    current_screen = SCREEN_COMM_CARD
    set_breathing_active(False)
    draw_comm_card()

def comm_prev():
    global comm_card_index
    if comm_card_index > 0:
        comm_card_index -= 1
        draw_comm_card()

def comm_next():
    global comm_card_index
    if comm_card_index < len(comm_cards) - 1:
        comm_card_index += 1
        draw_comm_card()

btn_comm_prev.on_press = comm_prev
btn_comm_next.on_press = comm_next
btn_comm_cats.on_press = show_comm_menu
btn_comm_speak.on_press = lambda: speak(comm_cards[comm_card_index][1])

# ============================================================
# SOS shortcut
# ============================================================
def do_sos():
    global comm_cards, comm_cat_name, comm_card_index
    comm_cat_name = "NEEDS"
    comm_cards = CAT_NEEDS
    comm_card_index = 0
    show_comm_card()

# ============================================================
# Menu icons — drawn inside the left square of each button
# Each function receives (bx, by, bh, fg, bg)
# ============================================================
def _icon_sos(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    lcd.fill_rect(cx-4, by+4,     8, bh-18, fg)  # bar
    lcd.fill_rect(cx-4, by+bh-10, 8, 7,     fg)  # dot

def _icon_ground(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    for i in range(6):                            # leaf top half (widens)
        w = 2 + i * 2
        lcd.fill_rect(cx - w//2, by+4+i*2, w, 2, fg)
    for i in range(5, -1, -1):                    # leaf bottom half (narrows)
        w = 2 + i * 2
        lcd.fill_rect(cx - w//2, by+16+(5-i)*2, w, 2, fg)
    lcd.fill_rect(cx-2, by+27, 4, bh-31, fg)      # stem

def _icon_time(bx, by, bh, fg, bg):
    x0, y0, sz = bx+4, by+4, bh-8
    draw_border(x0, y0, sz, sz, fg)
    lcd.fill_rect(x0+1, y0+sz//3,     sz-2, 1, fg)  # row dividers
    lcd.fill_rect(x0+1, y0+2*sz//3,   sz-2, 1, fg)
    lcd.fill_rect(x0+sz//2, y0+1, 1, sz-2, fg)       # column divider

def _icon_comm(bx, by, bh, fg, bg):
    x0, y0, w, h = bx+3, by+3, bh-6, bh-13
    lcd.fill_rect(x0, y0, w, h, fg)               # bubble fill
    lcd.fill_rect(x0+2, y0+2, w-4, h-4, bg)       # hollow centre
    lcd.fill_rect(x0+5, y0+h, 8, 5, fg)            # tail

def _icon_contact(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    lcd.fill_rect(cx-5, by+3, 10, 10, fg)          # head
    lcd.fill_rect(cx-8, by+15, 16, bh-19, fg)      # body

def _icon_settings(bx, by, bh, fg, bg):
    cx, cy, r = bx+bh//2, by+bh//2, 5
    lcd.fill_rect(cx-r, cy-r, r*2, r*2, fg)        # centre
    lcd.fill_rect(cx-3, cy-r-4, 6, 4, fg)           # top tooth
    lcd.fill_rect(cx-3, cy+r,   6, 4, fg)            # bottom tooth
    lcd.fill_rect(cx-r-4, cy-3, 4, 6, fg)            # left tooth
    lcd.fill_rect(cx+r,   cy-3, 4, 6, fg)             # right tooth

# ============================================================
# Dashboard (2x3 Grid) - replaces old MENU
# ============================================================
# Dashboard items: (label, fn, bg, fg, icon_fn)
DASHBOARD_ITEMS = [
    ("GROUNDING",    show_grounding, None, None,  _icon_ground),
    ("TIMETABLE",    show_timetable, None, None,  _icon_time),
    ("COMM CARDS",   show_comm_menu, None, None,  _icon_comm),
    ("CONTACTS",     show_contacts,  None, None,  _icon_contact),
    ("SETTINGS",     show_settings,  None, None,  _icon_settings),
    ("ABOUT",        lambda: show_about(), None, None,  _icon_sos),
]

dashboard_buttons = []

def show_about():
    """Show about screen with device info."""
    global current_screen
    t = th()
    current_screen = SCREEN_CONTACTS  # Reuse contacts layout temporarily
    set_breathing_active(False)
    lcd.fill(t["screen_bg"])
    draw_title_bar("ABOUT")
    
    about_text = (
        "Accessible Device v1.0\n\n"
        "ILI9486 Display\n"
        "XPT2046 Touchscreen\n"
        "Pimoroni Pico LiPo\n\n"
        "Battery: {}%\n"
        "Charging: {}".format(
            battery_percentage,
            "Yes" if battery_is_charging else "No"
        )
    )
    
    box_x = 16
    box_y = 60
    box_w = W - 32
    box_h = H - 60 - (NAV_H + 30)
    
    draw_text_box(about_text, box_x, box_y, box_w, box_h, prefer_scale=2)
    
    btn_about_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "HOME", show_dashboard)
    draw_button(btn_about_menu)

def draw_dashboard():
    """Draw 2x3 grid dashboard - text-only buttons, clean layout."""
    t = th()
    lcd.fill(t["screen_bg"])
    
    # Title + battery at top
    lcd.fill_rect(0, 0, W, 48, t["title_bg"])
    lcd.text("DASHBOARD", 12, 14, t["title_fg"], t["title_bg"], scale=2)
    draw_battery_display(force=True)
    
    # Grid layout: 2 rows x 3 columns
    grid_start_y = 60
    grid_h = H - grid_start_y - 20
    
    cols = 3
    rows = 2
    
    gap_x = 14
    gap_y = 14
    
    btn_w = (W - 2*16 - (cols-1)*gap_x) // cols
    btn_h = (grid_h - (rows-1)*gap_y) // rows
    
    dashboard_buttons.clear()
    
    for i, (label, fn, bg, fg, icon_fn) in enumerate(DASHBOARD_ITEMS):
        col = i % cols
        row = i // cols
        
        x = 16 + col * (btn_w + gap_x)
        y = grid_start_y + row * (btn_h + gap_y)
        
        b = make_btn(x, y, btn_w, btn_h, label, fn, bg=bg, fg=fg)
        dashboard_buttons.append(b)
        
        # Draw button with text centered (no icons)
        bg_color = getattr(b, "bg", t["btn_bg"])
        fg_color = getattr(b, "fg", t["btn_fg"])
        
        lcd.fill_rect(b.x, b.y, btn_w, btn_h, bg_color)
        draw_border(b.x, b.y, btn_w, btn_h, t["box_border"])
        
        # Draw text centered
        scale = 2
        text_w = len(label) * 8 * scale
        text_h = 16
        tx = b.x + (btn_w - text_w) // 2
        ty = b.y + (btn_h - text_h) // 2
        lcd.text(label, tx, ty, fg_color, bg_color, scale=scale)

def show_dashboard():
    global current_screen
    current_screen = SCREEN_DASHBOARD
    set_breathing_active(False)
    draw_dashboard()

# ============================================================
# Wire return-to-home buttons on screens
# ============================================================
btn_ground_menu.on_press    = show_dashboard
btn_tt_menu.on_press        = show_dashboard
btn_contacts_menu.on_press  = show_dashboard
btn_settings_menu.on_press  = show_dashboard
btn_commmenu_menu.on_press  = show_dashboard
btn_comm_menu.on_press      = show_dashboard

# ============================================================
# Breather colour sync (only update when quiet state changes)
# ============================================================
_last_quiet_for_color = None

def sync_breather_with_lanyard():
    global _last_quiet_for_color
    if breather is None:
        return
    if current_screen != SCREEN_GROUND:
        return
    if mic is None:
        return

    if _last_quiet_for_color is None or mic_quiet != _last_quiet_for_color:
        _last_quiet_for_color = mic_quiet
        if mic_quiet:
            breather.set_color(neo_quiet_color)
        else:
            breather.set_color(neo_active_color)

# ============================================================
# Touch loop helpers + mic poll
# ============================================================
was_down = False
last_tap_ms = 0

def screen_buttons():
    if current_screen == SCREEN_DASHBOARD:
        return dashboard_buttons

    if current_screen == SCREEN_GROUND:
        return [btn_ground_prev, btn_ground_menu, btn_ground_next]

    if current_screen == SCREEN_TIMETABLE:
        return [btn_tt_mon, btn_tt_tue, btn_tt_wed, btn_tt_thu, btn_tt_fri,
                btn_tt_prev, btn_tt_menu, btn_tt_next]

    if current_screen == SCREEN_CONTACTS:
        return [btn_contacts_menu]

    if current_screen == SCREEN_SETTINGS:
        return settings_buttons + [btn_settings_menu]

    if current_screen == SCREEN_COMM_MENU:
        return comm_menu_buttons + [btn_commmenu_menu]

    if current_screen == SCREEN_COMM_CARD:
        return [btn_comm_speak, btn_comm_menu, btn_comm_prev, btn_comm_cats, btn_comm_next]

    return []

def poll_mic_and_update_badge():
    global mic_quiet, mic_rms, _last_mic_poll
    if mic is None:
        return

    now = time.ticks_ms()
    if time.ticks_diff(now, _last_mic_poll) < MIC_POLL_MS:
        return
    _last_mic_poll = now

    info = mic.update()
    mic_quiet = bool(info["quiet"])
    mic_rms = float(info["rms"])

    draw_mic_badge(force=False)
    
    # Update settings display if on sensor tab
    if current_screen == SCREEN_SETTINGS and settings_page == 1:
        _redraw_sensor_content()

def poll_battery_and_update():
    """Poll battery voltage and calculate percentage."""
    global battery_percentage, battery_is_charging, _last_battery_poll
    if battery is None:
        return
    
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_battery_poll) < BATTERY_POLL_MS:
        return
    _last_battery_poll = now
    
    info = battery.update()
    battery_percentage = info["percentage"]
    battery_is_charging = info["is_charging"]
    
    draw_battery_display(force=False)

# ============================================================
# Start
# ============================================================
show_dashboard()

TOUCH_POLL_MS = 25
_last_touch_poll = 0

while True:
    now = time.ticks_ms()

    # Mic update (throttled)
    poll_mic_and_update_badge()

    # Battery update (throttled)
    poll_battery_and_update()

    # NeoPixel breathing update (HARD throttled inside BreathingPixels)
    sync_breather_with_lanyard()
    if breather is not None and current_screen == SCREEN_GROUND:
        breather.tick()

    # Touch read throttled
    if time.ticks_diff(now, _last_touch_poll) >= TOUCH_POLL_MS:
        _last_touch_poll = now

        t = tp.read(samples=7, delay_us=90) if tp.touched() else None
        down = False
        sx = sy = None

        if t:
            rx, ry, p = t
            if p <= CAL.get("P_MAX", 1200):
                sx, sy = raw_to_screen(rx, ry)
                if DEBUG_TOUCH_DOT:
                    debug_dot(sx, sy)
                down = True

        if down and not was_down:
            if time.ticks_diff(now, last_tap_ms) > 160:
                last_tap_ms = now

                for b in screen_buttons():
                    if b.contains(sx, sy):
                        draw_button(b, pressed=True)
                        time.sleep_ms(70)
                        draw_button(b, pressed=False)
                        b.on_press()
                        break

        was_down = down

    time.sleep_ms(8)
