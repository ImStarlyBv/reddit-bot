# reddit-bot

DeepSeek-driven Reddit agent. A text-only LLM (**DeepSeek v4**) controls a real Google Chrome via
Google's [`chrome-devtools-mcp`](https://github.com/ChromeDevTools/chrome-devtools-mcp) and operates
Reddit through the page DOM — no vision needed.

```
DeepSeek-v4-pro (text) ── chrome-devtools-mcp ──► your Chrome (logged-in profile) ──► reddit.com
       brain                   hands                     persistent session            target
```

## How it works
1. `agent.py` launches/attaches `chrome-devtools-mcp` (stdio) and pulls its browser tools.
2. Those tools are handed to DeepSeek as function-calling tools.
3. `instructions.md` is loaded as the system prompt.
4. Agentic loop: DeepSeek picks a tool → agent calls it via MCP → result goes back → repeat.

Reddit stays logged in via a **persistent Chrome profile** — log in once by hand, the session sticks.
Run it on a machine that already has Reddit access (e.g. your home PC).

## Quick start
```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # paste your DeepSeek key into .env

# connect mode (drives your real Chrome):
.\start_chrome.ps1                 # log into Reddit once, leave the window open
python agent.py "Open r/all and summarize the top 5 posts"
```

## Files
| File | Purpose |
|------|---------|
| `agent.py` | Orchestrator: DeepSeek ⇄ MCP loop |
| `instructions.md` | Agent operating manual (system prompt) |
| `TASK.md` | Build plan / roadmap |
| `start_chrome.ps1` | Launch your Chrome with remote debugging (connect mode) |
| `login_once.py` | One-time manual login for launch mode |
| `test_deepseek.py` / `smoke_test.py` / `test_vision.py` | Connectivity + capability tests |

## Notes
- DeepSeek is **text-only** — works because we drive the DOM, not pixels.
- `ALLOW_WRITES=false` by default: browses/summarizes but won't vote/comment/post until you flip it.
- Respect Reddit's ToS and rate limits. Assisted browsing, not spam.

## Config (`.env`)
See `.env.example`. Never commit `.env` or `chrome-profile/` — both are git-ignored.
