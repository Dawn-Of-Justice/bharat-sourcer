// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
#include <AccelStepper.h>
#include "motion.h"

AccelStepper feeder(AccelStepper::DRIVER, 6, 7);

void motionInit() {
  feeder.setMaxSpeed(500);
  feeder.setMinPulseWidth(2);  // DRV8825: STEP pulses of at least 1.9 µs
}
