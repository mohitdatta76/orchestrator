# CLAUDE.md — Manager Productivity Assistant

This file is read by Claude Code at the start of every session.
It provides the context needed to pick up where we left off.

---

## What this project is

A productivity assistant for an M2 engineering manager at Microsoft.
Built on a Python agentic orchestrator (Claude API + tool use loop).

The assistant helps with:
- **Daily briefings** — what's urgent, today's meetings, key signals
- **Meeting prep** — context, talking points, open items, risks
- **Weekly reviews** — what shipped/slipped, team health, next week's priorities
- **Q&A** — anything about people, projects, commitments from persistent memory

All O365 data (email, calendar, Teams) comes from Microsoft Graph API.
**Auth is not yet wired up** — the system runs on realistic mock data until
`GRAPH_ACCESS_TOKEN` is set in `.env`.

---

## Architecture overview

```
main.py              — Interactive REPL (agentic loop)
tools.py             — All tool schemas + dispatch (base + graph/memory tools)
config.py            — Config from .env (model, skills_dir, memory_dir, etc.)
skill_loader.py      — Loads skills/*.md, matches to user messages
system_prompt.md     — Base system prompt (M2 manager persona)

manager/
  graph_client.py    — O365 Graph API client; mock_mode=True if no token set
  tools_graph.py     — Tool schemas + execution for graph/memory tools
  memory_store.py    — CRUD for memory/ files (read, update, search)

memory/              — Persistent context store (populate with real data)
  people.json        — Direct reports, stakeholders, key relationships
  projects.json      — Active projects: status, risks, milestones
  action_items.json  — Open commitments with owner and due date
  context.md         — Rolling narrative log (newest first)

skills/              — All always: true (no keyword triggers needed)
  manager_assistant.md  — Core M2 manager layer, always-on, priority 100
  daily_briefing.md     — Briefing format + instructions, priority 90
  meeting_prep.md       — Meeting prep format + instructions, priority 85
  weekly_review.md      — Weekly review format + instructions, priority 80
  coding.md             — Coding assistant (keyword-triggered)
  research.md           — Research assistant (keyword-triggered)

refresh.py           — Daily sync script (fetch → Claude distills → updates memory)
cron_manager.py      — Enable/disable/status/run for 7am Mon–Fri cron
```

---

## Key design decisions

1. **All manager skills are `always: true`** — keyword triggers were removed because
   Claude's reasoning handles intent detection better than substring matching.
   Say "what's on my plate" or "am I ready for tomorrow" — no trigger phrase needed.

2. **Mock mode is automatic** — no `GRAPH_ACCESS_TOKEN` → `graph_client.py` returns
   realistic synthetic Microsoft data. Full system works end-to-end without credentials.

3. **Memory is append-friendly JSON + Markdown** — `update_memory("action_items", {...})`
   deep-merges; `update_memory("context", "text")` prepends to context.md.
   Designed to migrate to SQLite later without changing the tool interface.

4. **refresh.py is headless** — calls Claude directly (no REPL), dumps all sources into
   one payload, Claude returns structured JSON, script writes to memory files.

---

## Running the project

```bash
# First time setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY at minimum

# Start the assistant
python main.py

# Run a manual daily refresh
python refresh.py
python refresh.py --dry-run   # preview without writing

# Cron job (7am Mon–Fri, runs refresh.py)
python cron_manager.py enable
python cron_manager.py status
python cron_manager.py disable
python cron_manager.py run    # run now manually
```

---

## What to work on next

### High priority
- **Wire up real auth** — MSAL device-code flow in `graph_client.py` (stubs already there).
  Need `GRAPH_CLIENT_ID` + `GRAPH_TENANT_ID` in `.env`, then call `msal.PublicClientApplication`.
  Scopes needed: `Mail.Read`, `Calendars.Read`, `Chat.Read`, `ChannelMessage.Read.All`, `User.Read`.

- **Populate memory files** — replace placeholder data in `memory/people.json` and
  `memory/projects.json` with real direct reports, stakeholders, and active projects.
  This is what makes the assistant genuinely useful.

### Medium priority
- **ADO boards integration** — add `fetch_ado_items` tool to `manager/tools_graph.py`.
  Azure DevOps REST API uses a PAT (Personal Access Token), simpler than Graph OAuth.
  Endpoint: `https://dev.azure.com/{org}/{project}/_apis/wit/workitems`

- **Meeting transcript retrieval** — the `fetch_transcript` tool is stubbed.
  Teams meeting transcripts are available via Graph:
  `GET /me/onlineMeetings/{id}/transcripts/{id}/content`
  Requires `OnlineMeetingTranscript.Read.All` permission.

- **Email threading** — currently shows individual emails; grouping by conversation thread
  would reduce noise significantly. Graph supports `$expand=threads`.

### Lower priority
- **SQLite migration** — swap `memory_store.py` backend to SQLite for better querying
  and history. Tool interface (`read_memory`, `update_memory`, `search_memory`) stays the same.

- **Slack/email drafting** — add a `draft_reply(email_id, tone)` tool that uses Claude
  to draft a response to a specific email, which the user can copy/paste.

- **People enrichment** — auto-update `people.json` from org chart data (Graph `/users`
  endpoint) to keep team size and reporting relationships current.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `MODEL` | No | `claude-opus-4-6` | Model to use |
| `MAX_TOKENS` | No | `8096` | Max tokens per response |
| `MEMORY_DIR` | No | `memory` | Path to memory directory |
| `GRAPH_ACCESS_TOKEN` | No | — | O365 bearer token; unset = mock mode |
| `GRAPH_CLIENT_ID` | No | — | Azure AD app client ID (for MSAL flow) |
| `GRAPH_TENANT_ID` | No | — | Azure AD tenant ID (for MSAL flow) |

---

## File ownership notes

- `memory/` should be in `.gitignore` — it contains personal work context
- `logs/` (created by cron) should also be gitignored
- `.env` is already gitignored via `.env.example` convention
