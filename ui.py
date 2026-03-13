from touch_cal import CAL

class Button:
    def __init__(self, x, y, w, h, label, on_press):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.label = label
        self.on_press = on_press

    def contains(self, px, py):
        return (self.x <= px < self.x + self.w) and (self.y <= py < self.y + self.h)
