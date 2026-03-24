# neo.py
# NeoPixel breathing animation with hard-throttled writes.

import time
import math
from machine import Pin


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
