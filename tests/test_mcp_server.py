import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

from rpl.mcp_server import analyze_for_mcp, create_server
from rpl.service import analyze_source
from rpl.source import SourceError


FIXTURE = Path(__file__).parent / "fixtures" / "agentic_erp_sample.html"


class LocalMcpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = analyze_source(str(FIXTURE))

    def test_mcp_input_cannot_read_arbitrary_local_files(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaises(SourceError):
                analyze_for_mcp(str(FIXTURE), output_root=directory)

    def test_server_exposes_one_clear_tool_and_three_resources(self) -> None:
        with TemporaryDirectory() as directory:
            server = create_server(directory)
            tools = asyncio.run(server.list_tools())
            templates = asyncio.run(server.list_resource_templates())

        self.assertEqual([tool.name for tool in tools], ["analyze_arxiv_paper"])
        self.assertEqual(
            {str(template.uriTemplate) for template in templates},
            {
                "rpl://papers/{paper_key}/paper.html",
                "rpl://papers/{paper_key}/paper.md",
                "rpl://papers/{paper_key}/paper.json",
            },
        )

    def test_tool_returns_structured_output_and_readable_html_resource(self) -> None:
        with TemporaryDirectory() as directory:
            server = create_server(directory)
            with patch("rpl.mcp_server.analyze_source", return_value=self.analysis):
                _, structured = asyncio.run(
                    server.call_tool(
                        "analyze_arxiv_paper",
                        {"source": "https://arxiv.org/abs/2607.17331v1"},
                    )
                )

            self.assertEqual(structured["status"], "completed")
            self.assertEqual(structured["output_quality"]["status"], "ready")
            html_artifact = next(
                item for item in structured["artifacts"] if item["format"] == "html"
            )
            self.assertTrue(Path(html_artifact["path"]).is_file())
            contents = asyncio.run(
                server.read_resource(AnyUrl(html_artifact["resource_uri"]))
            )
            self.assertTrue(contents[0].content.startswith("<!doctype html>"))

            json_artifact = next(
                item for item in structured["artifacts"] if item["format"] == "json"
            )
            payload = json.loads(Path(json_artifact["path"]).read_text())
            self.assertEqual(payload["paper"]["paper_id"], "2607.17331v1")

    def test_real_stdio_transport_exposes_the_rpl_tool(self) -> None:
        async def inspect_server(directory: str) -> tuple[list[str], list[str]]:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "rpl.cli", "mcp", "--output", directory],
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resource_templates()
                    return (
                        [tool.name for tool in tools.tools],
                        [str(item.uriTemplate) for item in resources.resourceTemplates],
                    )

        with TemporaryDirectory() as directory:
            tools, resources = asyncio.run(inspect_server(directory))

        self.assertEqual(tools, ["analyze_arxiv_paper"])
        self.assertEqual(len(resources), 3)


if __name__ == "__main__":
    unittest.main()
