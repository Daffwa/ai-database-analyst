"""Tests for stable, client-safe domain errors."""

import pytest

from backend.core.errors import (
    AppError,
    ConfigurationError,
    DatabaseUnavailableError,
    DatasetVerificationError,
    ErrorCode,
    EvaluationBaselineError,
    ExternalServiceError,
    InvalidRequestError,
    LLMOutputError,
    LLMProviderError,
    LLMTimeoutError,
    QueryExecutionError,
    QueryTimeoutError,
    ResultTooLargeError,
    SchemaInspectionError,
    SecurityPolicyError,
    SemanticLayerError,
    SQLValidationError,
)


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (AppError(), ErrorCode.INTERNAL_ERROR),
        (InvalidRequestError(), ErrorCode.INVALID_REQUEST),
        (ConfigurationError(), ErrorCode.CONFIGURATION_ERROR),
        (ExternalServiceError(), ErrorCode.EXTERNAL_SERVICE_ERROR),
        (DatasetVerificationError(), ErrorCode.DATASET_VERIFICATION_ERROR),
        (DatabaseUnavailableError(), ErrorCode.DATABASE_UNAVAILABLE),
        (QueryExecutionError(), ErrorCode.QUERY_EXECUTION_FAILED),
        (ResultTooLargeError(), ErrorCode.RESULT_TOO_LARGE),
        (SchemaInspectionError(), ErrorCode.SCHEMA_INSPECTION_FAILED),
        (LLMTimeoutError(), ErrorCode.LLM_TIMEOUT),
        (LLMProviderError(), ErrorCode.LLM_PROVIDER_ERROR),
        (LLMOutputError(), ErrorCode.LLM_OUTPUT_INVALID),
        (EvaluationBaselineError(), ErrorCode.EVALUATION_BASELINE_MISMATCH),
        (QueryTimeoutError(), ErrorCode.QUERY_TIMEOUT),
        (SQLValidationError(), ErrorCode.SQL_VALIDATION_FAILED),
        (SemanticLayerError(), ErrorCode.SEMANTIC_LAYER_INVALID),
        (SecurityPolicyError(), ErrorCode.SECURITY_POLICY_VIOLATION),
    ],
)
def test_error_subclasses_use_stable_default_codes(
    error: AppError,
    expected_code: ErrorCode,
) -> None:
    assert error.code is expected_code
    assert str(error) == error.public_message


def test_public_payload_contains_only_explicit_safe_fields() -> None:
    error = InvalidRequestError(
        "Question must not be empty.",
        details={"field": "question"},
    )

    assert error.to_public_dict(request_id="request-123") == {
        "error_code": "INVALID_REQUEST",
        "message": "Question must not be empty.",
        "request_id": "request-123",
        "details": {"field": "question"},
    }


def test_public_payload_omits_empty_optional_fields() -> None:
    payload = AppError().to_public_dict()

    assert "request_id" not in payload
    assert "details" not in payload


def test_error_can_override_code_without_changing_hierarchy() -> None:
    error = AppError("Blocked.", code=ErrorCode.SECURITY_POLICY_VIOLATION)

    assert error.code is ErrorCode.SECURITY_POLICY_VIOLATION
