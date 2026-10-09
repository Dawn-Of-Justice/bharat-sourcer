// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>

AccelStepper xAxis(AccelStepper::DRIVER, 2, 5);
AccelStepper zAxis(AccelStepper::DRIVER, 4, 7);

void setup(void) {
  zAxis.setMinPulseWidth(3);
  xAxis.setMaxSpeed(1000);
  xAxis.setMinPulseWidth(2);  // DRV8825: STEP pulses of at least 1.9 µs
}

void loop() {
  xAxis.run();
  zAxis.run();
}
