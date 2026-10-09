// Synthetic test sketch: A4988 stepper (not a real project)
#include <AccelStepper.h>

AccelStepper stepper(AccelStepper::DRIVER, 3, 4);

void setup() {
  stepper.setMaxSpeed(1000);
  stepper.setAcceleration(500);
}

void loop() {
  stepper.runSpeed();
}
