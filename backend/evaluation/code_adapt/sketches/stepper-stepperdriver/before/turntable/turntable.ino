// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <Arduino.h>
#include "A4988.h"

#define MOTOR_STEPS 200
A4988 stepper(MOTOR_STEPS, 8, 9, 10, 11, 12);

void setup() {
  stepper.begin(60, 16);
}

void loop() {
  stepper.rotate(360);
}
