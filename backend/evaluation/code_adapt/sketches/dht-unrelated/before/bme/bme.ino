// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// TODO: maybe add a DHT22 later for a second room.
#include <Adafruit_BME280.h>

Adafruit_BME280 bme;

void setup() { bme.begin(0x76); }
void loop() { float t = bme.readTemperature(); }
