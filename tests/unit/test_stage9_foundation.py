"""Static Stage 9 Docker, CI, security, and operations contracts."""

from pathlib import Path

import yaml

from scripts.evaluate_stage9 import main as evaluate_stage9
from scripts.generate_compose_env import compose_environment, write_environment

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfiles_pin_base_and_run_as_non_root() -> None:
    for filename in ("Dockerfile.api", "Dockerfile.frontend"):
        source = (ROOT / filename).read_text(encoding="utf-8")
        assert "python:3.12.13-slim-bookworm@sha256:" in source
        assert "USER 10001:10001" in source
        assert "HEALTHCHECK" in source
        assert "COPY ." not in source
        assert ".env" not in source
    api_source = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    frontend_source = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "COPY --chown=10001:10001 scripts ./scripts" not in api_source
    assert "scripts/bootstrap_postgres.py" in api_source
    assert "data/evaluation/stage-7-v1.jsonl" in api_source
    assert "PYTHONPATH=/app" in frontend_source


def test_compose_has_ready_services_runtime_secrets_and_named_volume() -> None:
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(source)
    assert set(compose["services"]) == {"db", "bootstrap", "api", "frontend"}
    assert "postgres-data" in compose["volumes"]
    assert compose["services"]["api"]["read_only"] is True
    assert compose["services"]["frontend"]["read_only"] is True
    assert compose["services"]["api"]["depends_on"]["bootstrap"]["condition"] == (
        "service_completed_successfully"
    )
    assert "${POSTGRES_ADMIN_PASSWORD:?" in source
    assert "change-me" not in source


def test_compose_environment_generation_is_exclusive_and_secret_values_are_not_fixed(
    tmp_path: Path,
) -> None:
    first = compose_environment()
    second = compose_environment()
    secret_keys = {key for key in first if key.endswith("PASSWORD") or key.endswith("TOKEN")}
    assert all(first[key] and first[key] != second[key] for key in secret_keys)
    target = tmp_path / ".env.compose"
    write_environment(target, first)
    assert set(
        line.split("=", 1)[0] for line in target.read_text(encoding="utf-8").splitlines()
    ) == set(first)
    try:
        write_environment(target, second)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Compose credentials must not be overwritten implicitly")


def test_workflows_use_minimum_permissions_pinned_actions_and_no_secrets() -> None:
    workflow_directory = ROOT / ".github" / "workflows"
    workflows = {
        path.name: path.read_text(encoding="utf-8") for path in workflow_directory.glob("*.yml")
    }
    assert set(workflows) == {"ci.yml", "security.yml", "evaluation.yml", "docker.yml"}
    for source in workflows.values():
        assert "contents: read" in source
        assert "persist-credentials: false" in source
        assert "secrets." not in source
        assert "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd" in source
    assert "security-events: write" in workflows["security.yml"]
    assert "pull_request:" in workflows["security.yml"]
    assert "Image publication is intentionally absent" in workflows["docker.yml"]


def test_secret_scan_excludes_only_known_local_environment_files() -> None:
    source = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert "\\.env$" in source
    assert "\\.env\\.compose$" in source
    assert "example" not in source


def test_stage9_readiness_evaluator_records_implementation_state() -> None:
    assert evaluate_stage9() == 0
    report = (ROOT / "reports" / "evaluation" / "stage-9-readiness.json").read_text(
        encoding="utf-8"
    )
    assert '"implementation_gate_passed": true' in report
