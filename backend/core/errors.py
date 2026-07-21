"""Stable domain errors that do not depend on a web framework."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Public error identifiers shared by services and future API adapters."""

    INVALID_REQUEST = "INVALID_REQUEST"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    DATASET_VERIFICATION_ERROR = "DATASET_VERIFICATION_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    QUERY_EXECUTION_FAILED = "QUERY_EXECUTION_FAILED"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
    SCHEMA_INSPECTION_FAILED = "SCHEMA_INSPECTION_FAILED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"
    EVALUATION_BASELINE_MISMATCH = "EVALUATION_BASELINE_MISMATCH"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    SQL_VALIDATION_FAILED = "SQL_VALIDATION_FAILED"
    SEMANTIC_LAYER_INVALID = "SEMANTIC_LAYER_INVALID"
    SECURITY_POLICY_VIOLATION = "SECURITY_POLICY_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base error with a safe public representation.

    Internal exceptions may be attached as a Python cause, but callers should
    expose only :meth:`to_public_dict` to users.
    """

    default_code = ErrorCode.INTERNAL_ERROR
    default_public_message = "The request could not be completed."

    def __init__(
        self,
        public_message: str | None = None,
        *,
        code: ErrorCode | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.public_message = public_message or self.default_public_message
        self.details = dict(details or {})
        super().__init__(self.public_message)

    def to_public_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        """Return a stable client-safe payload."""

        payload: dict[str, Any] = {
            "error_code": self.code.value,
            "message": self.public_message,
        }
        if request_id:
            payload["request_id"] = request_id
        if self.details:
            payload["details"] = self.details
        return payload


class InvalidRequestError(AppError):
    """Raised when user input does not satisfy the public request contract."""

    default_code = ErrorCode.INVALID_REQUEST
    default_public_message = "The request is invalid."


class ConfigurationError(AppError):
    """Raised when required runtime configuration is invalid or unavailable."""

    default_code = ErrorCode.CONFIGURATION_ERROR
    default_public_message = "The application is not configured for this operation."


class ExternalServiceError(AppError):
    """Raised for sanitized failures from an external dependency."""

    default_code = ErrorCode.EXTERNAL_SERVICE_ERROR
    default_public_message = "A required service is temporarily unavailable."


class SecurityPolicyError(AppError):
    """Raised when a request violates a deterministic security policy."""

    default_code = ErrorCode.SECURITY_POLICY_VIOLATION
    default_public_message = "The request is not allowed by the security policy."


class DatasetVerificationError(AppError):
    """Raised when a pinned dataset artifact cannot be verified."""

    default_code = ErrorCode.DATASET_VERIFICATION_ERROR
    default_public_message = "The dataset could not be downloaded or verified."


class DatabaseUnavailableError(AppError):
    """Raised when the configured analytics database cannot be opened safely."""

    default_code = ErrorCode.DATABASE_UNAVAILABLE
    default_public_message = "The analytics database is unavailable."


class QueryExecutionError(AppError):
    """Raised when a read-only query cannot be executed safely."""

    default_code = ErrorCode.QUERY_EXECUTION_FAILED
    default_public_message = "The query could not be executed."


class ResultTooLargeError(AppError):
    """Raised when a result exceeds a configured response budget."""

    default_code = ErrorCode.RESULT_TOO_LARGE
    default_public_message = "The query result exceeds the configured limit."


class SchemaInspectionError(AppError):
    """Raised when database metadata cannot be normalized safely."""

    default_code = ErrorCode.SCHEMA_INSPECTION_FAILED
    default_public_message = "The database schema could not be inspected."


class LLMTimeoutError(AppError):
    """Raised when the configured LLM adapter exceeds its time budget."""

    default_code = ErrorCode.LLM_TIMEOUT
    default_public_message = "The language model request timed out."


class LLMProviderError(AppError):
    """Raised when a provider adapter fails without exposing provider details."""

    default_code = ErrorCode.LLM_PROVIDER_ERROR
    default_public_message = "The language model service is unavailable."


class LLMOutputError(AppError):
    """Raised when model output does not satisfy the structured contract."""

    default_code = ErrorCode.LLM_OUTPUT_INVALID
    default_public_message = "The language model returned an invalid response."


class EvaluationBaselineError(AppError):
    """Raised when a closed demo result no longer matches its trusted baseline."""

    default_code = ErrorCode.EVALUATION_BASELINE_MISMATCH
    default_public_message = "The verified demo baseline did not match."


class QueryTimeoutError(AppError):
    """Raised when database execution exceeds its configured time budget."""

    default_code = ErrorCode.QUERY_TIMEOUT
    default_public_message = "The query exceeded the execution time limit."


class SQLValidationError(AppError):
    """Raised when SQL cannot pass the deterministic security policy."""

    default_code = ErrorCode.SQL_VALIDATION_FAILED
    default_public_message = "The generated SQL did not pass security validation."


class SemanticLayerError(AppError):
    """Raised when versioned semantic definitions fail safe validation."""

    default_code = ErrorCode.SEMANTIC_LAYER_INVALID
    default_public_message = "The semantic layer is invalid or incompatible."
