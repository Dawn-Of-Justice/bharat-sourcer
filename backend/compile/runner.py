"""Compile runner for one code-adapt compile check (Cloud Run job task; stdlib only).

The job is started by the API with one override, BS_COMPILE_RUN_ID. The runner:

1. gets an ID token for the API from the metadata server (its service account has no
   roles; the token only proves which runner is calling);
2. fetches the sketch for the run from the API (`GET /internal/compile/<run_id>`);
3. writes the files into a temporary sketch folder after checking every path;
4. runs `arduino-cli compile` with the image's pinned core and libraries, with a time
   limit, never `upload`;
5. posts the outcome back (`POST /internal/compile/<run_id>/result`).

The job has no internet route (Direct VPC egress to a subnet without NAT); Private Google
Access reaches only Google endpoints such as the API. Code is compiled, never run.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "arduino-cli.yaml"
SUFFIXES = (".ino", ".cpp", ".c", ".h", ".hpp", ".s", ".tpp", ".ipp")
SEGMENT = re.compile(r"[A-Za-z0-9._~ +-]{1,100}")
SKETCH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}")
FQBN = re.compile(r"[\w.-]+:[\w.-]+:[\w.-]+")
MAX_FILES = 150
MAX_BYTES = 1_500_000
COMPILE_TIMEOUT_S = 300
OUTPUT_CHARS = 50_000
METADATA = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default"


class BundleError(ValueError):
    pass


def read_text(name: str) -> str | None:
    path = HERE / name
    return path.read_text("utf-8").strip() if path.exists() else None


def id_token(audience: str) -> str:
    query = urllib.parse.urlencode({"audience": audience, "format": "full"})
    request = urllib.request.Request(
        f"{METADATA}/identity?{query}", headers={"Metadata-Flavor": "Google"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode()


def call(url: str, token: str, body: dict | None = None, timeout: float = 120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if body is not None else "GET",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def clean_path(name: str) -> str:
    """A safe sketch-relative path, or BundleError."""
    if not isinstance(name, str) or "\\" in name or name.startswith("/"):
        raise BundleError("invalid file path")
    segments = name.split("/")
    if len(segments) > 8 or any(s in {"", ".", ".."} or not SEGMENT.fullmatch(s) for s in segments):
        raise BundleError("invalid file path")
    if not name.lower().endswith(SUFFIXES):
        raise BundleError("file type not allowed")
    return name


def write_sketch(root: Path, bundle: dict, core: str | None) -> Path:
    sketch, fqbn, files = bundle.get("sketch"), bundle.get("fqbn"), bundle.get("files")
    if not isinstance(sketch, str) or not SKETCH.fullmatch(sketch):
        raise BundleError("invalid sketch name")
    if not isinstance(fqbn, str) or not FQBN.fullmatch(fqbn):
        raise BundleError("invalid board")
    if core and ":".join(fqbn.split(":")[:2]) != core.split("@")[0]:
        raise BundleError("board is not built by this image")
    if not isinstance(files, dict) or not files or len(files) > MAX_FILES:
        raise BundleError("invalid file list")
    if f"{sketch}.ino" not in files:
        raise BundleError("missing main sketch file")
    if sum(len(str(text).encode()) for text in files.values()) > MAX_BYTES:
        raise BundleError("sketch too large")
    folder = root / sketch
    for name, text in files.items():
        target = folder / clean_path(name)
        if not isinstance(text, str):
            raise BundleError("invalid file content")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return folder


def sizes(output: str) -> str | None:
    found = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(("Sketch uses", "Global variables use"))
    ]
    return " ".join(found)[:1000] or None


def compile_sketch(
    bundle: dict, *, cli: tuple[str, ...] = ("arduino-cli",), timeout: float = COMPILE_TIMEOUT_S
) -> dict:
    core = read_text("core.txt")
    work = Path(tempfile.mkdtemp(prefix="sketch-"))
    try:
        try:
            folder = write_sketch(work, bundle, core)
        except BundleError as exc:
            return {"status": "error", "detail": f"Bundle rejected: {exc}", "core": core}
        build = work / "build"
        command = [
            *cli,
            "--config-file",
            str(CONFIG),
            "compile",
            "--fqbn",
            bundle["fqbn"],
            "--build-path",
            str(build),
            "--warnings",
            "default",
            "--no-color",
            str(folder),
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, cwd=work
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            output = output.decode() if isinstance(output, bytes) else output
            return {
                "status": "timeout",
                "log": relative(output, work)[-OUTPUT_CHARS:],
                "core": core,
            }
        output = relative(result.stdout + "\n" + result.stderr, work)
        print(f"compile exit={result.returncode} seconds={time.monotonic() - started:.0f}")
        failed = result.returncode != 0
        errors = relative(result.stderr, work) if result.stderr.strip() else output
        return {
            "status": "compile_failed" if failed else "compiles",
            "log": errors[-OUTPUT_CHARS:] if failed else None,
            "size": sizes(output),
            "core": core,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def relative(text: str, root: Path) -> str:
    return text.replace(str(root) + os.sep, "").replace(str(root), "")


def main() -> int:
    api = os.environ["BS_COMPILE_API_URL"].rstrip("/")
    run_id = os.environ["BS_COMPILE_RUN_ID"]
    token = id_token(api)
    status, bundle = call(f"{api}/internal/compile/{urllib.parse.quote(run_id)}", token)
    if status in {404, 409, 410}:
        print(f"run {run_id} not compilable or no longer current (HTTP {status})")
        return 0
    if status != 200 or not isinstance(bundle, dict):
        print(f"bundle request failed (HTTP {status})")
        return 1
    try:
        result = compile_sketch(bundle)
    except Exception as exc:  # noqa: BLE001 - report any runner failure to the API
        result = {"status": "error", "detail": f"Runner failed: {type(exc).__name__}"}
    result = {k: v for k, v in result.items() if v is not None}
    status, _ = call(
        f"{api}/internal/compile/{urllib.parse.quote(run_id)}/result",
        id_token(api),
        result,
        timeout=300,
    )
    print(f"reported {result['status']} (HTTP {status})")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
