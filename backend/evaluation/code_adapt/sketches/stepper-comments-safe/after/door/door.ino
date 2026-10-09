// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
// Driver: A4988 on STEP=3, DIR=4 (see wiring.md)
#include <AccelStepper.h>
/* AccelStepper old(AccelStepper::DRIVER, 8, 9); */
AccelStepper motor(AccelStepper::DRIVER, 3, 4);  // was an A4988 board

void setup() {
  motor.setMaxSpeed(800);
  motor.setMinPulseWidth(2);  // DRV8825: STEP pulses of at least 1.9 µs
}

void loop() { motor.run(); }
