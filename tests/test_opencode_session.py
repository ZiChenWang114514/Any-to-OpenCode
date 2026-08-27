import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "opencode_session.py"
SPEC = importlib.util.spec_from_file_location("opencode_session", SCRIPT_PATH)
assert SPEC and SPEC.loader
opencode_session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(opencode_session)
TEST_MODEL_ID = "muse-spark-1.2-contributor"


class ParseAssistantResponseTests(unittest.TestCase):
    def test_returns_text_and_actual_model(self) -> None:
        response = {
            "info": {"modelID": TEST_MODEL_ID},
            "parts": [
                {"type": "text", "text": "first"},
                {"type": "tool", "text": "ignored"},
                {"type": "text", "text": "second"},
            ],
        }

        reply, actual_model, actual_variant = opencode_session.parse_assistant_response(
            response, "session-test", TEST_MODEL_ID,
        )

        self.assertEqual(reply, "first\nsecond")
        self.assertEqual(actual_model, TEST_MODEL_ID)
        self.assertIsNone(actual_variant)

    def test_returns_actual_variant(self) -> None:
        response = {
            "info": {"modelID": TEST_MODEL_ID, "variant": "high"},
            "parts": [{"type": "text", "text": "done"}],
        }

        _, _, actual_variant = opencode_session.parse_assistant_response(
            response, "session-test", TEST_MODEL_ID,
        )

        self.assertEqual(actual_variant, "high")

    def test_provider_error_is_structured_and_sanitized(self) -> None:
        response = {
            "info": {
                "modelID": TEST_MODEL_ID,
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
                response, "session-test", TEST_MODEL_ID,
            )

        self.assertEqual(caught.exception.details, {
            "session_id": "session-test",
            "name": "APIError",
            "message": "Upstream request failed: Endpoint is unavailable.",
            "status_code": 503,
            "retryable": True,
        })

    def test_empty_text_is_an_error(self) -> None:
        response = {"info": {"modelID": TEST_MODEL_ID}, "parts": []}

        with self.assertRaises(opencode_session.OpenCodeAssistantError) as caught:
            opencode_session.parse_assistant_response(
                response, "session-empty", TEST_MODEL_ID,
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
                response, "session-test", TEST_MODEL_ID,
            )


class FreeModelDiscoveryTests(unittest.TestCase):
    def test_parses_active_zero_cost_models(self) -> None:
        output = """opencode/free-one
{
  "id": "free-one",
  "providerID": "opencode",
  "status": "active",
  "cost": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}}
}
opencode/paid-one
{
  "id": "paid-one",
  "providerID": "opencode",
  "status": "active",
  "cost": {"input": 1, "output": 2, "cache": {"read": 0, "write": 0}}
}
"""

        records = opencode_session.parse_verbose_models(output, "opencode")
        free = [record["id"] for record in records if opencode_session.is_zero_cost_model(record)]

        self.assertEqual(free, ["free-one"])

    def test_requires_all_advertised_costs_to_be_zero(self) -> None:
        record = {
            "status": "active",
            "cost": {"input": 0, "output": 0, "cache": {"read": 0.01, "write": 0}},
        }

        self.assertFalse(opencode_session.is_zero_cost_model(record))

    def test_failure_summary_omits_local_log_paths(self) -> None:
        error = RuntimeError(
            '{"error":"timed out","log_dir":"C:/private/temp",'
            '"test_session_deleted":true}'
        )

        summary = opencode_session.summarize_failure(error)

        self.assertEqual(summary, {"error": "timed out", "test_session_deleted": True})


if __name__ == "__main__":
    unittest.main()
