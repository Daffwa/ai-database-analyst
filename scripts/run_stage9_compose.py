"""Build without cache and verify the complete Stage 9 Compose stack."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.generate_compose_env import compose_environment, write_environment

ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "ai-database-analyst-stage9-gate"
REPORT_PATH = ROOT / "reports" / "test-results" / "stage-9-compose.json"


def _run(
    arguments: list[str],
    *,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _compose(
    env_file: Path, *arguments: str, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "--project-name",
            PROJECT_NAME,
            *arguments,
        ],
        timeout=timeout,
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    # The smoke gate constructs this URL from its own fixed localhost endpoint.
    with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310
        result = json.loads(response.read().decode("utf-8"))
        return result, {key.casefold(): value for key, value in response.headers.items()}


def _service_image(env_file: Path, service: str) -> str:
    output = _compose(env_file, "images", "--quiet", service).stdout.strip().splitlines()
    if not output:
        raise RuntimeError(f"Compose did not resolve the {service} image")
    return output[0]


def _assert_non_root_image(image: str, secrets_to_hide: tuple[str, ...]) -> str:
    config = json.loads(_run(["docker", "image", "inspect", image]).stdout)[0]
    user = str(config["Config"].get("User") or "")
    if user in {"", "0", "root", "0:0"}:
        raise RuntimeError("Application image does not declare a non-root user")
    serialized = json.dumps(config, sort_keys=True)
    history = _run(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", image]).stdout
    if any(secret in serialized or secret in history for secret in secrets_to_hide):
        raise RuntimeError("A generated credential reached image configuration or history")
    return user


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_diagnostic(value: str, secrets_to_hide: tuple[str, ...]) -> str:
    sanitized = value
    for secret in secrets_to_hide:
        sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(
        r"postgresql(?:\+psycopg)?://[^\s]+",
        "[REDACTED_DATABASE_URL]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized[-2_000:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the verified stack and volume")
    parser.add_argument(
        "--cached-build", action="store_true", help="Permit Docker layer cache for a faster rerun"
    )
    args = parser.parse_args()
    checked_at = datetime.now(UTC).isoformat()
    if _run(["docker", "info"], timeout=30, check=False).returncode != 0:
        _write_report(
            {
                "report_version": "stage-9-compose-v1",
                "checked_at": checked_at,
                "stage_gate_passed": False,
                "blocker": "Docker daemon unavailable.",
            }
        )
        return 2

    with tempfile.TemporaryDirectory(prefix="stage9-compose-") as temp_directory:
        env_file = Path(temp_directory) / ".env.compose"
        environment = compose_environment()
        environment["API_PUBLISHED_PORT"] = str(_free_port())
        environment["FRONTEND_PUBLISHED_PORT"] = str(_free_port())
        write_environment(env_file, environment)
        api_port = int(environment["API_PUBLISHED_PORT"])
        frontend_port = int(environment["FRONTEND_PUBLISHED_PORT"])
        generated_secrets = tuple(
            value
            for key, value in environment.items()
            if key.endswith("PASSWORD") or key.endswith("TOKEN")
        )
        passed = False
        report: dict[str, Any] = {
            "report_version": "stage-9-compose-v1",
            "checked_at": checked_at,
            "project_name": PROJECT_NAME,
            "build_without_cache": not args.cached_build,
            "stage_gate_passed": False,
            "blocker": None,
        }
        phase = "clean_previous_stack"
        try:
            _compose(env_file, "down", "--volumes", "--remove-orphans", timeout=120)
            phase = "build_images"
            build_arguments = ["build"]
            if not args.cached_build:
                build_arguments.append("--no-cache")
            build_arguments.extend(("api", "frontend"))
            _compose(env_file, *build_arguments, timeout=900)
            phase = "start_stack"
            _compose(
                env_file,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "240",
                timeout=300,
            )

            phase = "health_contracts"
            health, _ = _json_request(f"http://127.0.0.1:{api_port}/api/v1/health")
            if health != {"status": "healthy", "api_version": "v1"}:
                raise RuntimeError("API health contract is not healthy")
            # The smoke gate constructs this URL from its own fixed localhost endpoint.
            with urllib.request.urlopen(  # nosec B310
                f"http://127.0.0.1:{frontend_port}/_stcore/health", timeout=15
            ) as frontend_health:
                if frontend_health.read().decode("utf-8").strip().casefold() != "ok":
                    raise RuntimeError("Frontend health contract is not healthy")

            phase = "end_to_end_query"
            request_id = str(uuid4())
            question = "Berapa jumlah pelanggan?"
            query, query_headers = _json_request(
                f"http://127.0.0.1:{api_port}/api/v1/query",
                method="POST",
                payload={"question": question},
                headers={"X-Request-ID": request_id},
            )
            if query.get("status") != "success" or query.get("request_id") != request_id:
                raise RuntimeError("End-to-end query or request correlation failed")
            if query_headers.get("x-request-id") != request_id:
                raise RuntimeError("API response did not preserve the request correlation ID")
            metrics, _ = _json_request(
                f"http://127.0.0.1:{api_port}/api/v1/operations/metrics",
                headers={"X-Evaluation-Token": environment["EVALUATION_API_TOKEN"]},
            )
            if int(metrics.get("analytics_requests_total", 0)) < 1:
                raise RuntimeError("Operational metrics did not record the analytics request")
            if float(metrics.get("success_rate", 0)) <= 0:
                raise RuntimeError("Operational metrics did not expose the success rate")
            if metrics.get("input_tokens_total") is not None:
                raise RuntimeError("Fake-provider token usage must remain explicitly unavailable")

            phase = "log_privacy_and_correlation"
            logs = _compose(env_file, "logs", "--no-color", "api", timeout=60).stdout
            if request_id not in logs:
                raise RuntimeError("Structured logs cannot be correlated by request ID")
            if question in logs or "postgresql+psycopg://" in logs:
                raise RuntimeError("API logs contain a raw question or connection URL")
            if any(secret in logs for secret in generated_secrets):
                raise RuntimeError("API logs contain a generated credential")
            correlated_events = []
            for line in logs.splitlines():
                payload_start = line.find("{")
                if payload_start < 0:
                    continue
                try:
                    payload = json.loads(line[payload_start:])
                except json.JSONDecodeError:
                    continue
                if payload.get("request_id") == request_id:
                    correlated_events.append(payload)
            required_fields = {
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
            }
            if not any(required_fields <= set(event) for event in correlated_events):
                raise RuntimeError("Correlated analytics log is missing required fields")

            phase = "image_identity_and_secret_history"
            api_image = _service_image(env_file, "api")
            frontend_image = _service_image(env_file, "frontend")
            api_user = _assert_non_root_image(api_image, generated_secrets)
            frontend_user = _assert_non_root_image(frontend_image, generated_secrets)
            report.update(
                {
                    "stage_gate_passed": True,
                    "services_healthy": ["db", "api", "frontend"],
                    "bootstrap_completed": True,
                    "request_id_propagated": True,
                    "structured_log_fields_verified": True,
                    "sensitive_log_payload_detected": False,
                    "image_secret_detected": False,
                    "api_image_user": api_user,
                    "frontend_image_user": frontend_user,
                    "operational_metrics_verified": True,
                }
            )
            passed = True
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            report["blocker"] = f"Compose gate failed: {type(exc).__name__}"
            report["blocker_phase"] = phase
            diagnostic_parts = [str(exc)]
            if isinstance(exc, subprocess.CalledProcessError):
                diagnostic_parts.extend((exc.stdout or "", exc.stderr or ""))
            diagnostic = _safe_diagnostic("\n".join(diagnostic_parts), generated_secrets)
            report["safe_diagnostic"] = diagnostic
            print(f"{report['blocker']} during {phase}: {diagnostic}", file=sys.stderr)
        finally:
            if not args.keep:
                cleanup = _compose(
                    env_file,
                    "down",
                    "--volumes",
                    "--remove-orphans",
                    timeout=180,
                )
                report["project_resources_removed"] = cleanup.returncode == 0
            else:
                report["project_resources_removed"] = False
            _write_report(report)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
