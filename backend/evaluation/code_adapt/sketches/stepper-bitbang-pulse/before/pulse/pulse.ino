// Synthetic sketch written for the Bharat Sourcer code-adapt eval; not from a real project.
const int STEP_PIN = 3;
const int DIR_PIN = 4;

void setup() {
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
}

void step(int n) {
  for (int i = 0; i < n; i++) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(1);
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds( 1 );
  }
  delayMicroseconds(10);
}

void loop() { step(200); }
