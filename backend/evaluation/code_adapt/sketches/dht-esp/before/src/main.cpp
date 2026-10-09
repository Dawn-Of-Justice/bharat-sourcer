// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "DHTesp.h"

DHTesp dht;

void setup() {
  dht.setup(14, DHTesp::AM2302);
}

void loop() {
  TempAndHumidity v = dht.getTempAndHumidity();
}
