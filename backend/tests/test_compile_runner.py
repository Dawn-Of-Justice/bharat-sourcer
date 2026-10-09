"""The compile runner script (backend/compile/runner.py) with a fake arduino-cli."""

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).resolve().parents[1] / "compile" / "runner.py"
spec = importlib.util.spec_from_file_location("compile_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def bundle(**changes):
    value = {
        "sketch": "blink",
        "fqbn": "arduino:avr:uno",
        "files": {"blink.ino": "void setup() {}\nvoid loop() {}\n", "src/led.h": "#pragma once\n"},
    }
    return value | changes


def fake_cli(tmp_path, body: str) -> tuple[str, ...]:
    script = tmp_path / "fake_cli.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return (sys.executable, str(script))


@pytest.mark.parametrize(
    "name",
    ["../x.ino", "/etc/passwd.h", "a\\b.h", "src//x.h", "sketch.yaml", "x.ino/../../y.h", ""],
)
def test_unsafe_paths_are_rejected(name):
    with pytest.raises(runner.BundleError):
        runner.clean_path(name)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sketch": "../x"}, "invalid sketch name"),
        ({"fqbn": "uno"}, "invalid board"),
        ({"fqbn": "esp32:esp32:esp32"}, "not built by this image"),
        ({"files": {"other.ino": ""}}, "missing main sketch file"),
        ({"files": {"blink.ino": "", "platformio.ini": ""}}, "file type not allowed"),
    ],
)
def test_bundles_are_checked_before_writing(tmp_path, changes, message):
    with pytest.raises(runner.BundleError, match=message):
        runner.write_sketch(tmp_path, bundle(**changes), "arduino:avr@1.8.8")


def test_compile_success_reports_sizes_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_text", lambda name: "arduino:avr@1.8.8")
    cli = fake_cli(
        tmp_path,
        """
        import pathlib, sys
        folder = pathlib.Path(sys.argv[-1])
        assert (folder / "blink.ino").exists() and (folder / "src" / "led.h").exists()
        assert sys.argv[sys.argv.index("--fqbn") + 1] == "arduino:avr:uno"
        print("Sketch uses 924 bytes (2%) of program storage space. Maximum is 32256 bytes.")
        print("Global variables use 9 bytes (0%) of dynamic memory.")
        """,
    )
    result = runner.compile_sketch(bundle(), cli=cli)
    assert result["status"] == "compiles" and result["log"] is None
    assert result["core"] == "arduino:avr@1.8.8"
    assert result["size"].startswith("Sketch uses 924 bytes")
    assert "Global variables" in result["size"]


def test_compile_failure_returns_errors_with_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_text", lambda name: None)
    cli = fake_cli(
        tmp_path,
        """
        import pathlib, sys
        folder = pathlib.Path(sys.argv[-1])
        print(f"{folder / 'blink.ino'}:2:1: error: expected ';'", file=sys.stderr)
        sys.exit(1)
        """,
    )
    result = runner.compile_sketch(bundle(), cli=cli)
    assert result["status"] == "compile_failed"
    assert result["log"].strip().replace("\\", "/") == "blink/blink.ino:2:1: error: expected ';'"


def test_compile_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_text", lambda name: None)
    cli = fake_cli(tmp_path, "import time\ntime.sleep(5)\n")
    assert runner.compile_sketch(bundle(), cli=cli, timeout=0.5)["status"] == "timeout"


def test_rejected_bundle_is_reported_not_compiled(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "read_text", lambda name: None)
    cli = fake_cli(tmp_path, "raise SystemExit('must not run')\n")
    result = runner.compile_sketch(bundle(files={"../blink.ino": ""}), cli=cli)
    assert result["status"] == "error" and "Bundle rejected" in result["detail"]
