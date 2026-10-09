// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// Wiring: SSD1306 module on the I2C pins; Adafruit_SSD1306 library v2.
#include <Adafruit_SSD1306.h>
// #include <Adafruit_SSD1306.h>
Adafruit_SSD1306 oled(128, 32, &Wire, -1);  // 0.91" SSD1306 strip

void setup() {
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);  // SSD1306_SWITCHCAPVCC = internal charge pump
  // oled.startscrollright(0, 7);
  /* oled.dim(true); */
  /*
  oled.ssd1306_command(0xAE);
  */
  oled.display();
}

void loop() {}
