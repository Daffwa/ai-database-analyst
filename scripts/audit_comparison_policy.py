"""Generate deterministic development-only evidence for semantic comparator v2."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from backend.evaluation.case_loader import load_evaluation_dataset
from backend.evaluation.comparison_audit import build_comparison_policy_audit
from backend.schemas.evaluation import ComparisonPolicyAudit

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"
REPORT_PATH = ROOT / "reports" / "evaluation" / "stage-7-comparison-policy-v2-audit.json"
MARKDOWN_PATH = ROOT / "reports" / "evaluation" / "stage-7-comparison-policy-v2-audit.md"


def _markdown(audit: ComparisonPolicyAudit) -> str:
    metric_rows = "\n".join(
        (
            _metric_row(
                "Exact self matches", audit.exact_self_matches, audit.analytical_case_count
            ),
            _metric_row(
                "Presentation variants accepted",
                audit.presentation_variants_accepted,
                audit.presentation_variants_tested,
            ),
            _metric_row(
                "Same variants rejected by strict-v1",
                audit.strict_policy_presentation_rejections,
                audit.presentation_variants_tested,
            ),
            _metric_row(
                "Substantive variants rejected",
                audit.substantive_variants_rejected,
                audit.substantive_variants_tested,
            ),
            _metric_row(
                "Required-order changes rejected",
                audit.required_order_variants_rejected,
                audit.required_order_variants_tested,
            ),
            _metric_row(
                "Irrelevant-order changes accepted",
                audit.irrelevant_order_variants_accepted,
                audit.irrelevant_order_variants_tested,
            ),
        )
    )
    return (
        f"""# Stage 7 Semantic Comparison Policy v2 Audit

- Gate: {"passed" if audit.gate_passed else "failed"}
- Dataset: `{audit.dataset_version}` / `{audit.dataset_sha256}`
- Split scored: `{audit.split.value}`
- Policy: `{audit.comparison_policy.value}`
- Holdout cases scored: {audit.holdout_cases_scored}

| Invariant | Result |
|---|---:|
{metric_rows}

## Gate failures

{", ".join(audit.gate_failures) if audit.gate_failures else "None."}

## Boundaries

"""
        + "\n".join(f"- {limitation}" for limitation in audit.limitations)
        + "\n"
    )


def _metric_row(label: str, numerator: int, denominator: int) -> str:
    return f"| {label} | {numerator}/{denominator} |"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if (args.output.exists() or args.markdown.exists()) and not args.force:
        print("Comparison audit not written: output exists; use --force.")
        return 2
    audit = build_comparison_policy_audit(load_evaluation_dataset(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(audit.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(_markdown(audit), encoding="utf-8")
    print(
        f"comparison_policy={audit.comparison_policy.value} "
        f"development_cases={audit.development_case_count} "
        f"holdout_scored={audit.holdout_cases_scored} "
        f"gate_passed={audit.gate_passed}"
    )
    return 0 if audit.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
