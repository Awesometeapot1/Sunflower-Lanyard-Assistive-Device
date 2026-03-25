# draw.py
# Theme system and all drawing helpers.
# Imports hardware from hw.py; state is updated by main.py's polling functions.

import time
from ui import Button
import hw
from app_config import THEME_INDEX as _initial_theme

# ---------------------------------------------------------------------------
# Shared state — written by main.py poll functions, read by draw helpers
# ---------------------------------------------------------------------------
theme_index      = _initial_theme
mic_quiet        = False
mic_rms          = 0.0
battery_percentage   = 0
battery_is_charging  = False

_last_badge_draw  = 0
_last_badge_state = None
_last_battery_draw = 0

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------
# Tuple layout: (name, bg, text, btn, btn_text, accent1, accent2, border, highlight)
# All RGB565 colour values are pre-swapped (R↔B) because this panel's BGR
# subpixel order is fixed regardless of the MADCTL BGR bit.
THEMES = [
    # High-contrast modern dark
    ("NEON_DARK",
        0x0000,  # bg
        0xFFE0,  # text
        0x1082,  # btn
        0xFFE0,  # btn_text
        0x07E0,  # accent1
        0xF81F,  # accent2
        0xFFE0,  # border
        0xF81F,  # highlight
    ),
    # Warm light — soft peach
    ("CREAM",
        0xD79F,  # bg        R=255 G=242 B=210  warm ivory
        0x2104,  # text      near-black
        0xBEFD,  # btn       R=239 G=222 B=189  warm beige
        0x2104,  # btn_text
        0x7D18,  # accent1   R=197 G=162 B=123  warm tan
        0x4BB3,  # accent2   R=156 G=117 B=74   warm brown
        0x2104,  # border
        0x9E3F,  # highlight R=255 G=198 B=156  warm peach
    ),
    # Cool mint teal
    ("GLACIER",
        0xF7D8,  # bg        R=197 G=251 B=247  very light mint
        0x49E3,  # text      R=25  G=61  B=74   dark teal
        0x49E3,  # btn       dark teal
        0xD6F1,  # btn_text  R=140 G=222 B=214  light cyan
        0xC6A0,  # accent1   R=0   G=214 B=197  bright teal
        0x9D20,  # accent2   R=0   G=166 B=156  medium teal
        0xC6A0,  # border    bright teal
        0xE780,  # highlight R=0   G=243 B=230  vivid cyan
    ),
    # Dark navy — night mode
    ("NIGHT",
        0x1021,  # bg
        0xD6D6,  # text
        0x2883,  # btn
        0x9491,  # btn_text
        0x6289,  # accent1
        0xFA69,  # accent2
        0xD6D6,  # border
        0xBCE3,  # highlight
    ),
    # Warm orange sunset
    ("SUNSET",
        0x133C,  # bg        R=230 G=100 B=15   warm amber-orange
        0xFFFF,  # text      white
        0x0A57,  # btn       R=189 G=73  B=8    dark amber
        0xFFFF,  # btn_text  white
        0x175F,  # accent1   R=255 G=235 B=16   bright yellow
        0x041F,  # accent2   R=255 G=130 B=0    orange
        0xFFFF,  # border    white
        0x061F,  # highlight R=255 G=194 B=0    deep gold
    ),
    # Steel grey
    ("STEEL",
        0x528A,  # bg
        0xFFFF,  # text
        0x8C51,  # btn
        0xFFFF,  # btn_text
        0xCE59,  # accent1
        0x528A,  # accent2
        0xFFFF,  # border
        0x7BCF,  # highlight
    ),
    # Soft purple pastel
    ("LAVENDER",
        0xF51A,  # bg        R=214 G=162 B=247  light lavender
        0x2104,  # text      near-black
        0xE538,  # btn       R=197 G=166 B=230  medium lavender
        0x2104,  # btn_text
        0xD476,  # accent1   R=181 G=142 B=214  muted lavender
        0xB331,  # accent2   R=140 G=101 B=181  deeper purple
        0x2104,  # border
        0xFE3C,  # highlight R=230 G=198 B=255  bright violet
    ),
    # High-contrast B&W
    ("MONO",
        0x0000,  # bg
        0xFFFF,  # text
        0x3186,  # btn
        0xFFFF,  # btn_text
        0x6B4D,  # accent1
        0xFFFF,  # accent2
        0xFFFF,  # border
        0xFFFF,  # highlight
    ),
]


