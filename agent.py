"""
agent.py — the orchestrator.

DeepSeek (brain) ⇄ chrome-devtools-mcp (hands) ⇄ your Chrome ⇄ Reddit.

Flow:
  1. Launch chrome-devtools-mcp (stdio) with the persistent profile.
  2. List its tools -> convert to OpenAI function schemas.
  3. Load instructions.md as the system prompt.
  4. Agentic loop: DeepSeek picks a tool -> we call it via MCP -> feed result back -> repeat.

Usage:
  python agent.py "Open reddit.com and summarize the top 5 posts on r/all"
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

HERE = Path(__file__).parent
PROFILE_DIR = Path(os.getenv("CHROME_PROFILE_DIR", "./chrome-profile")).resolve()
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
ALLOW_WRITES = os.getenv("ALLOW_WRITES", "false").lower() == "true"
MAX_STEPS = int(os.getenv("MAX_STEPS", "25"))

deepseek = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)


BROWSER_URL = os.getenv("BROWSER_URL", "http://127.0.0.1:9222").strip()
CONNECT_MODE = os.getenv("CONNECT_MODE", "true").lower() == "true"


def server_params() -> StdioServerParameters:
    """
    CONNECT mode (default): attach to YOUR already-running Chrome (started via start_chrome.ps1)
    and open work in a new tab of your live, logged-in session — the 'use the browser I'm in' behavior.
    LAUNCH mode: MCP starts its own Chrome with a persistent profile instead.
    """
    if CONNECT_MODE:
        args = ["-y", "chrome-devtools-mcp@latest", f"--browserUrl={BROWSER_URL}",
                "--no-usage-statistics"]
    else:
        args = ["-y", "chrome-devtools-mcp@latest", f"--userDataDir={PROFILE_DIR}",
                "--viewport", "1280x900", "--no-usage-statistics"]
    return StdioServerParameters(command="npx", args=args)


def load_system_prompt() -> str:
    base = (HERE / "instructions.md").read_text(encoding="utf-8")
    gate = (
        "WRITES ARE ENABLED for this run. You may upvote/comment/post per the rules."
        if ALLOW_WRITES
        else "WRITES ARE DISABLED for this run. Read-only. For any state-changing action, describe "
        "what you WOULD do and stop — do not click the final confirm."
    )
    return f"{base}\n\n## Runtime flags\n{gate}\n"


def mcp_tools_to_openai(mcp_tools) -> list[dict]:
    """Convert MCP tool defs into OpenAI `tools=[...]` function schemas."""
    out = []
    for t in mcp_tools:
        out.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "")[:1024],
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        })
    return out


def extract_text(result) -> str:
    """Flatten an MCP tool result into text for the model."""
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        elif getattr(block, "type", "") == "image":
            parts.append("[image returned]")
    return "\n".join(parts) if parts else "[no text content]"


async def run(task: str) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[setup] profile={PROFILE_DIR}  model={MODEL}  writes={'ON' if ALLOW_WRITES else 'OFF'}")

    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = (await session.list_tools()).tools
            openai_tools = mcp_tools_to_openai(tool_list)
            print(f"[setup] {len(openai_tools)} browser tools available")

            messages = [
                {"role": "system", "content": load_system_prompt()},
                {"role": "user", "content": task},
            ]

            for step in range(1, MAX_STEPS + 1):
                resp = deepseek.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
                msg = resp.choices[0].message
                messages.append(msg.model_dump(exclude_none=True))

                if not msg.tool_calls:
                    print(f"\n=== DONE (step {step}) ===\n{msg.content}")
                    return

                for call in msg.tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"[step {step}] -> {name}({json.dumps(args)[:160]})")

                    try:
                        result = await session.call_tool(name, args)
                        content = extract_text(result)
                    except Exception as e:  # surface the error to the model so it can recover
                        content = f"TOOL ERROR: {e}"
                        print(f"           !! {content}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": content[:8000],
                    })

            print(f"\n=== STOPPED: hit MAX_STEPS ({MAX_STEPS}) without finishing ===")


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python agent.py "your task for the agent"')
        sys.exit(1)
    asyncio.run(run(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    main()
