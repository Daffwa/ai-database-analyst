# Test Result Artifacts

This directory will contain human-readable or machine-generated verification
artifacts when testing begins in Tahap 1. Generated large or environment-specific
reports may be excluded from Git; milestone summaries must remain reproducible
from documented commands.

Milestone summaries through Tahap 10 are tracked here. Each report names the
reproducible command, quality checks, total test result, coverage, and
stage-specific evidence.

`stage-8-postgres.json` is the machine-readable external gate. It must remain
false when Docker/PostgreSQL is unavailable; skipped tests are not counted as a
successful integration run.

`stage-9-compose.json` is the machine-readable no-cache whole-stack gate. Its
success requires healthy database/API/frontend services, end-to-end request
correlation, privacy-safe logs and metrics, non-root images, no generated
credential in image metadata/history, and successful cleanup.

`stage-10-summary.md` records documentation, browser QA, updated adversarial
runtime behavior, complete local audit evidence, and the exact external release
decisions that remain pending.
