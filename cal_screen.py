# cal_screen.py
# 4-point touch calibration wizard.
# Tap each crosshair target to calibrate the touchscreen.
# Saves to touch_cal.py and resets the device.

import time
import hw

_ARM   = 22    # crosshair arm length in px
_THICK = 3     # crosshair line thickness
_GAP   = 6     # gap around centre dot


def run():
    """Run the full calibration wizard. Saves and resets on success."""
    lcd = hw.lcd
    tp  = hw.tp
    W   = hw.W
    H   = hw.H

    BG  = 0x0000   # black
    FG  = 0xFFFF   # white
    ACC = 0x07FF   # cyan — active target
    OK  = 0x07E0   # green — confirm flash

    MARGIN_X = W // 8   # 60 px for W=480
    MARGIN_Y = H // 8   # 40 px for H=320

    # Clockwise from top-left
    targets = [
        (MARGIN_X,     MARGIN_Y,     "TOP LEFT"),
        (W - MARGIN_X, MARGIN_Y,     "TOP RIGHT"),
        (W - MARGIN_X, H - MARGIN_Y, "BOTTOM RIGHT"),
        (MARGIN_X,     H - MARGIN_Y, "BOTTOM LEFT"),
    ]

    # --- Introduction screen ---
    lcd.fill(BG)
    lcd.text("TOUCH CALIBRATION", 20,  70, FG,  BG, scale=2)
    lcd.text("Tap each + crosshair",   20, 110, ACC, BG, scale=2)
    lcd.text("to calibrate the screen.", 20, 135, ACC, BG, scale=2)
    lcd.text("Hold still when tapping.", 20, 170, FG,  BG, scale=1)
    time.sleep_ms(2500)

    raw_pts = []

    for i, (tx, ty, name) in enumerate(targets):
        lcd.fill(BG)
        lcd.text("TOUCH CALIBRATION", 20, 10, FG, BG, scale=2)
        _draw_progress(lcd, i, len(targets), FG, BG)
        lcd.text(name,               20, 55, ACC, BG, scale=2)
        lcd.text("Tap the crosshair", 20, 80, FG,  BG, scale=1)
        _crosshair(lcd, tx, ty, ACC)

        raw = _wait_tap(tp)
        if raw is None:
            _error(lcd, BG, FG)
            return

        raw_pts.append(raw)
        _crosshair(lcd, tx, ty, OK)   # green flash = confirmed
        time.sleep_ms(500)

    # --- Calculate ---
    cal = _compute(raw_pts, MARGIN_X, MARGIN_Y, W, H)
    if cal is None:
        _error(lcd, BG, FG)
        return

    # --- Save and reboot ---
    _save(cal)

    lcd.fill(BG)
    lcd.text("CALIBRATION SAVED!", 20, 110, OK, BG, scale=2)
    lcd.text("Restarting device...", 20, 150, FG, BG, scale=1)
    time.sleep_ms(2500)

    import machine
    machine.reset()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _crosshair(lcd, cx, cy, col):
    # Horizontal arms (gap around centre)
    lcd.fill_rect(cx - _ARM,       cy - 1, _ARM - _GAP,     _THICK, col)
    lcd.fill_rect(cx + _GAP,       cy - 1, _ARM - _GAP,     _THICK, col)
    # Vertical arms
    lcd.fill_rect(cx - 1, cy - _ARM,       _THICK, _ARM - _GAP, col)
    lcd.fill_rect(cx - 1, cy + _GAP,       _THICK, _ARM - _GAP, col)
    # Centre dot
    lcd.fill_rect(cx - 3, cy - 3, 7, 7, col)


def _draw_progress(lcd, done, total, fg, bg):
    bar_x, bar_y, bar_w, bar_h = 20, 36, hw.W - 40, 8
    lcd.fill_rect(bar_x, bar_y, bar_w, bar_h, fg)
    filled = bar_w * done // total
    if filled > 2:
        lcd.fill_rect(bar_x + 1, bar_y + 1, filled - 2, bar_h - 2, fg)
    rest = bar_w - filled
    if rest > 1:
        lcd.fill_rect(bar_x + filled, bar_y + 1, rest - 1, bar_h - 2, bg)


def _error(lcd, bg, fg):
    lcd.fill(bg)
    lcd.text("CALIBRATION FAILED",      20, 110, 0xF800, bg, scale=2)
    lcd.text("No touch detected.",       20, 150, fg,    bg, scale=1)
    lcd.text("Returning to settings...", 20, 170, fg,    bg, scale=1)
    time.sleep_ms(2500)


