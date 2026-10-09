// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Servo.h>

Servo arm;

void setup() {
  arm.attach(9);
}

void loop() {
  arm.write(90);
  delay(15);
}
