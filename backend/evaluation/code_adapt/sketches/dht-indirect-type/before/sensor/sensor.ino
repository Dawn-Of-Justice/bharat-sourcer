// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "DHT.h"
#define SENSOR_MODEL DHT22
const uint8_t kType = SENSOR_MODEL;
DHT dht(2, kType);

void setup() { dht.begin(); }
void loop() {}
