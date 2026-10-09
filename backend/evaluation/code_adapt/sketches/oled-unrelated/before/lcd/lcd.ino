// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// A 16x2 character LCD, no OLED (an SSD1306 was considered in an earlier draft).
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

void setup() {
  lcd.init();
  lcd.backlight();
  lcd.print("WHITE BLACK");
}

void loop() {}
