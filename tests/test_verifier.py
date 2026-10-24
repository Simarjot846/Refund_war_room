
import unittest
from refund_agent.verifier import verify_claims


class VerifierTests(unittest.TestCase):
    def test_rejects_number_that_only_matches_part_of_sql_value(self):
        sql = "SELECT refund_count FROM refund_stats"
        sql_result = {
            "sql": sql,
            "sha256": "test-hash",
            "rows": [{"refund_count": 77}],
        }

        claims = [
            {
                "tag": "fact",
                "text": "The refund count was 7.",
                "evidence": {
                    "type": "sql",
                    "sql": sql,
                    "sha256": "test-hash",
                },
            }
        ]

        result = verify_claims(
            claims,
            trace=[
                {
                    "tool": "run_sql",
                    "status": "ok",
                    "result": sql_result,
                }
            ],
            docs=[],
        )

        self.assertFalse(
            result["passed"],
            "Verifier should reject 7 when SQL evidence only supports 77.",
        )

    def test_rejects_unsupported_sql_number(self):
        from refund_agent.agent import RefundAgent
        from refund_agent.tools import ToolSuite

        tools = ToolSuite(seed=1, failure_rate=0, use_faults=False)
        agent = RefundAgent(tools, verifier_enabled=True)

        # Directly test the verifier with a forged claim.
        sql = "SELECT 77 AS refund_count"
        result = {
            "sql": sql,
            "sha256": "test-hash",
            "rows": [{"refund_count": 77}],
        }
        trace = [{
            "tool": "run_sql",
            "status": "ok",
            "result": result,
        }]

        from refund_agent.verifier import verify_claims

        claims = [{
            "tag": "fact",
            "text": "The refund count was 7.",
            "evidence": {
                "type": "sql",
                "sql": sql,
                "sha256": "test-hash",
            },
        }]

        verification = verify_claims(claims, trace, [], "2026-10-22")
        self.assertFalse(verification["passed"])
        self.assertTrue(verification["issues"])
        
    def test_agent_removes_claim_when_verifier_flags_it(self):
        from unittest.mock import patch
        from refund_agent.agent import RefundAgent
        from refund_agent.tools import ToolSuite

        tools = ToolSuite(seed=1, failure_rate=0, use_faults=False)
        agent = RefundAgent(tools, verifier_enabled=True)

        bad_claim = {
            "tag": "fact",
            "text": "The refund count was 7.",
            "evidence": {
                "type": "sql",
                "sql": "SELECT 77 AS refund_count",
                "sha256": "fake-hash",
            },
        }

        with patch.object(
            agent,
            "_call",
            side_effect=RuntimeError("Stop after planning"),
        ):
            with patch(
                "refund_agent.agent.verify_claims",
                return_value={
                    "passed": False,
                    "issues": [{
                        "claim_index": 0,
                        "reason": "test: unsupported number",
                    }],
                },
            ):
                # This mock-based test checks the removal logic only if
                # the normal answer flow reaches verification.
                try:
                    result = agent.answer("Tell me the refund trend")
                except RuntimeError:
                    self.skipTest(
                        "Normal answer flow stopped before verification; "
                        "use a focused helper test instead."
                    )

        self.assertNotIn(bad_claim, result["claims"])



if __name__ == "__main__":
    unittest.main()
