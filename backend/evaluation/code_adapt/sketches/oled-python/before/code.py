# Synthetic CircuitPython script for the code-adapt eval; not from a real project.
import adafruit_ssd1306
import board

i2c = board.I2C()
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
# oled = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
oled.fill(0)
oled.show()
