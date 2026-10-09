// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "effects.h"

extern Adafruit_SSD1306 display;

void scrollBanner() {
  display.startscrollleft(0x00, 0x07);
}

void stopBanner() {
  display.stopscroll();
}

void nightMode(bool on) {
  display.dim(on);
}
