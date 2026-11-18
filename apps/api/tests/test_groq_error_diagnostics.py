import json
import traceback

import httpx
import pytest
from groq import APIStatusError

from app.clients.groq_client import GroqClient, GroqClientError
from app.clients.groq_errors import classify_provider_error
from app.core.config import Settings
from tests.test_groq_client import sdk as sdk


def failure(body, status=400):
    return APIStatusError(
        "private-error-message",
        response=httpx.Response(status, request=httpx.Request("POST", "https://api.groq.test")),
        body=body,
    )


@pytest.mark.parametrize(
    "code,category",
    [
        ("tool_use_failed", "tool_generation"),
        ("tool_call_validation_error", "tool_generation"),
        ("context_length_exceeded", "context_length"),
        ("unsupported_parameter", "unsupported_parameter"),
        ("unsupported_value", "unsupported_parameter"),
        ("json_validate_failed", "output_generation"),
        ("invalid_request_error", "request_validation"),
        ("invalid_parameter", "request_validation"),
        ("invalid_value", "request_validation"),
        ("private-code", "bad_request_unknown"),
    ],
)
def test_known_codes_are_classified_without_echoing_unknown_codes(code, category):
    details = classify_provider_error(failure({"error": {"code": code}}))
    assert details["error_class"] == category
    assert "private" not in json.dumps(details)


@pytest.mark.parametrize("body", [None, "private-body", [], {"error": []}, {"error": None}])
def test_malformed_or_absent_body_remains_unknown(body):
    assert classify_provider_error(failure(body))["error_class"] == "bad_request_unknown"
    assert classify_provider_error(failure(body, 500))["error_class"] == "provider_failure"


@pytest.mark.parametrize(
    "param,parameter,field",
    [
        ("messages.3.tool_calls.0.index", "messages.tool_calls", "index"),
        ("messages[3].tool_calls[0].function.arguments", "messages.tool_calls", "arguments"),
        ("reasoning_effort", "reasoning_effort", "unknown"),
        ("response_format", "response_format", "unknown"),
        ("private-param", "unknown", "unknown"),
        ({"private-param": "secret"}, "unknown", "unknown"),
    ],
)
def test_parameter_paths_are_reduced_to_closed_labels(param, parameter, field):
    details = classify_provider_error(
        failure(
            {
                "error": {
                    "code": "invalid_request_error",
                    "param": param,
                }
            }
        )
    )
    assert details["parameter"] == parameter and details["field"] == field
    assert "private" not in json.dumps(details)


def test_message_only_field_hint_and_failed_generation_never_expose_content():
    details = classify_provider_error(
        failure(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        "messages[3].tool_calls[0]: property 'index' is unsupported private-detail"
                    ),
                    "failed_generation": {"system_prompt": "private-instructions"},
                }
            }
        )
    )
    assert details["field"] == "index" and details["parameter"] == "messages.tool_calls"
    assert details["error_class"] == "tool_generation"
    assert details["has_failed_generation"] is True
    assert "private" not in json.dumps(details)


async def test_rejected_parameters_do_not_retry_or_leak_provider_text(sdk, caplog):
    messages = [{"role": "user", "content": "private-user-content"}]
    sdk[1].chat.completions.create.side_effect = failure(
        {
            "error": {
                "code": "unsupported_parameter",
                "type": "private-type",
                "param": "reasoning_effort",
                "message": "private-error-body",
                "request_headers": {"authorization": "test-key"},
            }
        }
    )
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        with pytest.raises(GroqClientError) as caught:
            await client.complete(messages)
    sdk[1].chat.completions.create.assert_awaited_once()
    assert caught.value.code == "provider" and caught.value.status_code == 400
    assert "private" not in "".join(traceback.format_exception(caught.value))
    assert "private" not in caplog.text and "test-key" not in caplog.text
    event = next(json.loads(r.getMessage()) for r in caplog.records if r.name == "uvicorn.error")
    assert event["parameter"] == "reasoning_effort" and event["provider_type"] == "unknown"
    assert event["will_retry"] is False
