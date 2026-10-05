"""Token metering parses synthetic generateContent responses and never raises."""

import json

from bharat_sourcer.usage import record_usage


def test_usage_line_has_tokens_grounding_and_modalities(capsys):
    record_usage(
        "discovery",
        "gemini-test",
        {
            "usageMetadata": {
                "promptTokenCount": 1200,
                "candidatesTokenCount": 300,
                "thoughtsTokenCount": 50,
                "cachedContentTokenCount": 1000,
                "totalTokenCount": 1550,
                "promptTokensDetails": [{"modality": "VIDEO", "tokenCount": 900}],
            },
            "candidates": [{"groundingMetadata": {"groundingChunks": [{"web": {}}]}}],
        },
    )
    line = capsys.readouterr().out.strip()
    assert line.startswith("GEMINI_USAGE ")
    fields = json.loads(line.removeprefix("GEMINI_USAGE "))
    assert fields["site"] == "discovery" and fields["grounded"] is True
    assert (fields["prompt"], fields["cached"], fields["by_modality"]) == (
        1200,
        1000,
        {"VIDEO": 900},
    )


def test_usage_tolerates_missing_or_malformed_metadata(capsys):
    record_usage("chat_scope", "m", {})
    record_usage("chat_scope", "m", None)
    record_usage("chat_scope", "m", {"usageMetadata": "bad", "candidates": "bad"})
    out = capsys.readouterr().out
    assert out.count("GEMINI_USAGE") >= 1
