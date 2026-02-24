"""Shared utilities for stub implementations."""

from typing import Any


def stub_response(operation: str, message: str) -> dict[str, Any]:
    """Create a standard stub response with operation and message.

    Args:
        operation: The operation name being stubbed
        message: Description of the stub behavior

    Returns:
        A dict with stub=True, operation, and message keys
    """
    return {
        "stub": True,
        "operation": operation,
        "message": message,
    }
