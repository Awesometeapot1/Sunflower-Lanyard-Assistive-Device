# xpt2046.py
from machine import Pin
import time

class XPT2046:
    """
    Minimal XPT2046 resistive touch driver (SPI).
    Reads raw X/Y and returns (x, y, p) where p is a simple noise/pressure proxy.
    """

    CMD_X = 0xD0  # Read X (12-bit)
    CMD_Y = 0x90  # Read Y (12-bit)

    def __init__(self, spi, cs_pin, irq_pin=None):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.irq = Pin(irq_pin, Pin.IN, Pin.PULL_UP) if irq_pin is not None else None

        # Scratch buffers to avoid allocations in loop
        self._tx = bytearray(3)
        self._rx = bytearray(3)

    def touched(self):
        # IRQ goes low when touched (on most boards)
        if self.irq is None:
            return True  # if no IRQ, caller will poll get_raw()/read()
        return self.irq.value() == 0

    def _read12(self, cmd):
        # Send command then read 12-bit result (stored across rx[1], rx[2])
        self._tx[0] = cmd
        self._tx[1] = 0
        self._tx[2] = 0

        self.cs.value(0)
        self.spi.write_readinto(self._tx, self._rx)
        self.cs.value(1)

        # rx[1]: high bits, rx[2]: low bits; right shift 4 for 12-bit value
        return ((self._rx[1] << 8) | self._rx[2]) >> 4

    def get_raw(self, samples=5, delay_us=200):
        """
        Returns (x, y, p) raw values, or None if not pressed (when IRQ available).
        p is a simple stability heuristic: bigger spread => noisier contact.
        """
        if self.irq is not None and not self.touched():
            return None

        xs = []
        ys = []

        for _ in range(samples):
            # Many boards benefit from reading Y then X; keep consistent.
            y = self._read12(self.CMD_Y)
            x = self._read12(self.CMD_X)
            xs.append(x)
            ys.append(y)
            time.sleep_us(delay_us)

        xs.sort()
        ys.sort()

        # Median (robust against spikes)
        mid = len(xs) // 2
        x = xs[mid]
        y = ys[mid]

        # Stability/pressure proxy (not true pressure)
        p = (xs[-1] - xs[0]) + (ys[-1] - ys[0])
        return (x, y, p)

    # ---- Compatibility alias ----
    def read(self, samples=5, delay_us=200):
        """
        Alias for get_raw() so code can call tp.read().
        """
        return self.get_raw(samples=samples, delay_us=delay_us)
