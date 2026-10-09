// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Adafruit_SH110X.h>
#ifndef WHITE
#define WHITE SH110X_WHITE  // the sketch uses the old SSD1306 colour name
#endif

Adafruit_SH1106G display(128, 64, &Wire, -1);

void setup() {
  display.begin(0x3C, true);
  display.setTextColor(WHITE);
}

void loop() {}
