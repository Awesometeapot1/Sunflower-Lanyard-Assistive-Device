# screens.py
# All screen draw/show functions, buttons, and screen state.

import time
import json
import draw
import hw
from ui import Button
from draw import (th, draw_button, make_btn, draw_border,
                  draw_text_box, draw_title_bar, draw_indicator,
                  draw_battery_display, wrap_text, THEMES)
from hw import lcd, W, H, BLACK, WHITE, RED, GREEN, BLUE, CYAN, MAG, ORNG, GREY, YELL
from app_config import (
    TIMETABLE, CONTACT_TEXT,
    FAV_CARDS, CAT_NEEDS, CAT_SENSORY, CAT_RESPONSES, CAT_FEELINGS, CAT_STATUS,
    MIC_QUIET_THRESH, NEO_QUIET_COLOR, NEO_ACTIVE_COLOR,
)

# ---------------------------------------------------------------------------
# Injected by main.py after hardware init
# ---------------------------------------------------------------------------
breather = None

# ---------------------------------------------------------------------------
# Screen identifiers
# ---------------------------------------------------------------------------
SCREEN_DASHBOARD = "dashboard"
SCREEN_GROUND    = "grounding"
SCREEN_TIMETABLE = "timetable"
SCREEN_CONTACTS  = "contacts"
SCREEN_SETTINGS  = "settings"
SCREEN_COMM_MENU = "comm_menu"
SCREEN_COMM_CARD = "comm_card"

current_screen = SCREEN_DASHBOARD

# ---------------------------------------------------------------------------
# Shared nav layout constants
# ---------------------------------------------------------------------------
NAV_H  = 80
NAV_Y  = H - (NAV_H + 20)
NAV_X0 = 20
NAV_GAP = 12
NAV_W  = (W - 40 - 2 * NAV_GAP) // 3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def set_breathing_active(active):
    if breather is None:
        return
    breather.set_enabled(bool(active))
    if not active:
        try:
            breather.off()
        except Exception:
            pass

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

# ---------------------------------------------------------------------------
# Grounding screen
# ---------------------------------------------------------------------------
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
    "textures. Stay 1 minute.",
]
page_index = 0

btn_ground_prev = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_ground_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)
btn_ground_next = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)

def draw_grounding():
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("GROUNDING")
    draw_indicator("{}/{}".format(page_index + 1, len(GROUNDING_PAGES)))
    draw_text_box(GROUNDING_PAGES[page_index],
                  16, 60, W - 32, H - 60 - (NAV_H + 30), prefer_scale=2)
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

# ---------------------------------------------------------------------------
# Timetable screen
# ---------------------------------------------------------------------------
TT_DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
tt_day_index    = 0
tt_page         = 0
TT_ITEMS_PER_PAGE = 3

btn_tt_prev = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_tt_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)
btn_tt_next = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)

btn_tt_mon = Button(0, 0, 1, 1, "M", lambda: None)
btn_tt_tue = Button(0, 0, 1, 1, "T", lambda: None)
btn_tt_wed = Button(0, 0, 1, 1, "W", lambda: None)
btn_tt_thu = Button(0, 0, 1, 1, "T", lambda: None)
btn_tt_fri = Button(0, 0, 1, 1, "F", lambda: None)

def _tt_current_day():
    return TT_DAYS[tt_day_index]

def _tt_day_items(day):
    return TIMETABLE.get(day, [])

