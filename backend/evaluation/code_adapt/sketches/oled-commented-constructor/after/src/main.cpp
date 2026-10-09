// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Adafruit_SH110X.h>
Adafruit_SH1106G display(128, 64, &Wire, -1);
// Adafruit_SSD1306 display(128, 32, &Wire, -1);  // the 0.91" variant

void setup() {
  display.begin(0x3C, true);
  // display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setTextColor(SH110X_WHITE);
}

void loop() {}
