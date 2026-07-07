"""
Run the HarmonyOS MCP server with openai-agents and a DeepSeek-compatible endpoint.

Environment:
    DEEPSEEK_API_KEY=...
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_MODEL=deepseek-v4-flash

Usage:
    uv run python examples/deepseek_agents_mcp.py "查看本地天气"
"""

import asyncio
import os
from pathlib import Path
import sys

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServer, MCPServerStdio


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def run(mcp_server: MCPServer, message: str) -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Please set DEEPSEEK_API_KEY before running this example.")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    model_name = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

    agent = Agent(
        name="HarmonyOS Assistant",
        instructions=(
            "Use the MCP tools to inspect weather and operate HarmonyOS apps. "
            "When launching apps, prefer launch_harmony_app for aliases."
        ),
        model=OpenAIChatCompletionsModel(model=model_name, openai_client=client),
        mcp_servers=[mcp_server],
    )

    result = await Runner.run(starting_agent=agent, input=message)
    print(result.final_output)


async def main() -> None:
    set_tracing_disabled(True)
    message = " ".join(sys.argv[1:]) or "查看本地天气"

    async with MCPServerStdio(
        params={
            "command": "uv",
            "args": ["--directory", str(PROJECT_ROOT), "run", "server.py"],
        },
        cache_tools_list=True,
        name="harmonyos",
    ) as server:
        await run(server, message)


if __name__ == "__main__":
    asyncio.run(main())
