# Evaluation Artifacts

This directory will contain versioned evaluation summaries and regression
comparisons beginning in Tahap 3 and becoming a formal quality gate in Tahap 7.

Tahap 3 uses a small closed deterministic catalog only. It proves pipeline
mechanics and database grounding; it is not a statistically meaningful model
quality benchmark and is never injected into prompts as verified examples.

Tahap 4 adds a versioned known-unsafe SQL corpus and compares it with the 20
accepted baselines to report both blocking and false-blocking rates. This is
finite regression evidence, not a claim that all unknown attacks are prevented.

Tahap 5 adds deterministic semantic clarification and verified-query retrieval.
Tahap 6 reuses the 20 closed database cases to verify result identity,
presentation, result-only chart contracts, cell-grounded summaries, CSV, empty
state, feedback, history privacy, explorer coverage, and safe System Info.

Tahap 7 adds the formal `stage-7-v1` JSONL corpus: 20 filtering, 20
aggregation, 20 multi-table join, 10 time analysis, 10 ranking/top-N, 5
subquery, 5 ambiguity, and 10 unsafe cases. The tracked baseline includes 70
development and 30 holdout labels, normalized result expectations, metric
denominators, complete version provenance, P50/P95 latency, and privacy-minimized
per-case evidence. `stage-7-regression.json` compares current behavior with the
baseline and fails on any known security regression.

Every formal evaluation report must identify the dataset version, schema hash,
prompt version, semantic version, provider/model when applicable, runtime
configuration, timestamp, and Git commit.

Run the formal gate with:

```powershell
uv run python scripts/dev.py evaluate-stage7
```

The fake-provider baseline is deterministic regression evidence, not a claim
about real-model language generalization. Token/cost metrics remain unavailable
until a separately authorized provider run exists.

Tahap 8 adds `stage-8-readiness.json`. It deliberately separates deterministic
implementation readiness from actual PostgreSQL integration. The stage gate can
pass only when `reports/test-results/stage-8-postgres.json` records a successful
live container run.

Tahap 9 adds `stage-9-readiness.json`. It checks deterministic Docker, Compose,
workflow, and observability contracts, then requires separate successful
`stage-9-compose.json` and `stage-9-security.json` evidence before the local
stage gate can pass.

Tahap 10 adds `stage-10-readiness.json`. It verifies release documents, README
commands, local Markdown links, reviewed screenshot dimensions, prior evaluation and
external local gates, and the clean-checkout report. It reports the local
release gate separately from project-license, GitHub/hosted-CI, and optional
public-deployment decisions; missing external authorization must remain visible
rather than being counted as a local pass.
