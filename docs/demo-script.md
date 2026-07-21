# Portfolio Demo Script

Target duration: 6–8 minutes. Use only the bundled synthetic Chinook data.

## Preparation

```powershell
uv sync --extra dev
uv run python scripts/dev.py generate-compose-env
docker compose --env-file .env.compose up --build --wait
```

Open `http://127.0.0.1:8501`. Keep `PROJECT_STATUS.md`, the Tahap 7 baseline,
and the latest release audit available. Do not expose `.env.compose`, terminal
history containing secrets, or raw Docker environment output while recording.

## Storyboard

1. **Problem and boundary (45 seconds).** Explain that business users need
   database-grounded answers, while LLM-generated SQL must be treated as
   untrusted. Point out Streamlit → FastAPI → PostgreSQL and the separate
   metadata boundary.
2. **Safe success (90 seconds).** Submit “Berapa jumlah pelanggan?”. Show the
   value `59`, generated SQL, separately rewritten executed SQL, AST validation
   badge, source tables/columns, request ID, and audit metadata.
3. **Result experience (60 seconds).** Show the table/KPI or chart, bounded CSV
   export, fixed-category feedback, and privacy-minimized Query History.
4. **Ambiguity (60 seconds).** Ask “Siapa pelanggan terbaik?”. Show that the
   system requests an explicit business definition before generation or
   execution; it does not silently choose revenue or order count.
5. **Security (75 seconds).** Use a catalogued adversarial prompt from the
   evaluation set and show a blocked state. Explain that the prompt is not the
   boundary: recursive AST policy plus an exact PostgreSQL read-only role is.
6. **Reproducibility (60 seconds).** Show the pinned Chinook source/checksums,
   100-case Tahap 7 result, 4-case live PostgreSQL gate, security report, and
   clean Compose/checkout evidence.
7. **Limitations (45 seconds).** State clearly that the default provider is
   `fake`, the deterministic corpus does not prove real-model generalization,
   and no public deployment or authentication scheme has been selected yet;
   the project code is MIT licensed.

## Close

Stop the local services without deleting the named development data volume:

```powershell
docker compose --env-file .env.compose down --remove-orphans
```