def _tt_total_pages(day):
    items = _tt_day_items(day)
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
    if tt_page < _tt_total_pages(_tt_current_day()) - 1:
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

    days_y, days_h = 56, 44
    x0, gap = 16, 8
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

    day   = _tt_current_day()
    items = _tt_day_items(day)
    pages = _tt_total_pages(day)

    box_x = 16
    box_y = days_y + days_h + 10
    box_w = W - 32
    box_h = H - box_y - (NAV_H + 30)

    draw_indicator("{}  {}/{}".format(day, tt_page + 1, pages))

    if not items:
        draw_text_box("No lessons saved for this day yet.",
                      box_x, box_y, box_w, box_h, prefer_scale=2)
    else:
        start = tt_page * TT_ITEMS_PER_PAGE
        chunk = items[start:start + TT_ITEMS_PER_PAGE]
        lines = []
        for p in chunk:
            time_str = (p.get("time",  "") or "").strip()
            title    = (p.get("title", "") or "").strip()
            room     = (p.get("room",  "") or "").strip()
            note     = (p.get("note",  "") or "").strip()
            header   = "{} {}".format(time_str, title).strip()
            if room:
                header += "  ({})".format(room)
            lines.append(header)
            if note:
                lines.append("- " + note)
            lines.append("")
        draw_text_box("\n".join(lines).strip(), box_x, box_y, box_w, box_h, prefer_scale=2)

    draw_button(btn_tt_prev)
    draw_button(btn_tt_menu)
    draw_button(btn_tt_next)

def show_timetable():
    global current_screen
    current_screen = SCREEN_TIMETABLE
    set_breathing_active(False)
    draw_timetable()

# ---------------------------------------------------------------------------
# Contacts screen
# ---------------------------------------------------------------------------
btn_contacts_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "MENU", lambda: None)

def show_contacts():
    global current_screen
    current_screen = SCREEN_CONTACTS
    set_breathing_active(False)
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("CONTACTS")
    draw_text_box(CONTACT_TEXT, 16, 60, W - 32, H - 60 - (NAV_H + 30), prefer_scale=2)
    draw_button(btn_contacts_menu)

# ---------------------------------------------------------------------------
# Settings screen
# ---------------------------------------------------------------------------
settings_buttons  = []
settings_page     = 0
mic_thresh_live   = MIC_QUIET_THRESH
neo_quiet_color   = NEO_QUIET_COLOR
neo_active_color  = NEO_ACTIVE_COLOR
neo_preset_index  = -1
_last_quiet_for_color = None

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
btn_settings_cal  = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "CAL",  lambda: None)
btn_settings_tab0 = Button(20,  60, 210, 30, "THEMES",       lambda: None)
btn_settings_tab1 = Button(250, 60, 210, 30, "SENSOR & NEO", lambda: None)

def _do_calibrate():
    import cal_screen
    cal_screen.run()

def apply_theme(idx):
    draw.theme_index = idx
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
    _last_quiet_for_color = None
    save_config_partial(neo_quiet_color=list(qc), neo_active_color=list(ac))
    show_settings()

def adjust_mic_thresh(delta):
    global mic_thresh_live
    mic_thresh_live = round(max(0.002, min(0.08, mic_thresh_live + delta)), 3)
    if hw.mic is not None:
        hw.mic.quiet_threshold = mic_thresh_live
    save_config_partial(mic_quiet_thresh=mic_thresh_live)
    _redraw_sensor_content()

def _redraw_sensor_content():
    global settings_buttons
    t = th()
    lcd.fill_rect(0, 96, W, H - 96 - (NAV_H + 22), t["screen_bg"])
    settings_buttons = [btn_settings_tab0, btn_settings_tab1]

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

    lcd.text("MIC SENSITIVITY", 22, 163, t["box_border"], t["screen_bg"], scale=2)
    mt_y, mt_h = 183, 32
    btn_m = make_btn(22,  mt_y, 58, mt_h, "-", lambda: adjust_mic_thresh(-0.002))
    btn_p = make_btn(400, mt_y, 58, mt_h, "+", lambda: adjust_mic_thresh(+0.002))
    settings_buttons += [btn_m, btn_p]
    draw_button(btn_m)
    draw_button(btn_p)

    _refresh_sensor_text()

