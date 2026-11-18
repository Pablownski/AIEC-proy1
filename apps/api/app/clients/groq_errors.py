"""Classify provider failures using closed labels; never return raw error fields."""

import re

from groq import APIStatusError

ERROR_CODES = {
    "invalid_request_error",
    "invalid_parameter",
    "invalid_value",
    "unsupported_parameter",
    "unsupported_value",
    "tool_use_failed",
    "tool_call_validation_error",
    "json_validate_failed",
    "context_length_exceeded",
    "model_not_found",
    "model_decommissioned",
    "server_error",
}
ERROR_TYPES = {"invalid_request_error", "server_error", "authentication_error", "permission_error"}
PARAMETERS = {
    "messages",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "reasoning_effort",
    "reasoning_format",
    "include_reasoning",
    "max_completion_tokens",
    "response_format",
    "model",
}
FIELDS = {"index", "reasoning", "reasoning_content", "tool_call_id", "arguments", "name", "content"}


def classify_provider_error(exc: APIStatusError) -> dict[str, str | bool]:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    error = error if isinstance(error, dict) else {}
    raw_code, raw_type = error.get("code"), error.get("type")
    code = raw_code if isinstance(raw_code, str) and raw_code in ERROR_CODES else "unknown"
    kind = raw_type if isinstance(raw_type, str) and raw_type in ERROR_TYPES else "unknown"
    raw_param, raw_message = error.get("param"), error.get("message")
    param = raw_param if isinstance(raw_param, str) else ""
    message = raw_message if isinstance(raw_message, str) else ""
    # Analyze only a bounded prefix. None of these strings are returned or logged.
    param, message = param[:512], message[:2048]
    parameter = "unknown"
    field = "unknown"
    root = re.split(r"[.\[]", param)[0]
    if root in PARAMETERS:
        parameter = root
        if root == "messages" and "tool_calls" in param:
            parameter = "messages.tool_calls"
        leaf = re.split(r"[.\[\]]", param)[-1]
        if leaf in FIELDS:
            field = leaf
    # Some Groq errors only supply a message with a structural field path.
    if re.search(r"\bmessages(?:\.\d+|\[\d+\])?\.tool_calls\b", message):
        parameter = "messages.tool_calls"
    unsupported = re.search(r"property ['\"]([a-z_]+)['\"] is (?:unsupported|not allowed)", message)
    if unsupported and unsupported[1] in FIELDS:
        field = unsupported[1]
    has_failed_generation = "failed_generation" in error
    if code in {"tool_use_failed", "tool_call_validation_error"} or has_failed_generation:
        category = "tool_generation"
    elif code == "context_length_exceeded":
        category = "context_length"
    elif code == "json_validate_failed":
        category = "output_generation"
    elif code in {"unsupported_parameter", "unsupported_value"}:
        category = "unsupported_parameter"
    elif (
        code in {"invalid_request_error", "invalid_parameter", "invalid_value"}
        or kind == "invalid_request_error"
    ):
        category = "request_validation"
    else:
        category = "bad_request_unknown" if exc.status_code == 400 else "provider_failure"
    return {
        "error_class": category,
        "provider_code": code,
        "provider_type": kind,
        "parameter": parameter,
        "field": field,
        "has_failed_generation": has_failed_generation,
    }
