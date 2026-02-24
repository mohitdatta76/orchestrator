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

Live data (email, calendar, Teams/chat) comes from MCP servers registered in
`mcp_servers.md`. Without any MCP servers connected, the assistant works from
persistent memory only.

---

## Architecture overview

```
main.py              — Interactive REPL (agentic loop)
tools.py             — Base tool schemas + dispatch (bash, file I/O, memory)
config.py            — Config from .env (ANTHROPIC_API_KEY + DATA_DIR required)
skill_loader.py      — Loads skills from local files + registered MCP servers
system_prompt.md     — Base system prompt (M2 manager persona)
mcp_servers.md       — MCP server registry (gitignored, user-managed)

manager/
  memory_store.py    — CRUD for DATA_DIR files (read, update, search)
  mcp_skills.py      — MCP server client + mcp_servers.md parser

data/                — Template files shipped with source (never edited by users)
  people.json / projects.json / action_items.json
  context.md / decisions.md
  people/_template.md / projects/_template.md

skills/              — Local skills, always active
  manager_assistant.md  — Core M2 manager layer, always-on, priority 100
  daily_briefing.md     — Briefing format + instructions, priority 90
  meeting_prep.md       — Meeting prep format + instructions, priority 85
  weekly_review.md      — Weekly review format + instructions, priority 80
  coding.md             — Coding assistant (keyword-triggered)
  research.md           — Research assistant (keyword-triggered)
```

User data lives in `DATA_DIR` (set in `.env`, outside the source tree, gitignored):
```
DATA_DIR/
  people.json / projects.json / action_items.json
  context.md / decisions.md
  people/<alias>.md    — per-person 1:1 history
  projects/<name>.md   — per-project notes and decisions
```

---

## Key design decisions

1. **All manager skills are `always: true`** — Claude sees all skills every turn and
   applies whichever are relevant. No keyword triggers needed.

2. **Live data via MCP** — email, calendar, and messages come from MCP servers listed
   in `mcp_servers.md`. Skills are also dynamically registered from MCP servers.
   Local skills always take precedence over remote ones on name conflict.

3. **Memory is append-friendly JSON + Markdown** — `update_memory("action_items", {...})`
   deep-merges; `update_memory("context", "text")` prepends to context.md.

4. **DATA_DIR is required** — crashes on startup if not set. First run copies templates
   from `data/` into `DATA_DIR` automatically.

---

## Running the project

```bash
# First time setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY and DATA_DIR

# Seed from meeting notes or synthesis files
python seed.py --file my-notes.txt
python seed.py --file weekly_synthesis.json   # direct parse, no Claude call

# Start the assistant
python main.py
```

---

## What to work on next

### High priority
- **Populate DATA_DIR** — run `seed.py` against real notes/transcripts, or manually
  edit `people.json` and `projects.json`. This is what makes the assistant useful.

- **Connect an MCP server** — add entries to `mcp_servers.md` for email, calendar,
  and Teams data. The skills will use whatever tools the MCP server exposes.

### Medium priority
- **Per-person memory enrichment** — as 1:1s happen, seed notes into `people/<alias>.md`.
- **ADO boards via MCP** — an MCP server exposing ADO work items would make weekly
  reviews significantly more grounded.

### Lower priority
- **SQLite migration** — swap `memory_store.py` backend. Tool interface stays the same.
- **Email reply drafting** — skill that uses available email tools to draft responses.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `DATA_DIR` | Yes | Path to user data directory (outside source tree) |
| `MCP_SERVERS_FILE` | No | Path to MCP servers config (default: `mcp_servers.md`) |
| `MODEL` | No | Model to use (default: `claude-opus-4-6`) |
| `MAX_TOKENS` | No | Max tokens per response (default: `8096`) |

---

## Gitignore notes

These are gitignored and must not be committed:
- `DATA_DIR` contents — personal work context
- `mcp_servers.md` — contains server URLs and auth tokens
- `.env`
