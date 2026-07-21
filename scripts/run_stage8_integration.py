"""Run the actual Tahap 8 PostgreSQL gate in one ephemeral official container."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from backend.data.chinook import CHINOOK_POSTGRESQL_ARTIFACT, ensure_artifact
from backend.data.postgres import (
    ANALYTICS_READONLY,
    METADATA_USER,
    MIGRATION_USER,
    application_database_urls,
    bootstrap_postgresql,
)
from backend.metadata.migrations import run_metadata_migration
from backend.services.schema_service import load_schema_snapshot

ROOT = Path(__file__).resolve().parents[1]
CONTAINER_NAME = "ai-database-analyst-stage8-postgres"
IMAGE = "postgres:17.10-alpine3.24"
PORT = 55432
REPORT_PATH = ROOT / "reports" / "test-results" / "stage-8-postgres.json"
IMAGE_PULL_TIMEOUT_SECONDS = 180


def _docker(
    *args: str,
    check: bool = True,
    timeout_seconds: int = 30,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        env=environment,
    )


def _wait_for_postgres(admin_url: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(admin_url, connect_timeout=2):
                return
        except psycopg.Error:
            time.sleep(1)
    raise RuntimeError("PostgreSQL container did not become ready within 90 seconds")


def _write_report(*, verified: bool, blocker: str | None, test_return_code: int | None) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "report_version": "stage-8-postgres-v1",
                "checked_at": datetime.now(UTC).isoformat(),
                "container_image": IMAGE,
                "postgresql_integration_verified": verified,
                "test_return_code": test_return_code,
                "blocker": blocker,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the test container running")
    args = parser.parse_args()
    try:
        daemon_ready = _docker("info", check=False).returncode == 0
    except subprocess.TimeoutExpired:
        daemon_ready = False
    if not daemon_ready:
        _write_report(
            verified=False,
            blocker="Docker daemon unavailable; PostgreSQL container tests were not run.",
            test_return_code=None,
        )
        print("Docker daemon is not available", file=sys.stderr)
        return 2

    _docker("rm", "-f", CONTAINER_NAME, check=False)
    _docker("pull", IMAGE, timeout_seconds=IMAGE_PULL_TIMEOUT_SECONDS)
    admin_password = secrets.token_urlsafe(24)
    role_passwords = {
        ANALYTICS_READONLY: secrets.token_urlsafe(24),
        METADATA_USER: secrets.token_urlsafe(24),
        MIGRATION_USER: secrets.token_urlsafe(24),
    }
    docker_environment = os.environ.copy()
    docker_environment["POSTGRES_PASSWORD"] = admin_password
    _docker(
        "run",
        "--name",
        CONTAINER_NAME,
        "--detach",
        "--publish",
        f"127.0.0.1:{PORT}:5432",
        "--env",
        "POSTGRES_PASSWORD",
        IMAGE,
        environment=docker_environment,
    )
    try:
        admin_url = f"postgresql://postgres:{admin_password}@127.0.0.1:{PORT}/postgres"
        sqlalchemy_admin_url = (
            f"postgresql+psycopg://postgres:{admin_password}@127.0.0.1:{PORT}/postgres"
        )
        _wait_for_postgres(admin_url)
        seed_path = ensure_artifact(ROOT / "data" / "raw", artifact=CHINOOK_POSTGRESQL_ARTIFACT)
        snapshot = load_schema_snapshot(
            ROOT / "data" / "schemas" / "chinook-postgresql-v1.4.5.json"
        )
        bootstrap_postgresql(
            sqlalchemy_admin_url,
            seed_sql_path=seed_path,
            logical_snapshot=snapshot,
            passwords=role_passwords,
        )
        analytics_url, metadata_url, migration_url = application_database_urls(
            sqlalchemy_admin_url,
            analytics_password=role_passwords[ANALYTICS_READONLY],
            metadata_password=role_passwords[METADATA_USER],
            migration_password=role_passwords[MIGRATION_USER],
        )
        run_metadata_migration(ROOT, migration_url)
        environment = os.environ.copy()
        environment.update(
            {
                "STAGE8_POSTGRES_ADMIN_URL": sqlalchemy_admin_url,
                "ANALYTICS_DATABASE_URL": analytics_url,
                "METADATA_DATABASE_URL": metadata_url,
                "METADATA_MIGRATION_DATABASE_URL": migration_url,
            }
        )
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--no-cov", "tests/postgres"],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        _write_report(
            verified=completed.returncode == 0,
            blocker=(None if completed.returncode == 0 else "PostgreSQL integration tests failed."),
            test_return_code=completed.returncode,
        )
        return completed.returncode
    finally:
        if not args.keep:
            _docker("rm", "-f", CONTAINER_NAME, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
