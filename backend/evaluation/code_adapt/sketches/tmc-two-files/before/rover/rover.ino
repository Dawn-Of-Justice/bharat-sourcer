// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include "drivers.h"

A4988 left(200, 2, 3);
A4988 right(200, 4, 5);

void setup() {
  left.begin(30, 1);
  right.begin(30, 1);
}

void loop() {}
