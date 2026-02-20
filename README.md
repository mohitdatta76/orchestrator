# Manager Productivity Assistant

An AI-powered assistant for engineering managers at Microsoft. It monitors your email,
calendar, and Teams, maintains a persistent memory of your org and projects, and helps
you show up prepared for every day and every meeting.

Built on a Python agentic orchestrator using Claude (Anthropic API) + Microsoft Graph API.

---

## What it does

**Ask it anything in natural language:**

```
> morning briefing
> prep me for my 1:1 with Jordan
> what's the status of the Copilot integration project?
> what are my open action items?
> week in review
> did anyone message me about the API migration?
```

**It automatically:**
- Fetches your email, calendar, and Teams messages
- Reads your persistent memory (people, projects, commitments)
- Produces structured, actionable output in seconds

**Daily background refresh** (optional cron job):
Runs every weekday morning at 7am, fetches overnight data, updates your memory files,
and writes a pre-built briefing you can read any time.

---

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without a Microsoft Graph token, the assistant runs on **realistic mock data**
automatically — you can explore the full experience before wiring up credentials.

### 3. Populate your context (optional but recommended)

Edit `memory/people.json` to add your actual direct reports and stakeholders.
Edit `memory/projects.json` to add your active projects.

The assistant will update these files automatically as it learns more.

### 4. Run

```bash
python main.py
```

---

## Connecting to real Microsoft 365 data

### Get an access token (quickest path)

1. Go to [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)
2. Sign in with your Microsoft account
3. Copy the access token from the **Access token** tab
4. Add to `.env`:
   ```
   GRAPH_ACCESS_TOKEN=eyJ...
   ```

Tokens expire after ~1 hour. For a persistent setup, configure MSAL app credentials
(see `CLAUDE.md` for full instructions).

### Required Graph API permissions

| Permission | Used for |
|---|---|
| `Mail.Read` | Fetch emails |
| `Calendars.Read` | Fetch calendar events |
| `Chat.Read` | Fetch Teams DMs |
| `ChannelMessage.Read.All` | Fetch Teams channel messages |
| `User.Read` | Your profile |

---

## Daily refresh

Run manually anytime:

```bash
python refresh.py              # refresh last 24 hours
python refresh.py --since 48h  # go back further
python refresh.py --dry-run    # preview without writing anything
```

Enable automatic morning refresh (Mon–Fri, 7am):

```bash
python cron_manager.py enable
python cron_manager.py status
python cron_manager.py disable
```

---

## Project structure

```
main.py              REPL — start here
refresh.py           Daily sync script
cron_manager.py      Cron job manager

manager/
  graph_client.py    Microsoft Graph API (+ mock data fallback)
  tools_graph.py     Tool implementations for Claude
  memory_store.py    Read/write persistent memory

memory/              Your context (gitignored)
  people.json        Direct reports, stakeholders
  projects.json      Active projects
  action_items.json  Open commitments
  context.md         Rolling narrative log
  briefing_*.md      Daily pre-built briefings

skills/              Behaviour modules for the assistant
  manager_assistant.md  Core manager layer (always active)
  daily_briefing.md     Briefing format and instructions
  meeting_prep.md       Meeting prep format and instructions
  weekly_review.md      Weekly review format and instructions
```

---

## REPL commands

| Command | Description |
|---|---|
| `/skills` | List loaded skills |
| `/tools` | Show available tools |
| `/model claude-sonnet-4-6` | Switch model mid-session |
| `/clear` | Clear conversation history |
| `/help` | Show all commands |
| `exit` | Quit |

---

## What's coming

- [ ] Azure DevOps boards integration
- [ ] Meeting transcript retrieval
- [ ] Email reply drafting
- [ ] Persistent MSAL token (no manual token refresh)
