# Real LLM Provider and Model Decision

- Decision status: Accepted by the project owner
- Decision date: 2026-08-07
- Provider: Google Gemini Developer API
- Model family: Gemma 4
- Selected hosted model: `gemma-4-26b-a4b-it`
- API method: `models.generateContent` over HTTPS
- Paid budget: USD 0; the selected Gemma 4 API tier is currently free-only
- Data scope: synthetic Chinook questions and bounded schema/semantic context

## Decision

Use Google Gemini Developer API with `gemma-4-26b-a4b-it` as the first real
provider baseline. Keep `FakeLLMAdapter` as the offline default for CI and
deterministic regression. Do not configure automatic provider fallback.

The owner explicitly replaced the earlier proposed OpenAI baseline with Google
Gemini and Gemma 4. The earlier OpenAI proposal was never accepted and no
OpenAI credential or paid request was used.

## Exact model selection

Google currently documents two hosted Gemma 4 identifiers for Gemini API:

- `gemma-4-31b-it`;
- `gemma-4-26b-a4b-it`.

The project uses `gemma-4-26b-a4b-it` because Google describes the 26B A4B
Mixture-of-Experts variant as designed for efficient throughput and advanced
reasoning, and uses it in the official hosted API examples. This is an
integration baseline, not a claim that it is more accurate than the 31B model.
SQL and Bahasa Indonesia quality must be measured on the repository corpus.

Official documentation:

- [Run Gemma with the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core)
- [Gemini API release notes](https://ai.google.dev/gemini-api/docs/changelog)

## Required capabilities

The selected path provides the capabilities needed by the roadmap:

- hosted text generation through `models.generateContent`;
- system instructions;
- JSON response mode and JSON Schema generation configuration;
- function declarations for later bounded tool calling;
- `minimal` and `high` thinking levels;
- provider-reported token usage metadata;
- explicit output-token and application timeout limits.

Gemma cannot execute tools or SQL by itself. The application remains
responsible for parsing model output, validating tool arguments, authorizing
SQL, executing only rewritten read-only SQL, and returning observations.

Official API references:

- [Generate content API](https://ai.google.dev/api/generate-content)
- [Function calling with Gemma 4](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)
- [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

## Cost and quota decision

The current Gemini Developer API pricing page lists Gemma 4 input, output, and
context caching as free of charge on the free tier, with no paid tier currently
available. Therefore this decision does not authorize a paid resource and sets
the paid budget to USD 0.

Free access still has project-specific quotas and rate limits. The runtime must
fail safely on `429` responses and must retain its timeout, output-token, query,
and agent-step limits even though token billing is currently zero.

Official pricing:
[Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing).

## Data-policy decision

Google's pricing and terms state that content submitted through the free tier
may be used to improve Google products. Consequently:

- allowed: synthetic Chinook questions, the public Chinook schema, and bounded
  versioned semantic context;
- prohibited without a new review: personal data, customer data, private
  production schemas, credentials, authorization headers, and raw production
  result rows.

The request sets `store: false`, but this does not override the free-tier terms.
The selected data scope is intentionally public/synthetic so the free-tier data
policy is acceptable for this capstone baseline.

Official policy:

- [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)

## Runtime policy

- `LLM_PROVIDER=gemini`
- `LLM_MODEL=gemma-4-26b-a4b-it`
- `LLM_THINKING_LEVEL=minimal` for the first baseline
- `LLM_MAX_OUTPUT_TOKENS=4096`
- `LLM_TIMEOUT_SECONDS=30`
- `LLM_API_KEY` loaded only from an ignored local environment file or runtime
  secret injection
- response MIME type `application/json`
- response schema matching `StructuredSQLProposal`
- temperature `0`
- request storage flag `false`
- no automatic retry in the first adapter version
- no automatic provider fallback

Thinking level `high` may be compared later only through the versioned
evaluation workflow. Invalid output is never retried without a bounded,
explicit policy.

## Credential incident and required remediation

An API key was pasted into the conversation on 2026-08-07. It must be treated
as compromised even if it has not yet been abused. The implementation did not
write, print, validate, or use that value.

Before a live smoke test:

1. revoke or rotate the exposed key in Google AI Studio;
2. place the replacement key directly in the ignored local `.env` file as
   `LLM_API_KEY=...`;
3. never paste the replacement key into chat, source, documentation, test
   fixtures, screenshots, or Git history;
4. confirm the key is restricted to the intended Google project/API where
   available.

## Fallback behavior

Authentication failure, quota exhaustion, timeout, network failure, malformed
provider envelopes, and invalid structured output fail closed through the
existing sanitized error contract. The prompt is not silently sent to another
provider.

`FakeLLMAdapter` remains available for offline tests and the deterministic demo;
it is not an answer fallback for unknown real questions.

## Remaining validation gate

The provider/model decision, local adapter, and one synthetic live API smoke
are complete. The smoke passed on 2026-08-07 with `gemini` /
`gemma-4-26b-a4b-it`, structured intent `unsupported`, and 152 total tokens.
However, the point 3 audit later found a credential-like value in tracked
`.env.compose.example`. It was removed immediately. A second rotation was
verified on 2026-08-08: the active credential is stored only in ignored `.env`,
has no exact match in tracked files, and passed the bounded live smoke. Point 3
is complete. Real-model development/holdout evaluation remains a later point 5
gate.
