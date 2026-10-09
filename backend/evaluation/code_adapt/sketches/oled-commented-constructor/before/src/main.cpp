// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Adafruit_SSD1306.h>
Adafruit_SSD1306 display(128, 64, &Wire, -1);
// Adafruit_SSD1306 display(128, 32, &Wire, -1);  // the 0.91" variant

void setup() {
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  // display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setTextColor(SSD1306_WHITE);
}

void loop() {}
