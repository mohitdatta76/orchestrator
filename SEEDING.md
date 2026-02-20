# Seeding the Assistant with Historical Context

## How Claude actually uses this data

Claude doesn't read everything on every turn. It reads **what the tools pull in**:

- `read_memory("people/jordan_rivera")` → loads Jordan's file into the context window
- `search_memory("API migration")` → keyword-searches all files, returns matching excerpts

So the files are a **queryable knowledge base**, not a document that gets read top-to-bottom.
This means:
- **Structure matters more than completeness.** A well-structured file Claude can skim is
  better than a wall of text.
- **You don't need to dump everything.** Summarised context is better. Claude reasons well
  from good summaries.
- **Keyword density matters.** Use names, project names, and terms naturally — that's what
  `search_memory` matches on.

---

## Memory file structure

```
memory/
  context.md              2-month narrative summary (weeks as sections)
  decisions.md            Key decisions made in the last 2 months
  people.json             Org roster (names, aliases, roles — lightweight)
  projects.json           Project statuses (current state)
  action_items.json       Open commitments

  people/
    jordan_rivera.md      Rich 1:1 history, patterns, career context
    casey_williams.md
    robin_kumar.md
    [one file per direct report and key stakeholder]

  projects/
    copilot_integration.md   Full project history, decisions, meeting notes
    platform_migration.md
    [one file per active or recently completed project]
```

---

## Step 1: context.md — the 2-month narrative

This is the highest-leverage file to populate first. Write it like a weekly log,
newest week at the top. Aim for 2–4 sentences per week. Claude will read this when
asked "what's been happening" or "catch me up."

**Format:**

```markdown
# Manager Context Log

## 2025-W08 (Feb 17–21)
P0 outage on Feb 17 — root cause was an unvalidated config change. Post-mortem in progress,
three action items assigned across Jordan and Robin's teams. Q1 OKR reliability KR now at
94.2% vs 99% target — will need a remediation note for leadership. Casey's promo packet
submitted for the Feb cycle.

## 2025-W07 (Feb 10–14)
Architecture review for Copilot Integration v2 — Jordan's design approved with minor changes.
Skip-level with Robin's team surfaced concerns about direction clarity; planned a team meeting
to walk through H1 roadmap. Platform team announced a breaking API change affecting two services,
migration window starts March 1.

## 2025-W06 (Feb 3–7)
...
```

**How to create this:** Paste your calendar + email summaries into Claude and ask:
> "Summarise this week's key events as a 3–4 sentence manager journal entry."
Do this for each week going back 2 months. Takes ~20 minutes.

---

## Step 2: people/<alias>.md — one file per person

Copy `memory/people/_template.md` for each direct report and key stakeholder.
The most valuable sections to fill in:

**Snapshot** — who they are, what they own. 1 paragraph.
**Current focus** — what they're working on right now.
**1:1 history** — paste in your 1:1 notes. Even rough notes are fine.
**Patterns & observations** — things you've noticed that are hard to re-derive.

**File naming:** use `firstname_lastname.md` (lowercase, underscore).
Claude accesses it via `read_memory("people/jordan_rivera")`.

**How to create these:** For each person, paste their recent emails + your 1:1 notes
into Claude and ask:
> "Summarise this person's working style, current focus, and any patterns I should know,
>  in the format of memory/people/_template.md."

---

## Step 3: projects/<name>.md — one file per project

Copy `memory/projects/_template.md` for each active or recently shipped project.
Most valuable sections:

**Current status** — what's the state right now.
**Key decisions made** — the table of important calls, who made them, and why.
**Risks & blockers** — what's been a problem.
**Meeting notes** — paste in relevant meeting notes. Even raw notes work.

**File naming:** use `project_name.md` (lowercase, underscore).
Claude accesses it via `read_memory("projects/copilot_integration")`.

---

## Step 4: decisions.md

Log of the important decisions you've made in the last 2 months.

```markdown
# Key Decisions Log

## 2025-02-14 — Approved headcount backfill for IC4 on Jordan's team
Approved the SWE IC4 backfill request. Rationale: Copilot integration milestone at risk
without this resource. Approved in IcM, start date TBD pending recruiting.

## 2025-02-07 — Agreed to API migration window of March 1–21
Aligned with Sam Patel's team on a 3-week migration window. Jordan and Casey's teams
confirmed capacity. Risk: tight for Casey given promo cycle overhead.
```

---

## Step 5: Update people.json roster

`people.json` is lightweight — just names, aliases, roles, and team sizes.
It's how Claude knows who your direct reports are without reading every person file.

```json
{
  "direct_reports": [
    {
      "name": "Jordan Rivera",
      "alias": "jordan_rivera",
      "role": "Senior Engineering Manager",
      "team": "Copilot Integration",
      "team_size": 8,
      "level": "L63",
      "file": "people/jordan_rivera"
    }
  ]
}
```

---

## What NOT to dump in

- **Raw email threads** — too noisy. Summarise to key signals.
- **Full meeting transcripts** — too long. Extract decisions and action items.
- **Duplicate information** — if it's in a project file, don't also put it in context.md.
- **FYI threads that didn't require action** — not worth the noise.

The goal is a knowledge base Claude can query and reason from, not an archive.
High signal-to-noise is more important than completeness.

---

## Testing that it worked

Start the assistant and try:

```
> What do you know about Jordan Rivera?
> What's the status of the Copilot integration project?
> What were the main things that happened in the last 2 months?
> What decisions did I make about headcount?
```

Claude should call `read_memory` and `search_memory` automatically and give you
specific, grounded answers from your files — not generic responses.
