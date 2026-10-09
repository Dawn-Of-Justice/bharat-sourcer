// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 display(128, 64);

void setup() {
  display.begin(SSD1306_SWITCHCAPVCC, 0x3D);
  if (SSD1306_LCDHEIGHT != 64) {
    while (true) {}
  }
  display.drawLine(0, 0, 127, 63, INVERSE);
}

void loop() {}
