# Architecture

## The core idea

Yes — **the AI has the smarts. The code just plumbs data to it.**

This is the key mental model. There is no traditional business logic in this codebase.
No rules engine, no if-then decision trees, no hardcoded prioritisation logic.
Claude reasons about what's important, what's urgent, what questions to ask, and what
format to produce. The Python code exists to:

1. Get data to Claude (tools)
2. Keep Claude's state across turns (conversation history)
3. Persist information between sessions (memory files)
4. Run on a schedule without a human present (refresh script)

---

## The loop

Every interaction is the same cycle:

```
You type something
       │
       ▼
Claude reads your message + system prompt + conversation history
       │
       ▼
Claude decides: do I need more information?
       │
   YES │                          NO │
       ▼                             ▼
Claude calls a tool           Claude writes a response
(fetch_emails, read_memory…)        │
       │                             ▼
Python executes it            You see the answer
       │
Tool result returned to Claude
       │
Back to top — Claude decides again
```

This cycle repeats until Claude has everything it needs and writes a final response.
A single message from you might trigger 4–6 tool calls before Claude responds —
fetching emails, reading the people file, checking action items, searching memory.
You don't see any of that; you just see the output.

---

## Where the intelligence lives

### The model (Claude)
All reasoning happens here. Claude decides:
- Which tools to call and in what order
- What in the data is signal vs. noise
- What's urgent vs. what's FYI
- How to structure the output (briefing, meeting prep, or just a direct answer)
- Whether something should be logged as an action item

None of this is coded. It emerges from Claude's training + the prompts we give it.

### The system prompt (`system_prompt.md`)
This is Claude's personality and operating principles for this use case.
It tells Claude: you are an EA/chief-of-staff for a Microsoft M2 manager.
It encodes high-level heuristics: lead with urgency, read memory before answering,
track commitments, think about the manager's leverage through their managers.

### Skills (`skills/*.md`)
Skills are additional prompt instructions injected when relevant.
They encode two things:
- **Behaviour**: how to approach a specific type of task (e.g. for meeting prep,
  check open action items, anticipate what the other person will raise)
- **Format**: what the output should look like (the briefing template, the meeting
  prep template, etc.)

All manager skills are always active — Claude sees all of them every turn and uses
its judgment to apply whichever is relevant to your ask.

---

## What the code does

### `main.py` — the loop
A simple REPL. It takes your input, sends it to Claude with the current system prompt
and available tools, handles any tool calls Claude makes, and prints the response.
Maintains conversation history so Claude remembers context within a session.
~250 lines. No business logic.

### `tools.py` — the data pipes
Registers all available tools with Claude (as JSON schemas) and dispatches calls to
their implementations. When Claude says "call fetch_emails with days=1", this file
routes that to the right Python function and returns the result as a string.

### `manager/graph_client.py` — the data source
Fetches data from Microsoft 365 via Graph API. Returns raw structured data.
When no credentials are configured, returns realistic mock data instead.
This file has no opinions about what the data means — it just fetches it.

### `manager/tools_graph.py` — formatting for Claude
Takes raw data from `graph_client.py` and formats it into compact, readable text
that Claude can reason about efficiently. An email becomes a few lines:
subject, sender, timestamp, 250-char preview. A calendar event becomes:
title, time, attendees, notes. Less is more — Claude doesn't need raw JSON.

### `manager/memory_store.py` — persistence between sessions
Reads and writes the files in `DATA_DIR`. This is how Claude knows who Jordan Rivera
is next Tuesday even though the conversation was cleared. The agent updates these files
as it learns things — new action items, project status changes, context notes.

### `refresh.py` — the background brain
Runs headlessly (no human in the loop). Fetches all data sources, sends everything
to Claude in one shot, and asks Claude to extract structured intelligence: new action
items, project updates, a narrative summary. Claude returns JSON. The script writes
it to the memory files. A daily briefing file is also written for later retrieval.

---

## The data flow

```
Microsoft 365                    DATA_DIR/ files
(Email, Calendar, Teams)         (people, projects,
        │                         action items, context)
        │                                │
        ▼                                ▼
  graph_client.py              memory_store.py
        │                                │
        └──────────────┬─────────────────┘
                       │
                  tools_graph.py
                  (format as text)
                       │
                       ▼
              ┌────────────────┐
              │     Claude     │  ◄── system_prompt.md
              │                │  ◄── skills/*.md
              │  (all the      │  ◄── conversation history
              │   reasoning)   │
              └────────────────┘
                       │
                       ▼
              Response to you
              + memory updates
```

---

## Why this architecture

### Adding a new data source is just a new tool
Want Azure DevOps? Write a function that fetches work items and returns a formatted
string. Register it in `tools.py`. Tell Claude what it does in the tool description.
Claude will call it when relevant. No other changes needed.

### Adding new behaviour is just a new skill
Want Claude to also draft weekly status emails to your manager? Write a `skills/status_email.md`
that describes the format and when to use it. Claude picks it up on the next reload.
No code changes.

### The "smarts" improve for free
As Claude models improve, the assistant improves — better prioritisation, better
summaries, better judgment about what matters — with zero changes to this codebase.

### The hard part is prompt quality, not code
The most impactful thing to work on is the quality of the system prompt and skills.
Better instructions to Claude produce better outputs more reliably than more code.
A well-written skill file is worth more than a new feature.

---

## What this is not

- **Not a RAG system** — there's no vector database or semantic search.
  Memory is plain files; `search_memory` is keyword grep. Good enough for this scale.
  If the context grows large enough to need it, that's when to add embeddings.

- **Not an automation engine** — Claude doesn't take actions autonomously
  (it doesn't send emails, book meetings, or update ADO items on its own).
  It surfaces information and recommendations; a human decides and acts.
  That's intentional for now.

- **Not a fine-tuned model** — all the manager-specific knowledge lives in prompts,
  not model weights. This means it's easy to adjust behaviour by editing markdown files,
  and the same base Claude model handles everything.
