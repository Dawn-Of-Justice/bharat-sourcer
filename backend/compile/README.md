# Compile runner

Image and script for compile-only checks of code patches (code-adapt tier 3). The API
starts one Cloud Run job execution per check; `runner.py` fetches the sketch from the API,
compiles it with `arduino-cli` and posts the result back. See
[the contract](../../docs/contracts/code-adapt.md#compile-check-v0290) and
[the runbook](../infra/README.md#compile-runner-code-adapt-tier-3).

- `pins.json`: arduino-cli, one core per family and every library, at exact versions.
- `install.py`: image build step; installs one family's core and all libraries.
- `runner.py`: the job entry point (standard library only).
- `Dockerfile`: `docker build --build-arg FAMILY=<avr|esp32|esp8266|rp2040> backend/compile`.

Local check with networking disabled (the job also has no internet route):

```bash
docker build --build-arg FAMILY=avr -t compile-avr backend/compile
docker run --rm --network none --entrypoint python compile-avr -c \
  "import sys; sys.path.insert(0, '/opt/compile'); import runner; print(runner.compile_sketch({'sketch': 'main', 'fqbn': 'arduino:avr:uno', 'files': {'main.ino': 'void setup(){}\nvoid loop(){}\n'}}))"
```
