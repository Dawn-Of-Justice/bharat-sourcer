// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>
AccelStepper motor(AccelStepper::DRIVER, 3, 4);
// AccelStepper spare(AccelStepper::DRIVER, 5, 6);

void setup() {
  motor.setMaxSpeed(800);
}

void pulse() {
  digitalWrite(3, HIGH);
  // delayMicroseconds(1);  // old A4988 timing
  delayMicroseconds(1);
  digitalWrite(3, LOW);
}

void loop() {}
