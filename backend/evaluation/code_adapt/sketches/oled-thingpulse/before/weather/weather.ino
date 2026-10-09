// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Wire.h>
#include "SSD1306Wire.h"

SSD1306Wire display(0x3c, SDA, SCL);

void setup() {
  display.init();
  display.flipScreenVertically();
}

void loop() {
  display.clear();
  display.drawString(0, 0, "ok");
  display.display();
}
