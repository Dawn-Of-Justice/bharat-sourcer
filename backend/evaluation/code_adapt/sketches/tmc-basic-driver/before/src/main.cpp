// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "BasicStepperDriver.h"

BasicStepperDriver stepper(200, 8, 9);

void setup() {
  stepper.begin(120, 1);
}

void loop() {
  stepper.move(200);
}
