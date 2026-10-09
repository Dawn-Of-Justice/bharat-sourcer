// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 screen(128, 64, &Wire, -1);

void setup() {
  screen.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS);
  screen.clearDisplay();
  screen.setTextColor(SSD1306_WHITE, BLACK);
  screen.println("12:00");
  screen.display();
}

void loop() {}
