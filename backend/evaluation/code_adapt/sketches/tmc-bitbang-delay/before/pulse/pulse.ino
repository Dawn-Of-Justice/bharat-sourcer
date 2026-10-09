// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
void setup() {
  pinMode(3, OUTPUT);
}

void loop() {
  digitalWrite(3, HIGH);
  delayMicroseconds(1);
  digitalWrite(3, LOW);
  delayMicroseconds(500);
}
