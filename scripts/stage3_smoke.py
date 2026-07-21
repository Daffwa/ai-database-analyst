"""Run one deterministic Tahap 3 question and print its auditable response."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.core.config import get_settings
from backend.runtime.stage3 import create_stage3_runtime

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="Berapa jumlah pelanggan?")
    args = parser.parse_args()

    runtime = create_stage3_runtime(ROOT, get_settings())
    try:
        response = asyncio.run(runtime.demo_runner.run(args.question))
    finally:
        runtime.close()
    print(json.dumps(response.model_dump(mode="json"), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
