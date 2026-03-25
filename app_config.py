# app_config.py
# Loads config.json and exposes all configurable settings.
# Falls back to built-in defaults if the file is missing or corrupt.

import json

# -----------------------------------------------------------
# Colour map: name string -> RGB565 value
# -----------------------------------------------------------
COLOR_MAP = {
    "RED":   0x001F, "WHITE": 0xFFFF, "BLACK": 0x0000,
    "GREY":  0x7BEF, "DARK":  0x39E7, "YELL":  0x07FF,
    "GREEN": 0x07E0, "BLUE":  0xF800, "CYAN":  0xFFE0,
    "MAG":   0xF81F, "ORNG":  0x053F,
}

def _col(name):
    return COLOR_MAP.get(str(name).upper(), 0xFFFF)

def _card(c):
    return (c["icon"], c["phrase"], _col(c["bg"]), _col(c["fg"]))

def _build_contact_text(c):
    notes = "\n".join("- " + n for n in c.get("medical_notes", []))
    return (
        "CONTACT DETAILS\n\n"
        "Name: " + c.get("name", "") + "\n"
        "Pronouns: " + c.get("pronouns", "") + "\n"
        "Phone: " + c.get("phone", "") + "\n\n"
        "Emergency Contact\n"
        "Name: " + c.get("emergency_name", "") + "\n"
        "Relationship: " + c.get("emergency_relationship", "") + "\n"
        "Phone: " + c.get("emergency_phone", "") + "\n\n"
        "Medical Notes\n"
        + notes + "\n"
    )

# -----------------------------------------------------------
# Built-in defaults (mirrors original hardcoded values)
# -----------------------------------------------------------
_DEFAULTS = {
    "mic_quiet_thresh": 0.015,
    "mic_hysteresis": 0.003,
    "mic_quiet_hold_ms": 1500,
    "contact": {
        "name": "Izzy", "pronouns": "She/Her", "phone": "",
        "emergency_name": "", "emergency_relationship": "Mother",
        "emergency_phone": "",
        "medical_notes": [
            "Please be patient.",
            "Prefer text / yes-no questions.",
            "Sensory overload: noise/crowds.",
            "Needs space + quiet to regulate."
        ]
    },
    "timetable": {
        "MON": [{"time": "09:00-13:00", "title": "group project", "room": "2Q13A", "note": ""}],
        "TUE": [{"time": "10:00-11:00", "title": "internet of things lecture", "room": "2B025", "note": ""}],
        "WED": [{"time": "09:00-11:00", "title": "internet of things practical", "room": "2Q13A", "note": ""}],
        "THU": [
            {"time": "13:30-15:00", "title": "advanced algorithms practical", "room": "3Q085", "note": ""},
            {"time": "15:00-16:30", "title": "advanced algorithms lecture", "room": "2D067", "note": ""}
        ],
        "FRI": [{"time": "10:00-13:00", "title": "digital design", "room": "0T135", "note": ""}]
    },
    "comm_cards": {
        "FAVOURITES": [
            {"icon": "!", "phrase": "I NEED HELP",      "bg": "RED",  "fg": "WHITE"},
            {"icon": "!", "phrase": "PLEASE WAIT",       "bg": "ORNG", "fg": "BLACK"},
            {"icon": "!", "phrase": "I NEED SPACE",      "bg": "ORNG", "fg": "BLACK"},
            {"icon": "!", "phrase": "TOO LOUD",          "bg": "MAG",  "fg": "WHITE"},
            {"icon": "!", "phrase": "TOO MANY PEOPLE",   "bg": "MAG",  "fg": "WHITE"},
            {"icon": "!", "phrase": "I NEED TO GO HOME", "bg": "ORNG", "fg": "BLACK"},
            {"icon": "~", "phrase": "WATER PLEASE",      "bg": "CYAN", "fg": "BLACK"},
            {"icon": "~", "phrase": "I NEED HEADPHONES", "bg": "CYAN", "fg": "BLACK"}
        ],
        "NEEDS": [
            {"icon": "!", "phrase": "I NEED HELP",            "bg": "RED",  "fg": "WHITE"},
            {"icon": "~", "phrase": "PLEASE WAIT",            "bg": "ORNG", "fg": "BLACK"},
            {"icon": "~", "phrase": "I NEED SPACE",           "bg": "ORNG", "fg": "BLACK"},
            {"icon": "~", "phrase": "I NEED A BREAK",         "bg": "YELL", "fg": "BLACK"},
            {"icon": "~", "phrase": "WATER PLEASE",           "bg": "CYAN", "fg": "BLACK"},
            {"icon": "~", "phrase": "HUNGRY",                 "bg": "GREEN","fg": "BLACK"},
            {"icon": "~", "phrase": "TIRED",                  "bg": "GREY", "fg": "BLACK"},
            {"icon": "!", "phrase": "I NEED TO GO HOME",      "bg": "ORNG", "fg": "BLACK"},
            {"icon": "~", "phrase": "I NEED HEADPHONES",      "bg": "CYAN", "fg": "BLACK"},
            {"icon": "~", "phrase": "I'M HAVING A HARD DAY",  "bg": "ORNG", "fg": "BLACK"}
        ],
        "SENSORY": [
            {"icon": "!", "phrase": "TOO LOUD",                "bg": "MAG",  "fg": "WHITE"},
            {"icon": "!", "phrase": "TOO MANY PEOPLE",         "bg": "MAG",  "fg": "WHITE"},
            {"icon": "!", "phrase": "TOO BRIGHT",              "bg": "MAG",  "fg": "WHITE"},
            {"icon": "~", "phrase": "I NEED QUIET",            "bg": "BLUE", "fg": "WHITE"},
            {"icon": "~", "phrase": "I NEED DIM LIGHTS",       "bg": "BLUE", "fg": "WHITE"},
            {"icon": "!", "phrase": "PLEASE DON'T TOUCH ME",   "bg": "RED",  "fg": "WHITE"},
            {"icon": "~", "phrase": "I NEED LOWER BRIGHTNESS", "bg": "BLUE", "fg": "WHITE"}
        ],
        "RESPONSES": [
            {"icon": "?", "phrase": "YES",                     "bg": "GREEN","fg": "BLACK"},
            {"icon": "?", "phrase": "NO",                      "bg": "RED",  "fg": "WHITE"},
            {"icon": "~", "phrase": "MAYBE",                   "bg": "YELL", "fg": "BLACK"},
            {"icon": "~", "phrase": "I DON'T KNOW",            "bg": "GREY", "fg": "BLACK"},
            {"icon": "~", "phrase": "PLEASE TEXT ME",          "bg": "CYAN", "fg": "BLACK"},
            {"icon": "~", "phrase": "I CAN'T SPEAK RIGHT NOW", "bg": "CYAN", "fg": "BLACK"}
        ],
        "FEELINGS": [
            {"icon": "*", "phrase": "I FEEL OVERWHELMED", "bg": "ORNG", "fg": "BLACK"},
            {"icon": "*", "phrase": "I FEEL SICK",        "bg": "RED",  "fg": "WHITE"},
            {"icon": "*", "phrase": "I FEEL ANXIOUS",     "bg": "ORNG", "fg": "BLACK"},
            {"icon": "*", "phrase": "I AM OKAY",          "bg": "GREEN","fg": "BLACK"}
        ],
        "STATUS": [
            {"icon": "G", "phrase": "I AM OKAY",       "bg": "GREEN","fg": "BLACK"},
            {"icon": "A", "phrase": "I AM STRUGGLING", "bg": "YELL", "fg": "BLACK"},
            {"icon": "R", "phrase": "I AM IN CRISIS",  "bg": "RED",  "fg": "WHITE"}
        ]
    },
    "battery_poll_ms": 3000,
    "theme_index": 0,
}

