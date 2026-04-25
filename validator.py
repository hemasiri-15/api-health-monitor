"""
=============================================================================
validator.py - Response Validation Module
=============================================================================
Responsibility:
    - Check that an API response has the expected HTTP status code.
    - Verify that required JSON keys are present in the response body.
    - Assert that specific key-value pairs match expected values.
    - Return a structured ValidationResult indicating pass/fail + reasons.
=============================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class to hold validation outcome
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """
    Encapsulates the outcome of a single validation run.

    Attributes:
        passed:   True if ALL validation checks passed, False otherwise.
        errors:   List of human-readable strings describing each failure.
    """
    passed: bool = True
    errors: List[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        """Mark validation as failed and record the reason."""
        self.passed = False
        self.errors.append(reason)

    def summary(self) -> str:
        """Return a short one-line summary of the result."""
        if self.passed:
            return "Validation PASSED"
        return "Validation FAILED: " + " | ".join(self.errors)


# ---------------------------------------------------------------------------
# Core validation functions
# ---------------------------------------------------------------------------

def validate_status_code(actual: int, expected: int) -> ValidationResult:
    """
    Check that the HTTP response code matches what we expect.

    Args:
        actual:   HTTP status code received from the server.
        expected: HTTP status code defined in config.yaml.

    Returns:
        ValidationResult
    """
    result = ValidationResult()
    if actual != expected:
        result.fail(
            f"HTTP status mismatch: expected {expected}, got {actual}"
        )
    return result


def validate_required_keys(
    response_json: Any,
    required_keys: List[str]
) -> ValidationResult:
    """
    Ensure every key in required_keys exists somewhere in the response JSON.

    Handles both dict responses (single object) and list responses
    (e.g., RestCountries returns a list — we check the first element).

    Args:
        response_json: Parsed JSON (dict or list).
        required_keys: Keys that must be present.

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    if not required_keys:
        return result  # Nothing to validate; pass automatically

    # If the top-level response is a list, inspect the first element
    target = response_json
    if isinstance(response_json, list):
        if len(response_json) == 0:
            result.fail("Response is an empty list; cannot validate keys")
            return result
        target = response_json[0]

    # target must be a dict for key validation
    if not isinstance(target, dict):
        result.fail(
            f"Expected JSON object for key validation, got {type(target).__name__}"
        )
        return result

    # Check each required key
    for key in required_keys:
        if key not in target:
            result.fail(f"Missing required key: '{key}'")

    return result


def validate_expected_values(
    response_json: Any,
    expected_values: Dict[str, Any]
) -> ValidationResult:
    """
    Assert that specific key-value pairs in the response match configured values.

    Args:
        response_json:   Parsed JSON (dict or list).
        expected_values: Dict of {key: expected_value} pairs from config.yaml.

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    if not expected_values:
        return result  # No assertions configured; pass automatically

    # Unwrap list responses
    target = response_json
    if isinstance(response_json, list):
        if len(response_json) == 0:
            result.fail("Response is empty list; cannot assert values")
            return result
        target = response_json[0]

    if not isinstance(target, dict):
        result.fail(
            f"Cannot assert values on non-dict type: {type(target).__name__}"
        )
        return result

    for key, expected_val in expected_values.items():
        actual_val = target.get(key)
        if actual_val != expected_val:
            result.fail(
                f"Value mismatch for '{key}': expected {expected_val!r}, got {actual_val!r}"
            )

    return result


# ---------------------------------------------------------------------------
# Composite validator — runs all checks and merges results
# ---------------------------------------------------------------------------

def run_all_validations(
    actual_status: int,
    response_json: Optional[Any],
    validation_config: Dict[str, Any],
    expected_status: int
) -> ValidationResult:
    """
    Run all configured validation checks for one endpoint check cycle.

    This is the main entry point called by monitor.py after each HTTP request.

    Args:
        actual_status:     HTTP status code we received.
        response_json:     Parsed JSON body (or None if parsing failed).
        validation_config: Dict from config.yaml under 'validation:' key.
        expected_status:   Expected HTTP status code from config.yaml.

    Returns:
        A merged ValidationResult combining all sub-checks.
    """
    final = ValidationResult()

    # --- Step 1: Check HTTP status code ---
    status_result = validate_status_code(actual_status, expected_status)
    if not status_result.passed:
        for err in status_result.errors:
            final.fail(err)

    # If we can't parse JSON, further validation is impossible
    if response_json is None:
        final.fail("Response body is not valid JSON; skipping key/value checks")
        return final

    # --- Step 2: Check required keys ---
    required_keys = validation_config.get("required_keys", [])
    key_result = validate_required_keys(response_json, required_keys)
    if not key_result.passed:
        for err in key_result.errors:
            final.fail(err)

    # --- Step 3: Check expected values ---
    expected_values = validation_config.get("expected_values", {})
    val_result = validate_expected_values(response_json, expected_values)
    if not val_result.passed:
        for err in val_result.errors:
            final.fail(err)

    if final.passed:
        logger.debug("All validations passed.")
    else:
        logger.warning("Validation failures: %s", final.errors)

    return final