def _refresh_sensor_text():
    """Lightweight update: redraw only the 3 mic status text lines."""
    t = th()
    # Erase previous text area before redrawing to avoid ghosting
    lcd.fill_rect(88, 165, W - 100, 45, t["screen_bg"])
    lcd.text("Threshold: {:.3f}".format(mic_thresh_live),
             88, 170, t["box_border"], t["screen_bg"], scale=1)
    rms_color = GREEN if draw.mic_quiet else RED
    lcd.text("Current RMS: {:.3f}".format(draw.mic_rms),
             88, 185, rms_color, t["screen_bg"], scale=1)
    lcd.text("QUIET" if draw.mic_quiet else "LOUD",
             88, 200, rms_color, t["screen_bg"], scale=1)

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
    btn_settings_tab0 = make_btn(20,  60, 210, 30, "THEMES",
                                 lambda: set_settings_page(0), bg=t0_bg, fg=t0_fg)
    btn_settings_tab1 = make_btn(250, 60, 210, 30, "SENSOR & NEO",
                                 lambda: set_settings_page(1), bg=t1_bg, fg=t1_fg)
    draw_button(btn_settings_tab0)
    draw_button(btn_settings_tab1)
    settings_buttons = [btn_settings_tab0, btn_settings_tab1]

    if settings_page == 0:
        gx, gy   = 20, 98
        gw, gh   = W - 40, H - 98 - (NAV_H + 30)
        cols     = 3
        rows     = (len(THEMES) + cols - 1) // cols
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
            if i == draw.theme_index:
                draw_border(x,   y,   bw,   bh,   t["accent"])
                draw_border(x+1, y+1, bw-2, bh-2, t["accent"])
            settings_buttons.append(b)
    else:
        _redraw_sensor_content()

    draw_button(btn_settings_menu)
    draw_button(btn_settings_cal)

# ---------------------------------------------------------------------------
# Communication cards
# ---------------------------------------------------------------------------
def speak(text):
    print("SPEAK:", text)

COMM_CATEGORIES = [
    ("FAVOURITES", FAV_CARDS,     YELL,  BLACK),
    ("NEEDS",      CAT_NEEDS,     GREEN, BLACK),
    ("SENSORY",    CAT_SENSORY,   MAG,   WHITE),
    ("RESPONSES",  CAT_RESPONSES, CYAN,  BLACK),
    ("FEELINGS",   CAT_FEELINGS,  ORNG,  BLACK),
    ("STATUS",     CAT_STATUS,    GREY,  WHITE),
]

comm_menu_buttons = []
comm_cards     = FAV_CARDS
comm_cat_name  = "FAVOURITES"
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
    cols  = 2
    rows  = (len(COMM_CATEGORIES) + 1) // 2
    grid_x, grid_y = 20, 70
    grid_w = W - 40
    grid_h = H - 70 - (NAV_H + 30)
    gapx, gapy = 12, 12
    bw = (grid_w - gapx) // 2
    bh = (grid_h - (rows - 1) * gapy) // rows
    for i, (name, cards, bg, fg) in enumerate(COMM_CATEGORIES):
        c = i % cols
        r = i // cols
        x = grid_x + c * (bw + gapx)
        y = grid_y + r * (bh + gapy)
        def make_open(idx=i):
            return lambda: open_category(idx)
        comm_menu_buttons.append(make_btn(x, y, bw, bh, name, make_open(), bg=bg, fg=fg))

def show_comm_menu():
    global current_screen
    current_screen = SCREEN_COMM_MENU
    set_breathing_active(False)
    lcd.fill(th()["screen_bg"])
    draw_title_bar("COMM CARDS")
    build_comm_menu_buttons()
    for b in comm_menu_buttons:
        draw_button(b)
    draw_button(btn_commmenu_menu)

ACT_H  = 44
ACT_Y  = 48 + 8
ACT_X0 = 20
ACT_GAP = 12
ACT_W  = (W - 40 - ACT_GAP) // 2

