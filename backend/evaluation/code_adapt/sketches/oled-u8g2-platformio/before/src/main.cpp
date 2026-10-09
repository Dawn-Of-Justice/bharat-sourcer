// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <U8g2lib.h>
#include "sensors.h"

U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
U8X8_SSD1306_128X64_NONAME_HW_I2C u8x8(U8X8_PIN_NONE);

void setup() {
  u8g2.begin();
  u8x8.begin();
}

void loop() {}
