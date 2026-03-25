# main.py
# Entry point: hardware wiring, NeoPixel breather, polling, and main touch loop.
#
# Files needed on Pico:
#   main.py, hw.py, draw.py, screens.py, neo.py
#   app_config.py, ui.py, ili9486.py, xpt2046.py, touch_cal.py
#   mic_level.py, config.json (optional, falls back to defaults)
#
# Wiring:
#   NeoPixels : DIN -> GP10 (330Ω series), 5V -> VBUS, GND -> GND
#   MIC       : OUT -> GP26 (ADC0), VCC -> 3V3, GND -> GND

import time
from touch_cal import CAL
from neo import BreathingPixels
import hw
import draw
import screens
from app_config import BATTERY_POLL_MS

# ============================================================
# Debug
# ============================================================
DEBUG_TOUCH_DOT = False

# ============================================================
# NeoPixel breather
# ============================================================
NEOPIXELS_ENABLED = True
NEO_PIN   = 10
NEO_COUNT = 10

breather = None
try:
    if NEOPIXELS_ENABLED:
        breather = BreathingPixels(
            pin=NEO_PIN, n=NEO_COUNT,
            color=(0, 120, 255),
            max_brightness=0.22,
            inhale_s=4.0, hold_s=1.0, exhale_s=6.0, rest_s=1.0,
            rest_brightness=0.00, write_ms=60, min_delta=2,
        )
except Exception as e:
    print("NeoPixel init failed:", e)

screens.breather = breather

# ============================================================
# Touch coordinate mapping
# ============================================================
def _clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def _map_linear(raw, raw_min, raw_max, out_min, out_max):
    if raw_max == raw_min:
        return out_min
    v = (raw - raw_min) * (out_max - out_min) // (raw_max - raw_min) + out_min
    return _clamp(v, min(out_min, out_max), max(out_min, out_max))

def raw_to_screen(rx, ry):
    c = CAL
    if c.get("SWAP_XY", False): rx, ry = ry, rx
    if c.get("FLIP_X",  False): rx = 3800 - rx
    if c.get("FLIP_Y",  False): ry = 3800 - ry
    x = _map_linear(rx, c["RAW_X_LEFT"], c["RAW_X_RIGHT"], 0, hw.W - 1)
    y = _map_linear(ry, c["RAW_Y_TOP"],  c["RAW_Y_BOT"],   0, hw.H - 1)
    return x, y

def debug_dot(x, y):
    hw.lcd.fill_rect(x - 2, y - 2, 5, 5, hw.RED)

# ============================================================
# Polling — mic and battery
# ============================================================
_last_mic_poll     = 0
_last_battery_poll = 0

def poll_mic():
    global _last_mic_poll
    if hw.mic is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_mic_poll) < hw.MIC_POLL_MS:
        return
    _last_mic_poll = now
    info = hw.mic.update()
    new_quiet = bool(info["quiet"])
    new_rms   = float(info["rms"])
    changed = (new_quiet != draw.mic_quiet
               or abs(new_rms - draw.mic_rms) > 0.002)
    draw.mic_quiet = new_quiet
    draw.mic_rms   = new_rms
    draw.draw_mic_badge(force=False)
    if changed and (screens.current_screen == screens.SCREEN_SETTINGS
                    and screens.settings_page == 1):
        screens._refresh_sensor_text()

def poll_battery():
    global _last_battery_poll
    if hw.battery is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_battery_poll) < BATTERY_POLL_MS:
        return
    _last_battery_poll = now
    info = hw.battery.update()
    draw.battery_percentage  = info["percentage"]
    draw.battery_is_charging = info["is_charging"]
    draw.draw_battery_display(force=False)

# ============================================================
# Start
# ============================================================
screens.show_dashboard()

TOUCH_POLL_MS  = 25
_last_touch_poll = 0
was_down  = False
last_tap_ms = 0
_ground_was_down = False

while True:
    now = time.ticks_ms()

    poll_mic()
    poll_battery()

    screens.sync_breather_with_lanyard()
    if breather is not None and screens.current_screen == screens.SCREEN_GROUND:
        breather.tick()

    if time.ticks_diff(now, _last_touch_poll) >= TOUCH_POLL_MS:
        _last_touch_poll = now

        raw = hw.tp.read(samples=7, delay_us=90) if hw.tp.touched() else None
        down = False
        sx = sy = None

        if raw:
            rx, ry, p = raw
            if p <= CAL.get("P_MAX", 1200):
                sx, sy = raw_to_screen(rx, ry)
                if DEBUG_TOUCH_DOT:
                    debug_dot(sx, sy)
                down = True

        if down and not was_down:
            if time.ticks_diff(now, last_tap_ms) > 160:
                last_tap_ms = now
                for b in screens.screen_buttons():
                    if b.contains(sx, sy):
                        draw.draw_button(b, pressed=True)
                        time.sleep_ms(70)
                        draw.draw_button(b, pressed=False)
                        b.on_press()
                        break

        was_down = down

    # Physical grounding shortcut button on GP4 (active low)
    ground_now = not hw.ground_btn.value()
    if ground_now and not _ground_was_down:
        screens.show_grounding()
    _ground_was_down = ground_now

    time.sleep_ms(8)
