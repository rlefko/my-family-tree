"""Domain exceptions. Raised by services, caught by API exception handlers."""

from __future__ import annotations


class MFTError(Exception):
    """Base class for application-specific exceptions."""

    code: str = "mft_error"
    status_code: int = 500


class NotFoundError(MFTError):
    code = "not_found"
    status_code = 404


class ConflictError(MFTError):
    """Generic 409. Use ConflictDetectedError for genealogical conflicts."""

    code = "conflict"
    status_code = 409


class ValidationError(MFTError):
    code = "validation_error"
    status_code = 422


class ProposalRequiredError(MFTError):
    """Raised when an MCP write tool tries to commit instead of propose."""

    code = "proposal_required"
    status_code = 400


class CapabilityDeniedError(MFTError):
    """Raised when an agent tool call exceeds its declared capabilities."""

    code = "capability_denied"
    status_code = 403


class BudgetExceededError(MFTError):
    """Token / tool-call / wall-clock budget exhausted."""

    code = "budget_exceeded"
    status_code = 429


class ExtractionError(MFTError):
    """Document extraction failed in a non-retryable way."""

    code = "extraction_failed"
    status_code = 500


class StorageError(MFTError):
    code = "storage_error"
    status_code = 500


class RequestTooLargeError(MFTError):
    """Raised when an upload exceeds the configured byte limit."""

    code = "request_too_large"
    status_code = 413


class LLMProviderError(MFTError):
    code = "llm_provider_error"
    status_code = 502


class ExternalProviderError(MFTError):
    """A web search, genealogy, or fetch provider failed or refused the request."""

    code = "external_provider_error"
    status_code = 502


class UnsafeUrlError(ExternalProviderError):
    """A URL targets a private network or otherwise blocked address."""

    code = "unsafe_url"
    status_code = 400
