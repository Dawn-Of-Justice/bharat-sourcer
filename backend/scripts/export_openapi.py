"""Run from backend/: python scripts/export_openapi.py [--check]."""

import argparse
import json
from pathlib import Path

from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
target = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.json"
schema = create_app(Settings(_env_file=None, demo_mode=True, storage_backend="memory")).openapi()
content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
if args.check:
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        raise SystemExit("OpenAPI contract is stale. Run python scripts/export_openapi.py")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