btn_comm_prev  = Button(NAV_X0 + 0*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "PREV", lambda: None)
btn_comm_cats  = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "CATS", lambda: None)
btn_comm_next  = Button(NAV_X0 + 2*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "NEXT", lambda: None)
btn_comm_speak = make_btn(ACT_X0,           ACT_Y, ACT_W, ACT_H, "SPEAK", lambda: None, bg=BLUE, fg=WHITE)
btn_comm_menu  = make_btn(ACT_X0+ACT_W+ACT_GAP, ACT_Y, ACT_W, ACT_H, "MENU",  lambda: None)

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
    draw_indicator("{}/{}".format(comm_card_index + 1, len(comm_cards)))

    icon_scale = 4
    ix = card_x + (card_w - len(icon) * 8 * icon_scale) // 2
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

    lines   = wrap_text(phrase, max_chars)
    line_h  = 8 * scale + 6
    total_h = len(lines) * line_h
    start_y = iy + 8 * icon_scale + 18
    rem_h   = (card_y + card_h) - start_y - 12
    y       = start_y + (rem_h - total_h) // 2
    for line in lines:
        x = card_x + (card_w - len(line) * 8 * scale) // 2
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

btn_comm_prev.on_press  = comm_prev
btn_comm_next.on_press  = comm_next
btn_comm_cats.on_press  = show_comm_menu
btn_comm_speak.on_press = lambda: speak(comm_cards[comm_card_index][1])

def do_sos():
    global comm_cards, comm_cat_name, comm_card_index
    comm_cat_name  = "NEEDS"
    comm_cards     = CAT_NEEDS
    comm_card_index = 0
    show_comm_card()

