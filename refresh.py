#!/usr/bin/env python3
"""
Daily context refresh script.

Fetches recent emails, calendar, and Teams messages, then uses Claude to
distill the information into structured memory updates:
  - action_items.json  (new items, closed items)
  - projects.json      (status changes)
  - context.md         (narrative summary prepended)
  - memory/briefing_YYYY-MM-DD.md  (today's pre-built briefing)

Usage:
  python refresh.py                 # refresh last 24h (default)
  python refresh.py --since 48h     # refresh last 48h
  python refresh.py --since week    # refresh last 7 days
  python refresh.py --dry-run       # fetch and print without writing

This script is designed to run headlessly as a cron job.
See cron_manager.py to enable/disable the scheduled run.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from config import Config
from manager.graph_client import GraphClient
from manager import memory_store
from manager.tools_graph import GRAPH_TOOLS, execute as graph_execute


DISTILL_SYSTEM_PROMPT = """You are a chief-of-staff assistant for a Microsoft M2 engineering manager.

You will be given a dump of recent emails, calendar events, and Teams messages.
Your job is to extract structured intelligence and return it as a JSON object.

Return ONLY valid JSON matching this schema exactly — no prose, no markdown fences:

{
  "action_items_patch": {
    "add": [
      {
        "id": null,
        "title": "short imperative action title",
        "due": "YYYY-MM-DD or null",
        "owner": "me or person name",
        "context": "one sentence: what meeting/email this came from",
        "status": "open"
      }
    ],
    "close": [],
    "update": []
  },
  "project_updates": [
    {
      "name": "project name",
      "status": "on_track|at_risk|blocked|done",
      "notes": "brief update",
      "risks": ["..."],
      "blockers": ["..."]
    }
  ],
  "context_summary": "2-4 sentence narrative of the most important things that happened today. What moved, what's at risk, what decisions were made.",
  "urgent_flags": [
    "one-liner for each item needing same-day attention"
  ]
}

