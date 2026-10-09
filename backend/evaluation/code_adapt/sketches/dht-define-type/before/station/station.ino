// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <DHT.h>

#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void loop() {
  float h = dht.readHumidity();
  Serial.println(h, 1);
  delay(2000);
}
