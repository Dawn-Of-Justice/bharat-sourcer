// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>

AccelStepper xAxis(AccelStepper::DRIVER, 2, 5);
AccelStepper zAxis(AccelStepper::DRIVER, 4, 7);

void setup(void) {
  zAxis.setMinPulseWidth(3);
  xAxis.setMaxSpeed(1000);
}

void loop() {
  xAxis.run();
  zAxis.run();
}
