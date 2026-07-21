"""Backward-compatible aliases for the runtime advanced in Tahap 4."""

from backend.runtime.stage4 import Stage4Runtime, create_stage4_runtime

Stage3Runtime = Stage4Runtime
create_stage3_runtime = create_stage4_runtime

__all__ = ["Stage3Runtime", "create_stage3_runtime"]
