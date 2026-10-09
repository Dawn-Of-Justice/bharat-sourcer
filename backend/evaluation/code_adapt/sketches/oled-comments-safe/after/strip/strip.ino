// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// Wiring: SSD1306 module on the I2C pins; Adafruit_SSD1306 library v2.
#include <Adafruit_SH110X.h>
// #include <Adafruit_SSD1306.h>
Adafruit_SH1106G oled(128, 32, &Wire, -1);  // 0.91" SSD1306 strip

void setup() {
  oled.begin(0x3C, true);  // SSD1306_SWITCHCAPVCC = internal charge pump
  // oled.startscrollright(0, 7);
  /* oled.dim(true); */
  /*
  oled.ssd1306_command(0xAE);
  */
  oled.display();
}

void loop() {}
