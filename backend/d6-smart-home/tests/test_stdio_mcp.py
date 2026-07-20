import ast
import unittest
from pathlib import Path


class StdioMCPWrapperTests(unittest.TestCase):
    def test_wrapper_shares_gateway_super_mcp_and_keeps_stdout_clean(self):
        path = Path(__file__).resolve().parents[1] / "mcp_server_enhanced.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("_initialize_super_context", source)
        self.assertIn("_super_mcp.dispatch", source)
        self.assertIn("redirect_stdout(sys.stderr)", source)
        self.assertNotIn("TOOLS = {", source)
        self.assertNotIn("def tool_toggle_device", source)
        self.assertIn("MAX_LINE_BYTES", source)


if __name__ == "__main__":
    unittest.main()
