"""Tier 2 code adaptation tests. All sketches and model responses are synthetic; no network."""

import json

import httpx
import pytest

from bharat_sourcer.code_adapt_ai import (
    PatchError,
    apply_unified_diff,
    draft_patch,
    make_gemini_generate,
    validate_draft,
)
from bharat_sourcer.config import Settings

# Synthetic sketch: a DHT11 weather logger with unrelated filler so change ratios stay small.
SKETCH = """#include <DHT.h>
#define DHTPIN 2
DHT dht(DHTPIN, DHT11);

void setup() {
  Serial.begin(9600);
  dht.begin();
}

void blink() {
  digitalWrite(13, HIGH);
  delay(100);
  digitalWrite(13, LOW);
  delay(100);
}

void loop() {
  float t = dht.readTemperature();
  Serial.println(t);
  blink();
  delay(2000);
}
"""

GOOD_DIFF = """--- a/logger.ino
+++ b/logger.ino
@@ -1,3 +1,3 @@
-#include <DHT.h>
+#include <Adafruit_BME280.h>
 #define DHTPIN 2
-DHT dht(DHTPIN, DHT11);
+Adafruit_BME280 bme;
@@ -5,6 +5,6 @@
 void setup() {
   Serial.begin(9600);
-  dht.begin();
+  bme.begin(0x76);
 }

 void blink() {
@@ -17,6 +17,6 @@
 void loop() {
-  float t = dht.readTemperature();
+  float t = bme.readTemperature();
   Serial.println(t);
   blink();
   delay(2000);
 }
"""

FILES = {"logger.ino": SKETCH}
ALLOWED = {"Adafruit_BME280.h"}
MARKERS = {"DHT.h", "dht", "DHT11"}
ORIGINAL = {"id": "synthetic-dht11", "name": "DHT11 (synthetic)"}
SUBSTITUTE = {"id": "synthetic-bme280", "name": "BME280 (synthetic)"}
CHANGES = ["Replace the DHT library with Adafruit_BME280 and use bme.readTemperature()."]


def _validate(diffs, files=FILES):
    return validate_draft(files, diffs, allowed_new_includes=ALLOWED, original_markers=MARKERS)


