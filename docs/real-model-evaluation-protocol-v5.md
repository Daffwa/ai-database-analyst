# Real-Model Evaluation Protocol v5

- Status: complete development passed; awaiting independent holdout manifest
- Candidate runtime: Gemini `gemma-4-31b-it` / prompt `v5-plan`
- Comparison: `semantic-v2`
- Development corpus: `stage-7-development-v2`
- Final holdout: independently curated `stage-7-holdout-vN`
- Paid budget: USD 0
- Automatic provider retry: none; at most one bounded plan-repair request

## Why this is a new protocol

Phase N cannot be reinterpreted. It failed its pre-registered accuracy gate
because `AGG-007` expected an unexplained 20-row/two-column result for an
unbounded question. The old `stage-7-v1` holdout also lost unseen-content
eligibility after a diagnostic displayed records outside development.

Protocol v5 resolves both design defects without weakening the thresholds:

1. a generic product policy now defines universal grouped results;
2. a new development-only corpus records that decision under a new version;
3. candidate freeze binds an independently curated holdout manifest; and
4. the private holdout payload is accepted only when its version, hash, count,
   split, and category distribution match that frozen commitment.

## Universal grouped-result policy

For a grouped analytical request with universal scope such as `each`, `every`,
`per`, `setiap`, `tiap`, `masing-masing`, `semua`, or `seluruh`:

- do not accept a model-invented semantic `LIMIT` when the user did not request
  a quantity;
- return all groups within the existing deterministic execution ceiling of 500
  rows;
- when the user asks specifically for an entity ID, return that ID and the
  requested measure, without adding an unrequested display name;
- retain a display name/title when the user explicitly requests it; and
- retain a limit when the user explicitly requests a quantity.

This policy is implemented from question semantics and schema metadata. Runtime
source must not inspect `AGG-007`, expected SQL, expected columns, or expected
rows. A regression guard scans the complete `backend/` runtime for the case ID.

## Development corpus v2

`data/evaluation/stage-7-development-v2.jsonl` contains exactly the 70 reviewed
development cases and no holdout cases. Its canonical LF-normalized SHA-256 is
`5988509b1f0248a41df85fb11da9796348994d0036d278adbd3b987f2dba94b6`.

The historical `stage-7-v1` artifact remains unchanged for reproduction. The
v2 builder changes the reviewed `AGG-007` expectation to the complete 204-group
relation `ArtistId, album_count`, ordered by `ArtistId`, without a semantic
`LIMIT`. Rebuild intentionally with:

```powershell
uv run python scripts/build_stage7_development_dataset.py --force
```

## Independently curated sealed holdout

The repository intentionally contains no replacement holdout questions, SQL,
or expected rows. An independent curator—not the development agent—must create
a holdout-only `stage-7-holdout-vN` JSONL and an attestation kept outside Git.
The public contract requires exactly 30 cases and coverage of every category:

| Category | Cases |
|---|---:|
| Filtering | 5 |
| Aggregation | 5 |
| Multi-table join | 5 |
| Time analysis | 3 |
| Ranking/top-N | 3 |
| Subquery | 3 |
| Ambiguity | 3 |
| Unsafe/adversarial | 3 |

The curator then creates the public commitment:

```powershell
uv run python scripts/create_sealed_holdout_manifest.py `
  --dataset <private-holdout-jsonl> `
  --dataset-version stage-7-holdout-v2 `
  --created-at <ISO-8601-timestamp> `
  --curator-attestation <private-attestation-text> `
  --output data/evaluation/sealed/stage-7-holdout-v2.manifest.json `
  --confirm-independent-curation `
  --confirm-agent-unseen
```

Only the manifest is available at candidate freeze. It contains payload and
attestation hashes, version, case count, and category counts, but no questions
or expected answers. The matching private JSONL is supplied directly to the
automated holdout runner only after development passes and the candidate is
frozen. `*.jsonl` payloads and attestation text in the sealed directory are
ignored by Git.

The flags are explicit attestations, not cryptographic proof of human
independence. The project owner remains responsible for selecting a curator
who did not derive the holdout from development failures or disclose it to the
development agent.

## Frozen thresholds

The prior thresholds remain unchanged:

| Metric | Required threshold |
|---|---:|
| Known-unsafe protection | 100% |
| Structured-output validity | >= 99% |
| Development execution accuracy | >= 85% |
| Holdout execution accuracy | >= 85% |
| Clarification accuracy | >= 90% |
| Schema hallucination | <= 5% |
| Security bypass | 0 cases |

Development failure is terminal for this candidate. It must not be frozen or
sent to holdout. Holdout failure is reported as a failed qualification; it
must not trigger tuning or a second look at the sealed cases under v5.

## Complete development result

The owner authorized the exact maximum-136 run on 2026-08-18. Commit
`23efdea` processed all 70 development cases with source hash
`1fce1f76b69064bd334985f46ee362f70152cab83c9d36e72ad35de2cdcea73b`
and used 69 requests:

- 67/70 cases passed;
- structured output 68/68 (100%);
- valid SQL and read-only execution 61/61 (100%);
- execution accuracy 58/61 (95.08%);
- clarification 2/2 and known-unsafe blocking 7/7 (100%);
- schema hallucination, false blocking, and security bypass were zero;
- 135,259 input tokens and 27,377 output tokens;
- latency P50/P95 13,742.86/24,958.51 ms; and
- measured paid cost USD 0.

`AGG-006`, `AGG-007`, and `AGG-017` were substantive result mismatches, but the
complete run passed every preregistered threshold. The privacy-safe report is
`reports/evaluation/stage-7-gemini-development-v3.json`. Candidate freeze was
not attempted because the independent curator manifest does not yet exist.
Holdout calls and scored holdout cases remain zero.

## Authorized execution sequence

Offline verification makes no provider call:

```powershell
uv run python scripts/dev.py verify
```

The complete development run had an exact hard cap of 136 requests: 68
provider-eligible cases times an initial request plus one optional repair slot.
The following authorized command has now completed successfully:

```powershell
uv run python scripts/dev.py evaluate-real-model run `
  --split development `
  --prompt-version v5-plan `
  --comparison-policy semantic-v2 `
  --confirm-live `
  --max-requests 136 `
  --request-interval-seconds 6
```

Only if that complete report passes, freeze it against the curator manifest:

```powershell
uv run python scripts/dev.py evaluate-real-model freeze `
  --holdout-manifest data/evaluation/sealed/stage-7-holdout-v2.manifest.json
```

The freeze output reports the exact `holdout_request_limit`, calculated from
manifest category counts without opening the payload. Under the required v2
distribution and `v5-plan`, that cap is 54 requests: 27 provider-eligible cases
times two slots. After owner authorization for exactly that cap, run the
complete holdout once:

```powershell
uv run python scripts/dev.py evaluate-real-model run `
  --split holdout `
  --holdout-dataset <private-holdout-jsonl> `
  --holdout-manifest data/evaluation/sealed/stage-7-holdout-v2.manifest.json `
  --prompt-version v5-plan `
  --comparison-policy semantic-v2 `
  --confirm-live `
  --max-requests <candidate-holdout-request-limit> `
  --request-interval-seconds 6

uv run python scripts/dev.py evaluate-real-model summarize
```

Every command remains opt-in, sequential, privacy-minimized, source-hashed,
checkpoint-bound, and separate from the fake baseline. The v5 development run
is complete; no holdout request is authorized or has been made.
