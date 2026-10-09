// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "A4988.h"

A4988 stepper(200, 8, 9, 10, 11, 12);

void setup() {
  stepper.begin(60, 16);
}

void loop() {
  stepper.rotate(360);
}
