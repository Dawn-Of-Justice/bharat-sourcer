"""Image build step: install one family's pinned core and every pinned library.

Usage: python install.py <family>. Runs only while building the image (with internet);
the runtime job has no internet route, so nothing is installed at compile time.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "arduino-cli.yaml"
PACKAGES = Path("/opt/arduino/data/packages")
SMOKE = """#include <Wire.h>
#include <SPI.h>
void setup() { Serial.begin(115200); Wire.begin(); Serial.println(String(3.5f)); }
void loop() { delay(1000); }
"""


def cli(*args: str) -> str:
    result = subprocess.run(
        ["arduino-cli", "--config-file", str(CONFIG), *args], capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(f"arduino-cli {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main(family: str) -> None:
    pins = json.loads((HERE / "pins.json").read_text("utf-8"))
    spec = pins["families"][family]
    if spec["index"]:
        # Persist the third-party index so the installed platform resolves at compile time.
        with CONFIG.open("a", encoding="utf-8") as handle:
            handle.write(f"board_manager:\n  additional_urls:\n    - {spec['index']}\n")
    cli("core", "update-index")
    cli("core", "install", f"{spec['core']}@{spec['version']}")
    cli("lib", "update-index")
    cli("lib", "install", "--no-deps", *pins["libraries"])
    installed = {p["id"]: p for p in json.loads(cli("core", "list", "--json"))["platforms"]}
    version = installed[spec["core"]].get("installed_version") or installed[spec["core"]].get(
        "installed"
    )
    if version != spec["version"]:
        raise SystemExit(f"{spec['core']} installed {version}, pinned {spec['version']}")
    for pattern in spec["prune"]:
        for path in PACKAGES.glob(pattern):
            shutil.rmtree(path)
    smoke(spec["boards"])
    (HERE / "core.txt").write_text(f"{spec['core']}@{version}\n", encoding="utf-8")
    (HERE / "family.txt").write_text(f"{family}\n", encoding="utf-8")
    print(f"Installed {spec['core']}@{version} and {len(pins['libraries'])} libraries")


def smoke(boards: list[str]) -> None:
    """Compile a small sketch per board so a broken core or prune fails the build."""
    with tempfile.TemporaryDirectory() as work:
        sketch = Path(work) / "smoke"
        sketch.mkdir()
        (sketch / "smoke.ino").write_text(SMOKE, encoding="utf-8")
        for fqbn in boards:
            cli("compile", "--fqbn", fqbn, "--build-path", f"{work}/build-{fqbn}", str(sketch))
            print(f"Smoke compile passed: {fqbn}")


if __name__ == "__main__":
    main(sys.argv[1])