Rules:
- Only extract action items that are clear asks or commitments — not vague FYIs.
- Only include project updates where there's actual new information.
- Keep context_summary factual and specific.
- urgent_flags should be 0–4 items maximum. If nothing is urgent, return [].
"""


def parse_args():
    p = argparse.ArgumentParser(description="Daily manager context refresh")
    p.add_argument("--since", default="24h", choices=["24h", "48h", "week"],
                   help="How far back to fetch (default: 24h)")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and print without writing to memory")
    return p.parse_args()


def since_to_days(since: str) -> int:
    return {"24h": 1, "48h": 2, "week": 7}[since]


def build_data_payload(days: int) -> str:
    """Fetch all data sources and format as a single text payload for Claude."""
    client = GraphClient()
    sections = []

    print(f"  Fetching emails (last {days}d)...", end=" ", flush=True)
    emails = client.get_emails(days=days, max_results=30)
    print(f"{len(emails)} emails")
    if emails:
        email_lines = [f"## Recent Emails ({len(emails)})\n"]
        for e in emails:
            read_tag = "" if e.get("is_read") else " [UNREAD]"
            imp_tag = " [HIGH IMPORTANCE]" if e.get("importance") == "high" else ""
            email_lines.append(
                f"From: {e.get('from', '?')}{imp_tag}{read_tag}\n"
                f"Subject: {e.get('subject', '?')}\n"
                f"Time: {e.get('received', '?')}\n"
                f"Preview: {e.get('preview', '')}\n"
            )
        sections.append("\n".join(email_lines))

    print(f"  Fetching calendar (last {days}d + next 2d)...", end=" ", flush=True)
    events = client.get_calendar(days_ahead=2, days_back=days)
    print(f"{len(events)} events")
    if events:
        cal_lines = [f"## Calendar Events ({len(events)})\n"]
        for e in events:
            attendees = ", ".join(e.get("attendees", [])[:6])
            cal_lines.append(
                f"Meeting: {e.get('subject', '?')}\n"
                f"Time: {e.get('start', '?')} → {e.get('end', '?')}\n"
                f"Organiser: {e.get('organizer', '?')} | Attendees: {attendees}\n"
                f"Notes: {e.get('notes', '')}\n"
            )
        sections.append("\n".join(cal_lines))

    print(f"  Fetching Teams messages (last {days}d)...", end=" ", flush=True)
    messages = client.get_teams_messages(days=days)
    print(f"{len(messages)} messages")
    if messages:
        teams_lines = [f"## Teams Messages ({len(messages)})\n"]
        for m in messages:
            mention_tag = " [@MENTION]" if m.get("is_mention") else ""
            msg_type = "DM" if m.get("type") == "chat" else "Channel"
            teams_lines.append(
                f"[{msg_type}]{mention_tag} From: {m.get('from', '?')} at {m.get('timestamp', '?')}\n"
                f"{m.get('body', '')}\n"
            )
        sections.append("\n".join(teams_lines))

    return "\n\n---\n\n".join(sections)


def call_claude_distill(client: anthropic.Anthropic, config: Config, data: str) -> dict:
    """Call Claude to extract structured intelligence from the raw data."""
    user_message = (
        f"Here is the manager's data for the last refresh period:\n\n{data}\n\n"
        "Also, today's date is: " + datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".\n"
        "Extract structured intelligence and return as JSON."
    )

    response = client.messages.create(
        model=config.model,
        max_tokens=4096,
        system=DISTILL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    return json.loads(text)


def apply_updates(distilled: dict, dry_run: bool) -> None:
    """Write distilled intelligence to memory files."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Action items
    ai_patch = distilled.get("action_items_patch", {})
    if any(ai_patch.get(k) for k in ("add", "close", "update")):
        if not dry_run:
            result = memory_store.update_memory("action_items", ai_patch)
            print(f"  [action_items] {result}")
        else:
            added = len(ai_patch.get("add", []))
            closed = len(ai_patch.get("close", []))
            print(f"  [DRY-RUN] action_items: +{added} added, -{closed} closed")

    # Projects
    for proj in distilled.get("project_updates", []):
        if not dry_run:
            patch = {"projects": [proj]}
            memory_store.update_memory("projects", patch)
            print(f"  [projects] Updated: {proj.get('name', '?')} → {proj.get('status', '?')}")
        else:
            print(f"  [DRY-RUN] project: {proj.get('name', '?')} → {proj.get('status', '?')}")

    # Context narrative
    summary = distilled.get("context_summary", "").strip()
    if summary:
        if not dry_run:
            memory_store.update_memory("context", summary)
            print(f"  [context] Narrative updated.")
        else:
            print(f"  [DRY-RUN] context: {summary[:120]}...")

    # Urgent flags — print always
    flags = distilled.get("urgent_flags", [])
    if flags:
        print("\n  ⚠️  Urgent flags:")
        for f in flags:
            print(f"     • {f}")

    # Write daily briefing file
    if not dry_run:
        briefing_path = Path("memory") / f"briefing_{today}.md"
        urgent_section = "\n".join(f"- {f}" for f in flags) if flags else "Nothing urgent."
        ai_add = ai_patch.get("add", [])
        ai_section = "\n".join(
            f"- {item.get('title', '?')} (due: {item.get('due', 'TBD')})"
            for item in ai_add
        ) if ai_add else "No new action items logged."

        briefing_content = (
            f"# Daily Briefing — {today}\n\n"
            f"*Generated by refresh.py at {datetime.now(timezone.utc).strftime('%H:%M UTC')}*\n\n"
            f"## Urgent\n\n{urgent_section}\n\n"
            f"## New action items logged today\n\n{ai_section}\n\n"
            f"## Summary\n\n{summary}\n\n"
            f"---\n\n*Ask the assistant for a full briefing or meeting prep.*\n"
        )
        briefing_path.parent.mkdir(parents=True, exist_ok=True)
        briefing_path.write_text(briefing_content, encoding="utf-8")
        print(f"  [briefing] Written to {briefing_path}")


def main():
    args = parse_args()
    days = since_to_days(args.since)

    print(f"\n{'='*55}")
    print(f"Manager context refresh — last {args.since}")
    if args.dry_run:
        print("DRY-RUN mode: no files will be written")
    print(f"{'='*55}\n")

    # Load config
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=config.api_key)

    # Ensure memory directory exists
    memory_store.initialize_memory()

    print("Fetching data sources:")
    data_payload = build_data_payload(days)

    if not data_payload.strip():
        print("No data retrieved. Check your GRAPH_ACCESS_TOKEN or mock mode.")
        sys.exit(1)

    print("\nDistilling with Claude...")
    try:
        distilled = call_claude_distill(client, config, data_payload)
    except json.JSONDecodeError as e:
        print(f"Claude returned invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error calling Claude: {e}")
        sys.exit(1)

    print("\nApplying updates:")
    apply_updates(distilled, dry_run=args.dry_run)

    print(f"\n✓ Refresh complete — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
