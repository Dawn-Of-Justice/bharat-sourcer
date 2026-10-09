// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "DHT.h"
//#define DHTTYPE DHT11
#define DHTTYPE DHT22  // AM2302 module
// DHT test(3, DHT22);
DHT dht(2, DHTTYPE);

void setup() { dht.begin(); }
void loop() {}
