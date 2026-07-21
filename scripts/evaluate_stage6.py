"""Run the real database-backed Tahap 6 result and UX evaluation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.core.config import get_settings
from backend.evaluation.result_runner import run_result_evaluation
from backend.runtime.stage6 import create_stage6_runtime

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    runtime = create_stage6_runtime(ROOT, get_settings())
    try:
        summary = asyncio.run(run_result_evaluation(runtime))
    finally:
        runtime.close()
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return int(bool(summary.failed_case_ids))


if __name__ == "__main__":
    raise SystemExit(main())
