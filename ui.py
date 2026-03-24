from touch_cal import CAL
from machine import ADC, Pin

class Button:
    def __init__(self, x, y, w, h, label, on_press):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.label = label
        self.on_press = on_press

    def contains(self, px, py):
        return (self.x <= px < self.x + self.w) and (self.y <= py < self.y + self.h)


class Battery:
    """
    Pimoroni Pico LiPo battery monitor.
    Reads voltage from ADC3 (GPIO29) with 3:1 divider.
    Converts to 0-100% based on 3.7V (min) to 4.2V (max) LiPo range.
    """
    def __init__(self):
        try:
            self.vsys_adc = ADC(Pin(29))
            self.charging_pin = Pin(24, Pin.IN)
            self.conversion_factor = 3 * 3.3 / 65535
            self.voltage = 0.0
            self.percentage = 0
            self.is_charging = False
        except Exception as e:
            print("Battery init failed:", e)
            self.vsys_adc = None

    def update(self):
        """Read battery voltage and calculate percentage."""
        if self.vsys_adc is None:
            return {"voltage": 0.0, "percentage": 0, "is_charging": False}
        
        try:
            raw_adc = self.vsys_adc.read_u16()
            self.voltage = raw_adc * self.conversion_factor
            
            # Convert 3.7-4.2V LiPo range to 0-100%
            # Using extended range (2.8-4.2V) for safety
            self.percentage = int(100 * ((self.voltage - 2.8) / (4.2 - 2.8)))
            self.percentage = max(0, min(100, self.percentage))
            
            self.is_charging = self.charging_pin.value() == 1
        except Exception as e:
            print("Battery update failed:", e)
        
        return {
            "voltage": self.voltage,
            "percentage": self.percentage,
            "is_charging": self.is_charging
        }

    def get_battery_color(self):
        """Return RGB565 color based on battery level."""
        if self.percentage > 50:
            return 0x07E0  # GREEN
        elif self.percentage > 20:
            return 0xFFE0  # YELLOW
        else:
            return 0xF800  # RED
