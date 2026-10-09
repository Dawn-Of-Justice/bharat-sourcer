// Synthetic test sketch: DHT22 weather logger (not a real project)
#include <DHT.h>

#define DHTPIN 2
#define DHTTYPE DHT22   // DHT22 sensor on pin 2

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  Serial.println("DHT22 logger starting");
  dht.begin();
}

void loop() {
  float t = dht.readTemperature();
  Serial.println(t);
  delay(2000);
}
