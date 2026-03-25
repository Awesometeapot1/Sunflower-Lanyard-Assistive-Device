from machine import Pin, SPI
import time
import framebuf

# ST7796S SPI driver (RGB565)
# Correct colour order (RGB, not BGR)
# Drop‑in replacement for ILI9486 class

class ST7796S:
    def __init__(self, spi: SPI, cs: int, dc: int, rst: int,
                 width=320, height=480,
                 madctl=0x48, bgr=False,
                 x_offset=0, y_offset=0):

        self.spi = spi
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)

        self.width = width
        self.height = height

        self.x_offset = x_offset
        self.y_offset = y_offset

        # Force RGB colour order (BGR bit = bit 3)
        if bgr:
            madctl |= 0x08
        else:
            madctl &= ~0x08

        self.madctl = madctl & 0xFF

        self.reset()
        self.init_display()

    def reset(self):
        self.rst.value(1); time.sleep_ms(50)
        self.rst.value(0); time.sleep_ms(50)
        self.rst.value(1); time.sleep_ms(150)

    def write_cmd(self, cmd):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)

    def write_data(self, data):
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(data)
        self.cs.value(1)

    def _set_window(self, x0, y0, x1, y1):
        x0 += self.x_offset; x1 += self.x_offset
        y0 += self.y_offset; y1 += self.y_offset

        self.write_cmd(0x2A)
        self.write_data(bytearray([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))

        self.write_cmd(0x2B)
        self.write_data(bytearray([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))

        self.write_cmd(0x2C)

    def init_display(self):
        self.write_cmd(0x01)  # Software reset
        time.sleep_ms(150)

        self.write_cmd(0x11)  # Sleep out
        time.sleep_ms(120)

        # Pixel format: 16‑bit RGB565
        self.write_cmd(0x3A)
        self.write_data(b"\x55")

        # Memory access control (rotation + RGB order)
        self.write_cmd(0x36)
        self.write_data(bytearray([self.madctl]))

        # Inversion off (panel dependent)
        self.write_cmd(0x20)

        # Normal display mode
        self.write_cmd(0x13)

        # Display ON
        self.write_cmd(0x29)
        time.sleep_ms(50)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return

        if x < 0:
            w += x; x = 0
        if y < 0:
            h += y; y = 0
        if x + w > self.width:
            w = self.width - x
        if y + h > self.height:
            h = self.height - y
        if w <= 0 or h <= 0:
            return

        self._set_window(x, y, x + w - 1, y + h - 1)

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF

        chunk_pixels = 1024
        buf = bytearray(chunk_pixels * 2)
        for i in range(0, len(buf), 2):
            buf[i] = hi
            buf[i + 1] = lo

        total = w * h
        full = total // chunk_pixels
        rem = total % chunk_pixels

        self.cs.value(0)
        self.dc.value(1)
        for _ in range(full):
            self.spi.write(buf)
        if rem:
            self.spi.write(buf[:rem * 2])
        self.cs.value(1)

    def draw_pixel(self, x, y, color):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        self._set_window(x, y, x, y)
        self.write_data(bytearray([(color >> 8) & 0xFF, color & 0xFF]))

    def blit_buffer(self, buf, x, y, w, h, source_little_endian=True):
        if w <= 0 or h <= 0:
            return
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            return

        self._set_window(x, y, x + w - 1, y + h - 1)

        self.cs.value(0)
        self.dc.value(1)

        if not source_little_endian:
            self.spi.write(buf)
            self.cs.value(1)
            return

        mv = memoryview(buf)
        chunk = 2048
        tmp = bytearray(chunk)

        for i in range(0, len(mv), chunk):
            part = mv[i:i + chunk]
            n = len(part)
            if n != chunk:
                tmp = bytearray(n)

            for j in range(0, n, 2):
                tmp[j] = part[j + 1]
                tmp[j + 1] = part[j]

            self.spi.write(tmp)

        self.cs.value(1)

    def text(self, s, x, y, color=0xFFFF, bg=None, scale=2):
        if not s:
            return

        bw = 8 * len(s)
        bh = 8
        buf = bytearray(bw * bh * 2)
        fb = framebuf.FrameBuffer(buf, bw, bh, framebuf.RGB565)

        fb.fill(bg if bg is not None else 0)
        fb.text(s, 0, 0, color)

        if scale <= 1:
            self.blit_buffer(buf, x, y, bw, bh)
            return

        w = bw * scale
        h = bh * scale
        out = bytearray(w * h * 2)
        outfb = framebuf.FrameBuffer(out, w, h, framebuf.RGB565)
        outfb.fill(bg if bg is not None else 0)

        for yy in range(bh):
            for xx in range(bw):
                idx = (yy * bw + xx) * 2
                lo = buf[idx]
                hi = buf[idx + 1]
                pix = (hi << 8) | lo
                if bg is None and pix == 0:
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        outfb.pixel(xx * scale + sx, yy * scale + sy, pix)

        self.blit_buffer(out, x, y, w, h)
