"""Image build step: install one family's pinned core and every pinned library.

Usage: python install.py <family>. Runs only while building the image (with internet);
the runtime job has no internet route, so nothing is installed at compile time.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "arduino-cli.yaml"


def cli(*args: str) -> str:
    result = subprocess.run(
        ["arduino-cli", "--config-file", str(CONFIG), *args],
        check=True,
        capture_output=True,
        text=True,
    )
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
    (HERE / "core.txt").write_text(f"{spec['core']}@{version}\n", encoding="utf-8")
    (HERE / "family.txt").write_text(f"{family}\n", encoding="utf-8")
    print(f"Installed {spec['core']}@{version} and {len(pins['libraries'])} libraries")


if __name__ == "__main__":
    main(sys.argv[1])
