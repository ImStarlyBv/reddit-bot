"""
agent.py — the single-task orchestrator (the inner loop).

DeepSeek (brain) ⇄ chrome-devtools-mcp (hands) ⇄ your Chrome ⇄ X (Twitter).

One call to run_task() = ONE bounded agentic task: DeepSeek picks a tool -> we call it via MCP ->
feed the result back -> repeat, until it answers or hits MAX_STEPS (the per-task circuit breaker).
The 24/7 behavior lives in runner.py, which calls run_task() over and over with pacing + limits.

Manual use:
  python agent.py "Go to x.com and list 5 posts from the home timeline"
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

# Windows consoles default to cp1252 and choke on emoji in our live output. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

HERE = Path(__file__).parent
PROFILE_DIR = Path(os.getenv("CHROME_PROFILE_DIR", "./chrome-profile")).resolve()
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
ALLOW_WRITES = os.getenv("ALLOW_WRITES", "false").lower() == "true"
MAX_STEPS = int(os.getenv("MAX_STEPS", "30"))  # per-task circuit breaker, NOT a runtime limit
BROWSER_URL = os.getenv("BROWSER_URL", "http://127.0.0.1:9222").strip()
CONNECT_MODE = os.getenv("CONNECT_MODE", "true").lower() == "true"
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "instructions.md")

deepseek = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)


def server_params() -> StdioServerParameters:
    """CONNECT (default): attach to your already-running Chrome on BROWSER_URL.
    LAUNCH: MCP starts its own Chrome with a persistent profile."""
    if CONNECT_MODE:
        args = ["-y", "chrome-devtools-mcp@latest", f"--browserUrl={BROWSER_URL}",
                "--no-usage-statistics"]
    else:
        args = ["-y", "chrome-devtools-mcp@latest", f"--userDataDir={PROFILE_DIR}",
                "--viewport", "1280x900", "--no-usage-statistics"]
    return StdioServerParameters(command="npx", args=args)


def load_system_prompt(allow_writes: bool, runtime_note: str = "") -> str:
    """instructions.md + the runtime engagement state the runner computed."""
    base = (HERE / SYSTEM_PROMPT_FILE).read_text(encoding="utf-8")
    gate = (
        "ENGAGEMENT IS ENABLED this run — you may post/comment per the rules."
        if allow_writes
        else "ENGAGEMENT IS DISABLED this run — read-only. Describe what you WOULD write but do NOT "
        "type into any compose box; do not click Post or Reply."
    )
    extra = f"\n{runtime_note}" if runtime_note else ""
    return f"{base}\n\n## Runtime flags (live)\n{gate}{extra}\n"


def mcp_tools_to_openai(mcp_tools) -> list[dict]:
    out = []
    for t in mcp_tools:
        out.append({"type": "function", "function": {
            "name": t.name,
            "description": (t.description or "")[:1024],
            "parameters": t.inputSchema or {"type": "object", "properties": {}},
        }})
    return out


def extract_text(result) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        elif getattr(block, "type", "") == "image":
            parts.append("[image returned]")
    return "\n".join(parts) if parts else "[no text content]"


async def run_task(task: str, allow_writes: bool = ALLOW_WRITES, runtime_note: str = "",
                   max_steps: int = MAX_STEPS) -> str:
    """Run ONE bounded agentic task. Prints a live play-by-play. Returns the final answer text."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[setup] model={MODEL}  writes={'ON' if allow_writes else 'OFF'}  "
          f"prompt<-{SYSTEM_PROMPT_FILE}  max_steps={max_steps}", flush=True)

    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            openai_tools = mcp_tools_to_openai((await session.list_tools()).tools)
            print(f"[setup] {len(openai_tools)} browser tools available", flush=True)
            print(f"\n🧭 TASK: {task}\n{'─' * 60}", flush=True)

            messages = [
                {"role": "system", "content": load_system_prompt(allow_writes, runtime_note)},
                {"role": "user", "content": task},
            ]

            for step in range(1, max_steps + 1):
                resp = deepseek.chat.completions.create(
                    model=MODEL, messages=messages, tools=openai_tools,
                    tool_choice="auto", temperature=0.2,
                )
                msg = resp.choices[0].message
                messages.append(msg.model_dump(exclude_none=True))

                # live: the model's reasoning/narration this turn
                if msg.content and msg.content.strip():
                    print(f"\n🧠 step {step}: {msg.content.strip()}", flush=True)

                if not msg.tool_calls:
                    print(f"\n{'═' * 60}\n✅ FINAL ANSWER (step {step})\n{'═' * 60}\n{msg.content}\n",
                          flush=True)
                    return msg.content or ""

                for call in msg.tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"  🔧 step {step}: {name}({json.dumps(args)[:140]})", flush=True)

                    try:
                        result = await session.call_tool(name, args)
                        content = extract_text(result)
                        preview = " ".join(content.split())[:200]
                        print(f"     ↳ {preview}{'…' if len(content) > 200 else ''}", flush=True)
                    except Exception as e:  # surface to the model so it can recover
                        content = f"TOOL ERROR: {e}"
                        print(f"     ‼ {content}", flush=True)

                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": content[:8000]})

            print(f"\n⛔ STOPPED: hit MAX_STEPS ({max_steps}) — task ended by circuit breaker.",
                  flush=True)
            return "[stopped: max steps reached]"


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python agent.py "your task for the agent"')
        sys.exit(1)
    asyncio.run(run_task(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    main()
