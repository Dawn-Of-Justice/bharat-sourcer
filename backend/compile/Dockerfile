# Compile runner image for one core family (code-adapt tier 3):
#   docker build --build-arg FAMILY=esp32 -t bharat-sourcer-compile-esp32 backend/compile
# Cores and libraries are pinned in pins.json and installed at build time; the job that
# runs this image has no internet route and only compiles (never uploads or runs code).
FROM python:3.12-slim-bookworm

ARG FAMILY
ARG ARDUINO_CLI_VERSION=1.5.1
ARG ARDUINO_CLI_SHA256=28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b

RUN test -n "$FAMILY" \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /tmp/cli.tgz \
       "https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_64bit.tar.gz" \
    && echo "${ARDUINO_CLI_SHA256}  /tmp/cli.tgz" | sha256sum -c - \
    && tar -xzf /tmp/cli.tgz -C /usr/local/bin arduino-cli \
    && rm /tmp/cli.tgz \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY pins.json arduino-cli.yaml install.py /opt/compile/
RUN python /opt/compile/install.py "$FAMILY" \
    && rm -rf /tmp/arduino-staging /root/.cache \
    && useradd --create-home --uid 10001 runner \
    && chmod -R a-w /opt/arduino /opt/compile

COPY --chmod=0444 runner.py /opt/compile/runner.py

USER runner
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/opt/compile/runner.py"]