def th():
    n, bg, text, btn, btn_text, accent1, accent2, border, highlight = THEMES[theme_index]
    return {"name": n, "title_bg": bg, "title_fg": text, "screen_bg": bg,
            "box_bg": bg, "box_border": border, "btn_bg": btn, "btn_fg": btn_text,
            "accent": accent1, "accent2": accent2, "highlight": highlight}

# ---------------------------------------------------------------------------
# Low-level drawing helpers
# ---------------------------------------------------------------------------
def draw_border(x, y, w, h, c):
    hw.lcd.fill_rect(x,     y,       w, 1, c)
    hw.lcd.fill_rect(x,     y+h-1,   w, 1, c)
    hw.lcd.fill_rect(x,     y,       1, h, c)
    hw.lcd.fill_rect(x+w-1, y,       1, h, c)

def draw_mic_badge(force=False):
    global _last_badge_draw, _last_badge_state
    if hw.mic is None:
        return
    now = time.ticks_ms()
    if (not force) and time.ticks_diff(now, _last_badge_draw) < hw.MIC_DRAW_THROTTLE:
        return
    state = mic_quiet
    if (not force) and state == _last_badge_state:
        _last_badge_draw = now
        return
    t = th()
    bx, by, bw, bh = 160, 10, 90, 28
    if state:
        bg, fg, label = t["accent"], hw.BLACK, "QUIET OK"
    else:
        bg, fg, label = t["accent2"], hw.WHITE, "LOUD"
    hw.lcd.fill_rect(bx, by, bw, bh, bg)
    draw_border(bx, by, bw, bh, t["box_border"])
    tw = len(label) * 8
    hw.lcd.text(label, bx + (bw - tw) // 2, by + (bh - 8) // 2, fg, bg, scale=1)
    _last_badge_state = state
    _last_badge_draw  = now

def draw_battery_display(force=False):
    global _last_battery_draw
    if hw.battery is None:
        return
    now = time.ticks_ms()
    if (not force) and time.ticks_diff(now, _last_battery_draw) < 500:
        return
    _last_battery_draw = now
    t = th()
    color = hw.battery.get_battery_color()
    pct   = "{}%".format(battery_percentage)
    tw    = len(pct) * 8
    hw.lcd.text(pct, hw.W - tw - 12, 14, color, t["title_bg"], scale=1)

def draw_title_bar(title):
    global _last_badge_state
    _last_badge_state = None
    t = th()
    hw.lcd.fill_rect(0, 0, hw.W, 48, t["title_bg"])
    hw.lcd.text(title, 12, 14, t["title_fg"], t["title_bg"], scale=2)
    draw_mic_badge(force=True)
    draw_battery_display(force=True)

def draw_indicator(text):
    t = th()
    tw      = len(text) * 8 * 2
    reserve = 140 if hw.mic is not None else 0
    hw.lcd.text(text, hw.W - reserve - tw - 12, 14, t["title_fg"], t["title_bg"], scale=2)

def wrap_text(s, max_chars):
    words = s.split(" ")
    lines = []
    cur   = ""
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
                if i != len(parts) - 1:
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

def draw_button(btn, pressed=False):
    t      = th()
    bg     = getattr(btn, "bg", t["btn_bg"])
    fg     = getattr(btn, "fg", t["btn_fg"])
    border = t["box_border"]
    if pressed:
        bg, fg = fg, bg
    hw.lcd.fill_rect(btn.x, btn.y, btn.w, btn.h, bg)
    draw_border(btn.x, btn.y, btn.w, btn.h, border)
    scale  = 2
    text_w = len(btn.label) * 8 * scale
    hw.lcd.text(btn.label,
                btn.x + (btn.w - text_w) // 2,
                btn.y + (btn.h - 16)     // 2,
                fg, bg, scale=scale)

def make_btn(x, y, w, h, label, on_press, bg=None, fg=None):
    b = Button(x, y, w, h, label, on_press)
    if bg is not None: b.bg = bg
    if fg is not None: b.fg = fg
    return b

def draw_text_box(text, x, y, w, h, prefer_scale=2):
    t = th()
    hw.lcd.fill_rect(x, y, w, h, t["box_bg"])
    draw_border(x, y, w, h, t["box_border"])
    for scale in (prefer_scale, 1):
        max_chars = (w - 16) // (8 * scale)
        lines     = wrap_text(text, max_chars)
        line_h    = 8 * scale + 2
        max_lines = (h - 16) // line_h
        if len(lines) <= max_lines or scale == 1:
            ty    = y + 8
            shown = 0
            for line in lines:
                if shown >= max_lines:
                    break
                fg = t["title_fg"]
                hw.lcd.text(line, x + 8, ty, fg, t["box_bg"], scale=scale)
                ty    += line_h
                shown += 1
            return
