"""One live Gemini discovery probe; print only non-sensitive response diagnostics."""

import argparse
import json

import httpx

from bharat_sourcer.config import Settings
from bharat_sourcer.sourcing.service import DiscoveryError, GeminiDiscovery


class Diagnostics(httpx.HTTPTransport):
    def handle_request(self, request):
        response = super().handle_request(request)
        response.read()
        data = json.loads(response.content)
        print(
            json.dumps(
                {
                    "http_status": response.status_code,
                    "error_status": data.get("error", {}).get("status"),
                    "usage": data.get("usageMetadata"),
                    "candidates": [
                        {
                            "finishReason": c.get("finishReason"),
                            "sources": len(
                                c.get("groundingMetadata", {}).get("groundingChunks", [])
                            ),
                        }
                        for c in data.get("candidates", [])
                    ],
                }
            ),
            flush=True,
        )
        return response


parser = argparse.ArgumentParser()
parser.add_argument("--part", required=True)
args = parser.parse_args()
try:
    result = GeminiDiscovery(Settings(), transport=Diagnostics()).discover(args.part)
    print(f"Discovery accepted {len(result.source_urls)} source URLs")
except DiscoveryError as exc:
    print(f"Discovery rejected: {type(exc.__cause__).__name__}")
