// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <DHT.h>
#define DHTTYPE DHT11
DHT dht(4, DHTTYPE);

void setup() { dht.begin(); }
void loop() { int t = (int)dht.readTemperature(); }
