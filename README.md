# Manager Productivity Assistant

An AI-powered assistant for engineering managers. Maintains a persistent memory of
your org, projects, and commitments — and connects to live data via MCP servers.

Built on a Python agentic loop using Claude (Anthropic API).

---

## What it does

Ask it anything in natural language:

```
> morning briefing
> prep me for my 1:1 with Jordan
> what's the status on the Copilot integration project?
> what are my open action items?
> week in review
```

It reads your persistent memory (people, projects, commitments) and, if MCP servers
are connected, fetches live email, calendar, and message data to produce structured,
actionable output.

---

## Requirements

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- A directory on your machine for your personal data (outside the source tree)
- MCP server(s) for live data — optional, works from memory without them

---

## Installation

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd orchestrator

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set the two required values:

```bash
ANTHROPIC_API_KEY=sk-ant-...
DATA_DIR=/Users/you/orchestrator-data
```

`DATA_DIR` can be any path you choose. It will be created and populated automatically
on first run. It is never committed to git.

### 3. Run

```bash
python main.py
```

---

## Populating your context

The assistant is only as useful as the context it has.

### Seed from notes or transcripts

```bash
python seed.py --file my-notes.txt          # unstructured text → Claude extracts
python seed.py --file weekly_synthesis.json  # structured synthesis → direct parse
python seed.py --dir ./meeting-notes/        # process a whole directory
python seed.py --file notes.txt --dry-run    # preview without writing
```

### Edit directly

Open `DATA_DIR` in your editor:

| File | What to put in it |
|---|---|
| `people.json` | Direct reports, stakeholders, key relationships |
| `projects.json` | Active projects with status, risks, milestones |
| `action_items.json` | Open commitments |
| `context.md` | Narrative context |

---

## Connecting live data via MCP

Add servers to `mcp_servers.md` (created automatically, gitignored):

```
[MCP_SERVER]
ServerURL = https://your-mcp-server.com/mcp
AuthToken = optional-bearer-token

[MCP_SERVER]
ServerURL = https://another-server.com/mcp
```

MCP servers can provide both **data tools** (email, calendar, messages) and
**skills** (prompt templates). Skills from MCP servers are merged with local skills —
local always wins on name conflict.

---

## REPL commands

| Command | What it does |
|---|---|
| `/skills` | List loaded skills (local + MCP) |
| `/tools` | Show available tools |
| `/model claude-sonnet-4-6` | Switch model mid-session |
| `/clear` | Clear conversation history |
| `/help` | Show all commands |
| `exit` | Quit |

---

## Project structure

```
main.py              Start here — interactive REPL
seed.py              Seed memory from notes or structured synthesis files
mcp_servers.md       MCP server registry (gitignored, user-managed)

manager/
  memory_store.py    Read/write files in DATA_DIR
  mcp_skills.py      MCP server client + mcp_servers.md parser

skills/              Local skills — always active
  manager_assistant.md  Core manager layer
  daily_briefing.md     Morning briefing format
  meeting_prep.md       Meeting prep format
  weekly_review.md      Weekly review format

data/                Template files shipped with the source
  people.json / projects.json / action_items.json
  context.md / decisions.md
  people/_template.md / projects/_template.md
```

Your personal data in `DATA_DIR` (outside this repo, never committed):

```
DATA_DIR/
  people.json / projects.json / action_items.json
  context.md / decisions.md
  people/     ← per-person 1:1 notes
  projects/   ← per-project notes and decisions
```

---

## What's coming

- [ ] MCP server for Microsoft 365 (email, calendar, Teams)
- [ ] MCP server for Azure DevOps boards
- [ ] Email reply drafting skill
- [ ] Meeting transcript skill
