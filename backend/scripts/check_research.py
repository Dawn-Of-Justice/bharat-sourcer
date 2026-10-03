"""Explicit live research check; paid model use, labelled synthetic or guarded URL input."""

import argparse
import json
from pathlib import Path

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem, ResearchSource
from bharat_sourcer.sourcing.fetch import Page, SafeFetcher
from bharat_sourcer.sourcing.research import GeminiResearch


class DiagnosticTransport(httpx.HTTPTransport):
    def handle_request(self, request):
        response = super().handle_request(request)
        response.read()
        # Response only: never record request headers or credentials.
        Path(".data/research-provider-response.json").write_bytes(response.content)
        print("Provider HTTP status:", response.status_code, flush=True)
        return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Guarded source URL; omit for labelled synthetic text")
    parser.add_argument("--part", default="Synthetic Model B bearing")
    args = parser.parse_args()
    Path(".data").mkdir(exist_ok=True)
    page = (
        SafeFetcher().get(args.url)
        if args.url
        else Page(
            "https://manufacturer.example/fixture",
            200,
            {"content-type": "text/plain"},
            b"Synthetic Model B bearing. Bore diameter 8 mm. "
            b"Test fixture only. Not a real product.",
        )
    )
    reader = GeminiResearch(Settings(), DiagnosticTransport())
    item = BomItem(line_id="L01", raw_name=args.part)
    result = reader.research(item, [page], [ResearchSource(url=page.url, status="read")], [item])
    Path(".data/research-check.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "synthetic": not bool(args.url),
                "status": result.status,
                "candidates": len(result.candidates),
                "facts": sum(len(c.facts) for c in result.candidates),
                "questions": len(result.questions)
                + sum(len(c.assessment.questions) for c in result.candidates),
            }
        )
    )
    if result.status != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
