import json
from unittest.mock import Mock, patch

from langgraph_agents.claude_cli import invoke_structured


class TestInvokeStructured:
    def test_reads_structured_output_from_cli_json_envelope(self):
        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
        completed = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "is_error": False,
                    "result": "",
                    "structured_output": {"value": "ok"},
                }
            ),
            stderr="",
        )

        with patch("langgraph_agents.claude_cli.subprocess.run", return_value=completed):
            result = invoke_structured("Return {value: ok}", schema)

        assert result == {"value": "ok"}