# ---------------------------------------------------------------------------
# Touch sampling
# ---------------------------------------------------------------------------

def _wait_tap(tp):
    """Wait up to 30 s for a clean tap. Returns median raw (x, y) or None."""
    deadline = time.ticks_add(time.ticks_ms(), 30_000)
    while not tp.touched():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return None
        time.sleep_ms(20)

    time.sleep_ms(80)   # debounce

    xs, ys = [], []
    for _ in range(16):
        r = tp.get_raw(samples=7, delay_us=300)
        if r is not None:
            xs.append(r[0])
            ys.append(r[1])
        time.sleep_ms(25)

    # Wait for release
    while tp.touched():
        time.sleep_ms(20)
    time.sleep_ms(150)

    if not xs:
        return None
    xs.sort()
    ys.sort()
    mid = len(xs) // 2
    return (xs[mid], ys[mid])


# ---------------------------------------------------------------------------
# Calibration calculation
# ---------------------------------------------------------------------------

def _compute(raw_pts, margin_x, margin_y, W, H):
    (rx_tl, ry_tl) = raw_pts[0]   # top-left target
    (rx_tr, ry_tr) = raw_pts[1]   # top-right target
    (rx_br, ry_br) = raw_pts[2]   # bottom-right target
    (rx_bl, ry_bl) = raw_pts[3]   # bottom-left target

    # Detect axis swap: moving left→right changes screen X.
    # If raw X changes more than raw Y on that move, axes are not swapped.
    dx_horiz = abs(rx_tr - rx_tl)
    dy_horiz = abs(ry_tr - ry_tl)
    SWAP_XY  = dy_horiz > dx_horiz

    if SWAP_XY:
        rx_tl, ry_tl = ry_tl, rx_tl
        rx_tr, ry_tr = ry_tr, rx_tr
        rx_br, ry_br = ry_br, rx_br
        rx_bl, ry_bl = ry_bl, rx_bl

    # Average the two readings at each screen edge
    raw_x_at_left  = (rx_tl + rx_bl) // 2
    raw_x_at_right = (rx_tr + rx_br) // 2
    raw_y_at_top   = (ry_tl + ry_tr) // 2
    raw_y_at_bot   = (ry_bl + ry_br) // 2

    # Known screen positions of the targets
    sx_left  = margin_x
    sx_right = W - margin_x
    sy_top   = margin_y
    sy_bot   = H - margin_y

    span_x = sx_right - sx_left
    span_y = sy_bot   - sy_top
    if span_x == 0 or span_y == 0:
        return None

    # Extrapolate raw values to screen edges (0 and W-1 / H-1)
    scale_x        = (raw_x_at_right - raw_x_at_left) / span_x
    raw_x_at_0     = int(raw_x_at_left  - scale_x * sx_left)
    raw_x_at_wm1   = int(raw_x_at_right + scale_x * (W - 1 - sx_right))

    scale_y        = (raw_y_at_bot - raw_y_at_top) / span_y
    raw_y_at_0     = int(raw_y_at_top - scale_y * sy_top)
    raw_y_at_hm1   = int(raw_y_at_bot + scale_y * (H - 1 - sy_bot))

    return {
        "RAW_X_LEFT":  raw_x_at_0,
        "RAW_X_RIGHT": raw_x_at_wm1,
        "RAW_Y_TOP":   raw_y_at_0,
        "RAW_Y_BOT":   raw_y_at_hm1,
        "W":       W,
        "H":       H,
        "SWAP_XY": SWAP_XY,
        "FLIP_X":  False,
        "FLIP_Y":  False,
        "P_MAX":   250,
        "SAMPLES": 15,
    }


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _save(cal):
    lines = [
        "# touch_cal.py",
        "# Auto-generated by calibration wizard",
        "",
        "CAL = {",
        '    "RAW_X_LEFT":  {},'.format(cal["RAW_X_LEFT"]),
        '    "RAW_X_RIGHT": {},'.format(cal["RAW_X_RIGHT"]),
        '    "RAW_Y_TOP":   {},'.format(cal["RAW_Y_TOP"]),
        '    "RAW_Y_BOT":   {},'.format(cal["RAW_Y_BOT"]),
        '    "W": {},'.format(cal["W"]),
        '    "H": {},'.format(cal["H"]),
        '    "SWAP_XY": {},'.format(str(cal["SWAP_XY"])),
        '    "FLIP_X":  False,',
        '    "FLIP_Y":  False,',
        '    "P_MAX":   250,',
        '    "SAMPLES": 15,',
        "}",
    ]
    with open("touch_cal.py", "w") as f:
        f.write("\n".join(lines) + "\n")
