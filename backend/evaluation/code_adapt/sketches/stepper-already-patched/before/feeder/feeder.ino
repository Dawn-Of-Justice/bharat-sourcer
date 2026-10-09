// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>

AccelStepper motor(AccelStepper::DRIVER, 3, 4);

void setup() {
  motor.setMinPulseWidth(2);
  motor.setMaxSpeed(800);
}

void loop() {
  digitalWrite(5, HIGH);
  delayMicroseconds(2);
  digitalWrite(5, LOW);
  motor.runSpeed();
}
