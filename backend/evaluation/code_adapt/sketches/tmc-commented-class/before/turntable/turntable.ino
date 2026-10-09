// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "BasicStepperDriver.h"
// A4988 stepper(200, 8, 9, 10, 11, 12);
/* A4988 old(200, 2, 3); */
BasicStepperDriver stepper(200, 8, 9);

void setup() {
  stepper.begin(60, 1);
}

void loop() {
  stepper.rotate(90);
}
