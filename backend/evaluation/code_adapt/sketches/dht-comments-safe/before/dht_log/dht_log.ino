// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// Uncomment the line for your sensor:
//#define DHTTYPE DHT22
#define DHTTYPE DHT22   // DHT22 / AM2302
/*
  Older boards used: #define DHTTYPE AM2302
*/
#include "DHT.h"
DHT dht(7, DHTTYPE);
void setup() { dht.begin(); }
void loop() {}
