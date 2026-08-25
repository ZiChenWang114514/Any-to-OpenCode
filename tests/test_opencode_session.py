import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "opencode_session.py"
SPEC = importlib.util.spec_from_file_location("opencode_session", SCRIPT_PATH)
assert SPEC and SPEC.loader
opencode_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(opencode_session)


class ParseAssistantResponseTests(unittest.TestCase):
    def test_returns_text_and_actual_model(self) -> None:
        response = {
            "info": {"modelID": "ox-alpha-free"},
            "parts": [
                {"type": "text", "text": "first"},
                {"type": "tool", "text": "ignored"},
                {"type": "text", "text": "second"},
            ],
        }

        reply, actual_model = opencode_session.parse_assistant_response(
            response, "session-test", "ox-alpha-free",
        )

        self.assertEqual(reply, "first\nsecond")
        self.assertEqual(actual_model, "ox-alpha-free")

    def test_provider_error_is_structured_and_sanitized(self) -> None:
        response = {
            "info": {
                "modelID": "ox-alpha-free",
                "error": {
                    "name": "APIError",
                    "data": {
                        "message": "Upstream request failed: Endpoint is unavailable.",
                        "statusCode": 503,
                        "isRetryable": True,
                        "responseHeaders": {"authorization": "secret"},
                        "responseBody": "private payload",
                    },
                },
            },
            "parts": [],
        }

        with self.assertRaises(opencode_session.OpenCodeAssistantError) as caught:
            opencode_session.parse_assistant_response(
                response, "session-test", "ox-alpha-free",
            )

        self.assertEqual(caught.exception.details, {
            "session_id": "session-test",
            "name": "APIError",
            "message": "Upstream request failed: Endpoint is unavailable.",
            "status_code": 503,
            "retryable": True,
        })

    def test_empty_text_is_an_error(self) -> None:
        response = {"info": {"modelID": "ox-alpha-free"}, "parts": []}

        with self.assertRaises(opencode_session.OpenCodeAssistantError) as caught:
            opencode_session.parse_assistant_response(
                response, "session-empty", "ox-alpha-free",
            )

        self.assertEqual(caught.exception.details["name"], "EmptyAssistantReply")
        self.assertEqual(caught.exception.details["session_id"], "session-empty")

    def test_model_mismatch_remains_an_error(self) -> None:
        response = {
            "info": {"modelID": "different-model"},
            "parts": [{"type": "text", "text": "hello"}],
        }

        with self.assertRaisesRegex(RuntimeError, "Requested model"):
            opencode_session.parse_assistant_response(
                response, "session-test", "ox-alpha-free",
            )


if __name__ == "__main__":
    unittest.main()
