# Sealed Holdout Boundary

This directory intentionally contains no holdout questions, SQL, or expected
rows. Private `*.jsonl` payloads and curator attestation text are ignored by
Git.

An independent curator must:

1. create a new `stage-7-holdout-vN` JSONL containing exactly 30 `holdout`
   cases under the public 5 filtering / 5 aggregation / 5 join / 3 time /
   3 ranking / 3 subquery / 3 ambiguity / 3 unsafe distribution;
2. keep that JSONL and the attestation outside Git and unavailable to the
   development agent;
3. run `scripts/create_sealed_holdout_manifest.py` locally with both explicit
   attestation flags;
4. provide only the generated manifest for candidate freeze; and
5. provide the matching private JSONL to the automated holdout runner only
   after the complete development report passes and the candidate is frozen.

The manifest commits the version, canonical payload SHA-256, case count,
category distribution, and curator-attestation SHA-256. Candidate freeze binds
the manifest hash and payload hash. Holdout execution rejects missing, altered,
partial, or mixed-split payloads before constructing the runtime or calling the
provider.

Do not ask the development agent to display, summarize, review, or commit the
private holdout payload.