# -----------------------------------------------------------
# Load config.json (fall back to defaults on any error)
# -----------------------------------------------------------
try:
    with open("config.json") as _f:
        _cfg = json.load(_f)
    print("app_config: loaded config.json")
except Exception as _e:
    print("app_config: using defaults -", _e)
    _cfg = _DEFAULTS

# -----------------------------------------------------------
# Exposed settings
# -----------------------------------------------------------
MIC_QUIET_THRESH  = float(_cfg.get("mic_quiet_thresh",  _DEFAULTS["mic_quiet_thresh"]))
MIC_HYSTERESIS    = float(_cfg.get("mic_hysteresis",    _DEFAULTS["mic_hysteresis"]))
MIC_QUIET_HOLD_MS = int(_cfg.get("mic_quiet_hold_ms",   _DEFAULTS["mic_quiet_hold_ms"]))

TIMETABLE = _cfg.get("timetable", _DEFAULTS["timetable"])

_cc = _cfg.get("comm_cards", _DEFAULTS["comm_cards"])
FAV_CARDS     = [_card(c) for c in _cc.get("FAVOURITES", [])]
CAT_NEEDS     = [_card(c) for c in _cc.get("NEEDS",      [])]
CAT_SENSORY   = [_card(c) for c in _cc.get("SENSORY",    [])]
CAT_RESPONSES = [_card(c) for c in _cc.get("RESPONSES",  [])]
CAT_FEELINGS  = [_card(c) for c in _cc.get("FEELINGS",   [])]
CAT_STATUS    = [_card(c) for c in _cc.get("STATUS",     [])]

CONTACT_TEXT  = _build_contact_text(_cfg.get("contact", _DEFAULTS["contact"]))

_nq = _cfg.get("neo_quiet_color",  [0, 120, 255])
_na = _cfg.get("neo_active_color", [160, 0, 255])
NEO_QUIET_COLOR  = (int(_nq[0]), int(_nq[1]), int(_nq[2]))
NEO_ACTIVE_COLOR = (int(_na[0]), int(_na[1]), int(_na[2]))

BATTERY_POLL_MS  = int(_cfg.get("battery_poll_ms", _DEFAULTS["battery_poll_ms"]))
THEME_INDEX      = int(_cfg.get("theme_index",     _DEFAULTS["theme_index"]))
