// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>

AccelStepper motor(AccelStepper::DRIVER, 3, 4);

void setup() {
  motor.setMaxSpeed(800);
}

void loop() {
  motor.runSpeed();
}
