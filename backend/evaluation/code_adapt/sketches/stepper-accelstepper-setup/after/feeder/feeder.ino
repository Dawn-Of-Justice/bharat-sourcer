// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>

AccelStepper motor(AccelStepper::DRIVER, 3, 4);

void setup() {
  motor.setMaxSpeed(800);
  motor.setMinPulseWidth(2);  // DRV8825: STEP pulses of at least 1.9 µs
  motor.setAcceleration(400);
}

void loop() {
  motor.runSpeed();
}
