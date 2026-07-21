"""Run the complete closed 20-case Tahap 3 mini evaluation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.core.config import get_settings
from backend.evaluation.runner import run_mini_evaluation
from backend.runtime.stage3 import create_stage3_runtime

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    runtime = create_stage3_runtime(ROOT, get_settings())
    try:
        summary = asyncio.run(run_mini_evaluation(runtime.demo_runner))
    finally:
        runtime.close()
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