def _draft(responses, files=FILES):
    calls = []

    def generate(prompt, schema):
        calls.append(prompt)
        response = responses[len(calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    result = draft_patch(
        files,
        original=ORIGINAL,
        substitute=SUBSTITUTE,
        changes=CHANGES,
        allowed_new_includes=ALLOWED,
        original_markers=MARKERS,
        generate=generate,
    )
    return result, calls


def _response(diff, path="logger.ino"):
    return {"files": [{"path": path, "unified_diff": diff}], "notes": ["n"], "assumptions": []}


# --- diff applier --------------------------------------------------------------------------


def test_clean_apply_with_multiple_hunks():
    patched = apply_unified_diff(SKETCH, GOOD_DIFF, "logger.ino")
    assert "#include <Adafruit_BME280.h>" in patched
    assert "bme.begin(0x76);" in patched and "dht" not in patched
    assert patched.endswith("}\n")
    assert patched.count("\n") == SKETCH.count("\n")


def test_context_mismatch_raises():
    bad = GOOD_DIFF.replace(" #define DHTPIN 2", " #define DHTPIN 4")
    with pytest.raises(PatchError, match="does not match"):
        apply_unified_diff(SKETCH, bad)


def test_shifted_hunk_is_not_fuzzed():
    bad = GOOD_DIFF.replace("@@ -17,6 +17,6 @@", "@@ -16,6 +16,6 @@")
    with pytest.raises(PatchError):
        apply_unified_diff(SKETCH, bad)


def test_wrong_file_and_rename_rejected():
    with pytest.raises(PatchError, match="expected"):
        apply_unified_diff(SKETCH, GOOD_DIFF, "other.ino")
    renamed = GOOD_DIFF.replace("+++ b/logger.ino", "+++ b/new.ino")
    with pytest.raises(PatchError, match="renames"):
        apply_unified_diff(SKETCH, renamed)


def test_out_of_order_and_bad_counts_rejected():
    hunks = GOOD_DIFF.split("@@ -5,6")
    swapped = "@@ -5,6" + hunks[1] + hunks[0].split("\n", 2)[2]
    with pytest.raises(PatchError, match="overlaps or is out of order"):
        apply_unified_diff(SKETCH, swapped)
    with pytest.raises(PatchError, match="declares"):
        apply_unified_diff(SKETCH, GOOD_DIFF.replace("@@ -1,3 +1,3 @@", "@@ -1,4 +1,3 @@"))


def test_crlf_is_preserved():
    crlf = SKETCH.replace("\n", "\r\n")
    patched = apply_unified_diff(crlf, GOOD_DIFF)
    assert patched == apply_unified_diff(SKETCH, GOOD_DIFF).replace("\n", "\r\n")


def test_no_newline_at_end_of_file():
    original = "a\nb\nc"
    diff = "@@ -2,2 +2,2 @@\n b\n-c\n\\ No newline at end of file\n+C\n"
    assert apply_unified_diff(original, diff) == "a\nb\nC\n"
    keep = (
        "@@ -2,2 +2,2 @@\n b\n-c\n\\ No newline at end of file\n+C\n\\ No newline at end of file\n"
    )
    assert apply_unified_diff(original, keep) == "a\nb\nC"
    with pytest.raises(PatchError, match="final newline"):
        apply_unified_diff(original, "@@ -2,2 +2,2 @@\n b\n-c\n+C\n")
    with pytest.raises(PatchError, match="final newline"):
        apply_unified_diff("a\nb\nc\n", diff)


def test_pure_insertion():
    assert apply_unified_diff("a\nb\n", "@@ -1,0 +2,1 @@\n+x\n") == "a\nx\nb\n"


# --- validator -----------------------------------------------------------------------------


def test_good_draft_validates():
    patched, errors = _validate({"logger.ino": GOOD_DIFF})
    assert errors == []
    assert "Adafruit_BME280 bme;" in patched["logger.ino"]


def test_extra_file_rejected():
    _, errors = _validate({"logger.ino": GOOD_DIFF, "secrets.h": "@@ -0,0 +1 @@\n+x\n"})
    assert any("secrets.h: not one of the provided files" in e for e in errors)


def _one_line_diff(new_line):
    return (
        f"@@ -5,3 +5,4 @@\n void setup() {{\n   Serial.begin(9600);\n+{new_line}\n   dht.begin();\n"
    )


@pytest.mark.parametrize(
    ("line", "label"),
    [
        ('  system("reboot");', "process execution"),
        ('  popen("ls", "r");', "process execution"),
        ('  http.begin("http://example.invalid/x");', "network access"),
        ("  WiFiClient client;", "network access"),
        ('  File f = SD.open("log.txt");', "filesystem access"),
        ('  const char* api_key = "abc";', "credential"),
        ('  const char* k = "AIzaSyD0000000000000000000000000000";', "credential"),
    ],
)
def test_hostile_added_lines_rejected(line, label):
    _, errors = _validate({"logger.ino": _one_line_diff(line)})
    assert any(label in e for e in errors), errors


def test_unknown_include_rejected_but_allowed_include_passes():
    _, errors = _validate({"logger.ino": _one_line_diff("#include <WiFi.h>")})
    assert any("'WiFi.h' not allowed" in e for e in errors)
    _, errors = _validate({"logger.ino": _one_line_diff("#include <adafruit_bme280.h>")})
    assert errors == []


def test_python_imports_checked():
    files = {"main.py": "import dht\nimport machine\nd = dht.DHT11(machine.Pin(4))\n"}
    diff = (
        "@@ -1,3 +1,4 @@\n import dht\n+import os\n import machine\n"
        " d = dht.DHT11(machine.Pin(4))\n"
    )
    _, errors = validate_draft(
        files, {"main.py": diff}, allowed_new_includes={"bme280"}, original_markers={"dht"}
    )
    assert any("'os' not allowed" in e for e in errors)


def test_unrelated_rewrite_far_from_markers_rejected():
    diff = (
        "@@ -11,3 +11,3 @@\n   digitalWrite(13, HIGH);\n-  delay(100);\n+  delay(50);\n"
        "   digitalWrite(13, LOW);\n"
    )
    _, errors = _validate({"logger.ino": diff})
    assert any("unrelated to the original part" in e for e in errors)


def test_large_change_rejected():
    lines = SKETCH.splitlines()
    removed = "".join(f"-{line}\n" for line in lines)
    added = "".join(f"+{line.replace('dht', 'bme')}\n" for line in lines)
    diff = f"@@ -1,{len(lines)} +1,{len(lines)} @@\n{removed}{added}"
    _, errors = _validate({"logger.ino": diff})
    assert any("more than 40%" in e for e in errors)


def test_unapplicable_and_empty_drafts_rejected():
    _, errors = _validate({"logger.ino": "@@ -1,1 +1,1 @@\n-nope\n+x\n"})
    assert any("does not apply" in e for e in errors)
    assert _validate({})[1] == ["draft contains no changes"]


# --- drafting flow -------------------------------------------------------------------------


def test_draft_success_first_call():
    result, calls = _draft([_response(GOOD_DIFF)])
    assert result.ok and result.calls == 1 and len(calls) == 1
    assert result.diffs == {"logger.ino": GOOD_DIFF}
    assert "bme.readTemperature()" in result.files["logger.ino"]
    assert result.notes == ["n"]
    assert "<untrusted>" in calls[0] and SKETCH in calls[0]


def test_repair_succeeds_on_second_call():
    hostile = _response(_one_line_diff('  system("rm -rf /");'))
    result, calls = _draft([hostile, _response(GOOD_DIFF)])
    assert result.ok and result.calls == 2
    assert "process execution" in calls[1]


def test_both_attempts_fail():
    bad = _response(GOOD_DIFF, path="other.ino")
    result, _ = _draft([bad, {"files": "nope"}])
    assert not result.ok and result.reason == "ai_failed_validation" and result.calls == 2
    assert result.errors


def test_generate_raising_fails_cleanly():
    result, _ = _draft([RuntimeError("boom")])
    assert not result.ok and result.reason == "ai_failed_validation" and result.calls == 1
    result, _ = _draft([_response("garbage"), TimeoutError()])
    assert not result.ok and result.reason == "ai_failed_validation" and result.calls == 2


def test_input_limits():
    four = {f"f{i}.ino": SKETCH for i in range(4)}
    result, calls = _draft([], files=four)
    assert result.reason == "file_not_read" and result.calls == 0 and calls == []
    big = {"big.ino": "x" * (60 * 1024 + 1)}
    assert _draft([], files=big)[0].reason == "file_not_read"
    assert _draft([], files={})[0].reason == "file_not_read"


# --- Gemini adapter (mock transport) -------------------------------------------------------


def test_gemini_generate_uses_mock_transport(monkeypatch):
    seen = {}
    recorded = []
    monkeypatch.setattr(
        "bharat_sourcer.code_adapt_ai.record_usage", lambda *args, **kw: recorded.append(args)
    )

    def handler(request):
        seen["body"] = json.loads(request.content)
        text = json.dumps(_response(GOOD_DIFF))
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
        )

    settings = Settings(gemini_api_key="synthetic-test-key")
    generate = make_gemini_generate(settings, transport=httpx.MockTransport(handler))
    assert generate("prompt", {"type": "object"})["files"][0]["path"] == "logger.ino"
    config = seen["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["maxOutputTokens"] == 8192
    assert recorded and recorded[0][0] == "code_adapt"
