// Synthetic test sketch: SSD1306 status display (not a real project)
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 display(128, 64, &Wire, -1);

void setup() {
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    for (;;);
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.println("Using SSD1306_WHITE text");
  display.display();
}

void loop() {
  display.fillRect(0, 0, 10, 10, SSD1306_BLACK);
  display.display();
}
