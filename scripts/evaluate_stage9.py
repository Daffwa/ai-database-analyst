"""Evaluate deterministic implementation and external evidence for Stage 9."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "evaluation" / "stage-9-readiness.json"


def _json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    compose_source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_source)
    api_dockerfile = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    workflows = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    }
    compose_report = _json(ROOT / "reports" / "test-results" / "stage-9-compose.json")
    security_report = _json(ROOT / "reports" / "security" / "stage-9-security.json")
    clean_checkout_report = _json(ROOT / "reports" / "test-results" / "stage-9-clean-checkout.json")
    stage8_report = _json(ROOT / "reports" / "evaluation" / "stage-8-readiness.json")
    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    checks = {
        "stage8_gate_preserved": stage8_report.get("stage_gate_passed") is True,
        "pinned_non_root_images": all(
            "@sha256:" in source and "USER 10001:10001" in source
            for source in (api_dockerfile, frontend_dockerfile)
        ),
        "compose_services_complete": set(services) == {"db", "bootstrap", "api", "frontend"},
        "compose_health_and_readiness": all(
            "healthcheck" in services.get(name, {}) for name in ("db", "api", "frontend")
        )
        and services.get("api", {}).get("depends_on", {}).get("bootstrap", {}).get("condition")
        == "service_completed_successfully",
        "compose_has_named_volume": "postgres-data" in compose.get("volumes", {}),
        "compose_requires_runtime_secrets": "${POSTGRES_ADMIN_PASSWORD:?" in compose_source
        and "POSTGRES_PASSWORD: change-me" not in compose_source,
        "least_privilege_workflows": set(workflows)
        == {"ci.yml", "docker.yml", "evaluation.yml", "security.yml"}
        and all("contents: read" in source for source in workflows.values())
        and all("persist-credentials: false" in source for source in workflows.values()),
        "fork_workflows_reference_no_secrets": "secrets." not in "\n".join(workflows.values()),
        "observability_fields_present": all(
            field in (ROOT / "backend" / "api" / "routes.py").read_text(encoding="utf-8")
            for field in (
                "request_id",
                "stage",
                "status",
                "model",
                "prompt_version",
                "schema_hash",
                "sql_fingerprint",
                "latency_ms",
                "row_count",
                "error_code",
            )
        ),
        "request_id_frontend_api_propagation": "X-Request-ID"
        in (ROOT / "frontend" / "api_client.py").read_text(encoding="utf-8")
        and "current_request_id()"
        in (ROOT / "backend" / "services" / "orchestrator.py").read_text(encoding="utf-8"),
        "operational_rates_present": all(
            field in (ROOT / "backend" / "schemas" / "api.py").read_text(encoding="utf-8")
            for field in (
                "http_requests_per_second",
                "success_rate",
                "blocked_rate",
                "clarification_rate",
                "timeout_rate",
                "repair_rate",
                "input_tokens_total",
                "output_tokens_total",
            )
        ),
        "compose_gate_passed": compose_report.get("stage_gate_passed") is True,
        "security_gate_passed": security_report.get("stage_gate_passed") is True,
        "clean_checkout_gate_passed": clean_checkout_report.get("stage_gate_passed") is True,
    }
    implementation_checks = tuple(
        name
        for name in checks
        if name
        not in {
            "compose_gate_passed",
            "security_gate_passed",
            "clean_checkout_gate_passed",
        }
    )
    implementation_gate_passed = all(checks[name] for name in implementation_checks)
    stage_gate_passed = all(checks.values())
    report = {
        "report_version": "stage-9-readiness-v1",
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "implementation_gate_passed": implementation_gate_passed,
        "compose_gate_verified": checks["compose_gate_passed"],
        "security_gate_verified": checks["security_gate_passed"],
        "clean_checkout_gate_verified": checks["clean_checkout_gate_passed"],
        "stage_gate_passed": stage_gate_passed,
        "blocker": (
            None
            if stage_gate_passed
            else (
                "One or more Stage 9 implementation, clean-checkout, Compose, "
                "or security checks failed."
            )
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if implementation_gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
