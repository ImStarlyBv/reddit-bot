# TASK.md — DeepSeek ↔ Chrome ↔ Reddit

The build plan. How we go from empty folder to a DeepSeek agent driving *your* Chrome on Reddit.

## Goal
A Python agent where **DeepSeek** (the brain) controls **your Google Chrome** (the hands) via the
**`chrome-devtools-mcp`** server, to read and interact with **Reddit** while staying logged in as you.

## Tech stack
| Layer            | Choice                          | Why |
|------------------|---------------------------------|-----|
| LLM / brain      | DeepSeek API (`deepseek-chat`)  | Cheap, OpenAI-compatible, supports tool/function calling |
| LLM client       | `openai` Python SDK             | DeepSeek speaks the OpenAI API; point `base_url` at DeepSeek |
| Browser control  | `chrome-devtools-mcp` (Node)    | Google's MCP server; drives Chrome over CDP, exposes click/fill/navigate/snapshot tools |
| MCP client       | `mcp` Python SDK (stdio)        | Connects agent.py to the MCP server, lists its tools, calls them |
| Browser          | Chrome with a **persistent profile** | Log in once by hand → session cookies persist → every run is already authenticated |
| Runtime          | Python 3.14, Node 24            | Both already installed on this machine |

## Architecture (the loop)
1. `agent.py` launches `chrome-devtools-mcp` via `npx` (stdio transport).
2. It asks the MCP server for its tool list → converts each to an OpenAI `tools=[...]` schema.
3. It loads `instructions.md` as the **system prompt**.
4. Agentic loop: send messages → DeepSeek picks a tool → agent calls it through MCP → feeds the
   result back → repeat until DeepSeek answers with no tool call.
5. Chrome opens a dedicated profile dir so your login survives between runs.

## Milestones / checklist

### Phase 0 — Setup (do this first, by hand)
- [ ] `python -m venv .venv` and activate it
- [ ] `pip install -r requirements.txt`
- [ ] Copy `.env.example` → `.env`, paste your **DeepSeek API key** (https://platform.deepseek.com)
- [ ] Confirm `npx -y chrome-devtools-mcp@latest --help` runs (downloads the server)

### Phase 1 — One-time manual login (the "auto-login" foundation)
**Connect mode (default — the "use the browser I'm in" behavior):**
- [ ] Run `./start_chrome.ps1` — opens your Chrome with remote debugging on :9222
- [ ] In that window: log into Google, then reddit.com ("Continue with Google" / log in). **Leave it open.**
- [ ] Why manual: Google blocks scripted credential entry. The live session sidesteps it.

**Launch mode (alternative — `CONNECT_MODE=false`):**
- [ ] Run `python login_once.py` — opens Chrome with our persistent profile (`./chrome-profile/`),
      log in once, close it. Cookies persist; the agent launches its own Chrome from that profile.

### Phase 2 — First automated run
- [ ] (Connect mode) keep the start_chrome.ps1 window open, then run agent.py in another terminal
- [ ] `python agent.py "Open reddit.com and tell me the top 5 posts on r/all"`
- [ ] Verify Chrome reuses the logged-in profile (you should see your username, not a login wall)
- [ ] Confirm DeepSeek is calling MCP tools (watch the console trace)

### Phase 3 — Reddit task skills
- [ ] Read a subreddit feed and summarize → already works via the snapshot tools
- [ ] Open a post + top comments → `navigate_page` + `take_snapshot`
- [ ] Upvote / save a post → `click` on the snapshot's element uid
- [ ] Post a comment / reply → `fill` + `click` (gated behind a confirmation flag, see instructions.md)
- [ ] Search Reddit, follow/join a subreddit

### Phase 4 — Safety + polish
- [ ] Dry-run mode: agent describes the action before any write (comment/vote/post)
- [ ] Rate limiting / human-like pacing so Reddit doesn't flag the account
- [ ] Logging of every tool call to `runs/<timestamp>.log`
- [ ] Optional: scheduled runs (digest of your subreddits each morning)

## Risks / things to respect
- **Reddit ToS & rate limits.** Don't mass-post, spam, or vote-manipulate — that gets the account banned.
  Keep it to assisted browsing / single deliberate actions. This is your own account acting as you.
- **Google bot detection.** Only ever log in *manually* in the persistent profile. Never script credentials.
- **Writes are dangerous.** Comments/posts/votes are public and hard to undo — keep them behind the
  `ALLOW_WRITES` confirmation gate (see instructions.md).
- **Secrets.** `.env` and `chrome-profile/` hold your key and live session — both are git-ignored.

## File map
```
deepseekredditer/
├── TASK.md            ← this file (the plan)
├── instructions.md    ← the agent's operating manual = system prompt DeepSeek reads
├── agent.py           ← orchestrator: DeepSeek ⇄ MCP loop
├── login_once.py      ← opens Chrome w/ persistent profile for the one-time manual login
├── requirements.txt   ← Python deps
├── .env.example       ← template for secrets
├── .gitignore
└── chrome-profile/    ← (created on first login) your persistent Chrome session — DO NOT COMMIT
```
