# mic_level.py
# Robust "sound level" + quiet detection for an analog mic module on a Pico ADC pin.
# Designed to behave nicely even when NeoPixels are running.

from machine import ADC
import time
import math

class MicLevel:
    def __init__(
        self,
        adc_pin=26,              # GP26 / ADC0
        sample_count=120,        # samples per update
        sample_us=80,            # delay between samples in microseconds
        ema_alpha=0.15,          # smoothing (0..1), higher = faster response
        quiet_threshold=0.5,   # tune this (typical 0.008 .. 0.030)
        hysteresis=0.003,        # prevents flicker around threshold
        quiet_hold_ms=1500,      # must be quiet this long to switch into quiet

        # NEW: keep UI responsive even if something is noisy
        max_read_ms=12,          # hard budget for sampling work per update
        yield_every=25           # let the interpreter breathe
    ):
        self.adc = ADC(adc_pin)

        self.sample_count = int(sample_count)
        self.sample_us = int(sample_us)

        self.ema_alpha = float(ema_alpha)
        self.quiet_threshold = float(quiet_threshold)
        self.hysteresis = float(hysteresis)
        self.quiet_hold_ms = int(quiet_hold_ms)

        self.max_read_ms = int(max_read_ms)
        self.yield_every = int(yield_every)

        self._ema_rms = 0.0
        self._quiet = False
        self._quiet_start = None

    def _read_rms_budgeted(self):
        """
        Reads ADC samples and returns RMS of AC component.
        Stops early if it hits max_read_ms to avoid freezing the UI.
        """
        start = time.ticks_ms()

        s = 0.0
        ss = 0.0
        n = 0

        for i in range(self.sample_count):
            v = self.adc.read_u16() / 65535.0
            s += v
            ss += v * v
            n += 1

            if self.sample_us > 0:
                time.sleep_us(self.sample_us)

            # yield
            if self.yield_every and (i % self.yield_every == 0):
                time.sleep_ms(0)

            # time budget
            if time.ticks_diff(time.ticks_ms(), start) >= self.max_read_ms:
                break

        if n < 8:
            n = 8  # avoid weirdness, but still behave

        mean = s / n
        var = (ss / n) - (mean * mean)
        if var < 0:
            var = 0
        return math.sqrt(var)

    def update(self):
        raw_rms = self._read_rms_budgeted()

        self._ema_rms = (self.ema_alpha * raw_rms) + ((1.0 - self.ema_alpha) * self._ema_rms)

        now = time.ticks_ms()
        enter_quiet_at = self.quiet_threshold
        exit_quiet_at  = self.quiet_threshold + self.hysteresis

        if not self._quiet:
            if self._ema_rms < enter_quiet_at:
                if self._quiet_start is None:
                    self._quiet_start = now
                elif time.ticks_diff(now, self._quiet_start) >= self.quiet_hold_ms:
                    self._quiet = True
            else:
                self._quiet_start = None
        else:
            if self._ema_rms > exit_quiet_at:
                self._quiet = False
                self._quiet_start = None

        return {"raw_rms": raw_rms, "rms": self._ema_rms, "quiet": self._quiet}

    @property
    def quiet(self):
        return self._quiet

    @property
    def rms(self):
        return self._ema_rms
