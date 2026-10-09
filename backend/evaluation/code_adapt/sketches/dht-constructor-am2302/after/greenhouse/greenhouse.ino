// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "DHT.h"

DHT outside(5, DHT11);
DHT inside(6, DHT11);
const char *SENSOR_NAME = "DHT22";

void setup() {
  outside.begin();
  inside.begin();
}

void loop() {}
