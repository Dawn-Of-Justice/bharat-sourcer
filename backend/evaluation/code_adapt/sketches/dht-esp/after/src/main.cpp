// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "DHTesp.h"

DHTesp dht;

void setup() {
  dht.setup(14, DHTesp::DHT11);
}

void loop() {
  TempAndHumidity v = dht.getTempAndHumidity();
}
