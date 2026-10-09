// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

#define SCREEN_ADDRESS 0x3C
Adafruit_SH1106G screen(128, 64, &Wire, -1);

void setup() {
  screen.begin(SCREEN_ADDRESS, true);
  screen.clearDisplay();
  screen.setTextColor(SH110X_WHITE, SH110X_BLACK);
  screen.println("12:00");
  screen.display();
}

void loop() {}
