# hw.py
# Hardware initialisation — imported by draw.py, screens.py, and main.py.
# All objects are created once here; other modules import them directly.

from machine import Pin, SPI
from st7796s import ST7796S as ILI9486
from xpt2046 import XPT2046
from touch_cal import CAL
from ui import Battery
from app_config import MIC_QUIET_THRESH, MIC_HYSTERESIS, MIC_QUIET_HOLD_MS

# --- RGB565 colour constants ---
BLACK = 0x0000
WHITE = 0xFFFF
GREY  = 0x7BEF
DARK  = 0x39E7
YELL  = 0x07FF   # pre-swapped for BGR panel
RED   = 0x001F   # pre-swapped for BGR panel
GREEN = 0x07E0
BLUE  = 0xF800   # pre-swapped for BGR panel
CYAN  = 0xFFE0   # pre-swapped for BGR panel
MAG   = 0xF81F
ORNG  = 0x053F   # pre-swapped for BGR panel

# --- Display dimensions ---
W = CAL.get("W", 480)
H = CAL.get("H", 320)

# --- SPI + LCD + touch ---
_SPI_ID = 0
_SCK, _MOSI, _MISO               = 18, 19, 16
_LCD_CS, _LCD_DC, _LCD_RST, _BL  = 17, 20, 21, 22
_TP_CS, _TP_IRQ                   = 15, 14

Pin(_BL, Pin.OUT).value(1)

spi = SPI(_SPI_ID, baudrate=2_000_000, polarity=0, phase=0,
          sck=Pin(_SCK), mosi=Pin(_MOSI), miso=Pin(_MISO))

lcd = ILI9486(spi, cs=_LCD_CS, dc=_LCD_DC, rst=_LCD_RST,
              width=W, height=H, madctl=0xE0, bgr=True,
              x_offset=0, y_offset=0)

tp = XPT2046(spi, cs_pin=_TP_CS, irq_pin=_TP_IRQ)

# --- Battery (Pimoroni Pico LiPo) ---
try:
    battery = Battery()
except Exception as _e:
    print("Battery init failed:", _e)
    battery = None

# --- Mic (analog quiet detector) ---
MIC_POLL_MS       = 400
MIC_DRAW_THROTTLE = 250

_MIC_SAMPLE_COUNT = 120
_MIC_SAMPLE_US    = 80
_MIC_EMA_ALPHA    = 0.15

# --- Grounding shortcut button (GP4, active low) ---
ground_btn = Pin(4, Pin.IN, Pin.PULL_UP)

try:
    from mic_level import MicLevel
    mic = MicLevel(
        adc_pin=26,
        sample_count=_MIC_SAMPLE_COUNT,
        sample_us=_MIC_SAMPLE_US,
        ema_alpha=_MIC_EMA_ALPHA,
        quiet_threshold=MIC_QUIET_THRESH,
        hysteresis=MIC_HYSTERESIS,
        quiet_hold_ms=MIC_QUIET_HOLD_MS,
        max_read_ms=12,
        yield_every=25,
    )
    print("Mic initialised, threshold:", MIC_QUIET_THRESH)
except Exception as _e:
    print("Mic init failed:", _e)
    mic = None