# ---------------------------------------------------------------------------
# Dashboard pixel-art icons (bx, by, bh, fg, bg)
# ---------------------------------------------------------------------------
def _icon_sos(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    lcd.fill_rect(cx-4, by+4,      8, bh-18, fg)
    lcd.fill_rect(cx-4, by+bh-10,  8, 7,     fg)

def _icon_ground(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    for i in range(6):
        w = 2 + i * 2
        lcd.fill_rect(cx - w//2, by+4+i*2, w, 2, fg)
    for i in range(5, -1, -1):
        w = 2 + i * 2
        lcd.fill_rect(cx - w//2, by+16+(5-i)*2, w, 2, fg)
    lcd.fill_rect(cx-2, by+27, 4, bh-31, fg)

def _icon_time(bx, by, bh, fg, bg):
    x0, y0, sz = bx+4, by+4, bh-8
    draw_border(x0, y0, sz, sz, fg)
    lcd.fill_rect(x0+1,    y0+sz//3,   sz-2, 1, fg)
    lcd.fill_rect(x0+1,    y0+2*sz//3, sz-2, 1, fg)
    lcd.fill_rect(x0+sz//2, y0+1, 1, sz-2, fg)

def _icon_comm(bx, by, bh, fg, bg):
    x0, y0, w, h = bx+3, by+3, bh-6, bh-13
    lcd.fill_rect(x0,   y0,   w,   h,   fg)
    lcd.fill_rect(x0+2, y0+2, w-4, h-4, bg)
    lcd.fill_rect(x0+5, y0+h, 8,   5,   fg)

def _icon_contact(bx, by, bh, fg, bg):
    cx = bx + bh // 2
    lcd.fill_rect(cx-5, by+3,  10, 10,     fg)
    lcd.fill_rect(cx-8, by+15, 16, bh-19,  fg)

def _icon_settings(bx, by, bh, fg, bg):
    cx, cy, r = bx+bh//2, by+bh//2, 5
    lcd.fill_rect(cx-r,   cy-r,   r*2, r*2, fg)
    lcd.fill_rect(cx-3,   cy-r-4, 6,   4,   fg)
    lcd.fill_rect(cx-3,   cy+r,   6,   4,   fg)
    lcd.fill_rect(cx-r-4, cy-3,   4,   6,   fg)
    lcd.fill_rect(cx+r,   cy-3,   4,   6,   fg)

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_ITEMS = [
    ("GROUNDING",  show_grounding, None, None, _icon_ground),
    ("TIMETABLE",  show_timetable, None, None, _icon_time),
    ("COMM CARDS", show_comm_menu, None, None, _icon_comm),
    ("CONTACTS",   show_contacts,  None, None, _icon_contact),
    ("SETTINGS",   show_settings,  None, None, _icon_settings),
    ("ABOUT",      lambda: show_about(), None, None, _icon_sos),
]

dashboard_buttons = []

def show_about():
    global current_screen
    current_screen = SCREEN_CONTACTS
    set_breathing_active(False)
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("ABOUT")
    about_text = (
        "Accessible Device v1.0\n\n"
        "ILI9486 Display\n"
        "XPT2046 Touchscreen\n"
        "Pimoroni Pico LiPo\n\n"
        "Battery: {}%\n"
        "Charging: {}".format(
            draw.battery_percentage,
            "Yes" if draw.battery_is_charging else "No",
        )
    )
    draw_text_box(about_text, 16, 60, W - 32, H - 60 - (NAV_H + 30), prefer_scale=2)
    btn_about_menu = Button(NAV_X0 + 1*(NAV_W+NAV_GAP), NAV_Y, NAV_W, NAV_H, "HOME", show_dashboard)
    draw_button(btn_about_menu)

def draw_dashboard():
    t = th()
    lcd.fill(t["screen_bg"])
    draw_title_bar("DASHBOARD")   # resets _last_badge_state so badge is always redrawn

    grid_start_y = 60
    cols, rows   = 3, 2
    gap_x, gap_y = 14, 14
    btn_w = (W - 32 - (cols-1)*gap_x) // cols
    btn_h = (H - grid_start_y - 20 - (rows-1)*gap_y) // rows

    dashboard_buttons.clear()
    for i, (label, fn, bg, fg, icon_fn) in enumerate(DASHBOARD_ITEMS):
        col = i % cols
        row = i // cols
        x   = 16 + col * (btn_w + gap_x)
        y   = grid_start_y + row * (btn_h + gap_y)

        b = make_btn(x, y, btn_w, btn_h, label, fn, bg=bg, fg=fg)
        dashboard_buttons.append(b)

        bg_color = getattr(b, "bg", t["btn_bg"])
        fg_color = getattr(b, "fg", t["btn_fg"])
        lcd.fill_rect(b.x, b.y, btn_w, btn_h, bg_color)
        draw_border(b.x, b.y, btn_w, btn_h, t["box_border"])

        icon_h  = btn_h * 5 // 9
        icon_fn(b.x + (btn_w - icon_h) // 2, b.y + 8, icon_h, fg_color, bg_color)

        for scale in (2, 1):
            text_w = len(label) * 8 * scale
            if text_w <= btn_w - 8:
                break
        lcd.text(label,
                 b.x + (btn_w - text_w) // 2,
                 b.y + btn_h - 8 * scale - 10,
                 fg_color, bg_color, scale=scale)

def show_dashboard():
    global current_screen
    current_screen = SCREEN_DASHBOARD
    set_breathing_active(False)
    draw_dashboard()

# ---------------------------------------------------------------------------
# Wire return-to-home buttons
# ---------------------------------------------------------------------------
btn_ground_menu.on_press   = show_dashboard
btn_tt_menu.on_press       = show_dashboard
btn_contacts_menu.on_press = show_dashboard
btn_settings_menu.on_press = show_dashboard
btn_commmenu_menu.on_press = show_dashboard
btn_comm_menu.on_press     = show_dashboard
btn_settings_cal.on_press  = _do_calibrate

# ---------------------------------------------------------------------------
# Breather colour sync
# ---------------------------------------------------------------------------
def sync_breather_with_lanyard():
    global _last_quiet_for_color
    if breather is None or current_screen != SCREEN_GROUND or hw.mic is None:
        return
    if _last_quiet_for_color is None or draw.mic_quiet != _last_quiet_for_color:
        _last_quiet_for_color = draw.mic_quiet
        breather.set_color(neo_quiet_color if draw.mic_quiet else neo_active_color)

# ---------------------------------------------------------------------------
# Active button list for touch handler
# ---------------------------------------------------------------------------
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
        return settings_buttons + [btn_settings_menu, btn_settings_cal]
    if current_screen == SCREEN_COMM_MENU:
        return comm_menu_buttons + [btn_commmenu_menu]
    if current_screen == SCREEN_COMM_CARD:
        return [btn_comm_speak, btn_comm_menu, btn_comm_prev, btn_comm_cats, btn_comm_next]
    return []
