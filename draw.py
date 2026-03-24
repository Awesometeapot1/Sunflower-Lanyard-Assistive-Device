# draw.py
# Theme system and all drawing helpers.
# Imports hardware from hw.py; state is updated by main.py's polling functions.

import time
from ui import Button
import hw

# ---------------------------------------------------------------------------
# Shared state — written by main.py poll functions, read by draw helpers
# ---------------------------------------------------------------------------
theme_index      = 0
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
# Tuple layout: (name, title_bg, title_fg, screen_bg, box_bg, box_border, btn_bg, btn_fg, accent)
THEMES = [
    # High-contrast modern dark
    ("NEON_DARK",  0x0000, 0x07FF, 0x0000, 0x0000, 0x07FF, 0x07E0, 0x0000, 0xF81F),
    # Soft warm light — warm brown title, peach-cream buttons (visible on white)
    ("CREAM",      0xB40A, 0xFFFF, 0xFFFF, 0xFFFF, 0x8410, 0xF695, 0x0000, 0x07E0),
    # Cool icy blue
    ("GLACIER",    0x07FF, 0x0000, 0xCFFF, 0xCFFF, 0x001F, 0x07FF, 0x0000, 0x001F),
    # Gentle dark — deep navy, soft blue text, good for night/low light
    ("NIGHT",      0x10E7, 0xB65C, 0x10E7, 0x216A, 0x53D6, 0x3230, 0xB65C, 0x05B9),
    # Sunset — golden buttons visible against orange screen
    ("SUNSET",     0x8A22, 0xFFFF, 0xFD20, 0xFD20, 0xF800, 0xFE4A, 0x0000, 0xF81F),
    # Steel grey
    ("STEEL",      0x4208, 0xFFFF, 0x8410, 0x8410, 0xFFFF, 0x4208, 0xFFFF, 0x07FF),
    # Calming lavender — actual soft purple (was neon magenta)
    ("LAVENDER",   0x5192, 0xFFFF, 0xEF1F, 0xEF1F, 0x5192, 0xB51A, 0x0000, 0x7A99),
    # High-contrast monochrome
    ("MONO",       0xFFFF, 0x0000, 0x8410, 0x8410, 0xFFFF, 0x0000, 0xFFFF, 0xFFFF),
]

def th():
    n, tbg, tfg, sbg, bbg, bbdr, btnbg, btnfg, acc = THEMES[theme_index]
    return {"name": n, "title_bg": tbg, "title_fg": tfg, "screen_bg": sbg,
            "box_bg": bbg, "box_border": bbdr, "btn_bg": btnbg, "btn_fg": btnfg, "accent": acc}

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
        bg, fg, label = hw.GREEN, hw.BLACK, "QUIET OK"
    else:
        bg, fg, label = hw.MAG,   hw.WHITE, "LOUD"
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
                fg = hw.WHITE if t["box_bg"] == hw.BLACK else hw.BLACK
                hw.lcd.text(line, x + 8, ty, fg, t["box_bg"], scale=scale)
                ty    += line_h
                shown += 1
            return
