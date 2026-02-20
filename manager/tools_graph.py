"""
Tool schemas and execution for O365 Graph API tools.

Follows the same pattern as tools.py — each tool has:
  - A schema dict (Anthropic tool_use format)
  - An execute() handler

Tools exposed:
  fetch_emails     — recent emails from Outlook
  fetch_calendar   — upcoming/recent calendar events
  fetch_teams      — recent Teams chats and channel messages
  fetch_transcript — transcript for a named meeting
"""

import json
from datetime import datetime, timezone

from manager.graph_client import GraphClient
from manager import memory_store

_client: GraphClient | None = None


def _get_client() -> GraphClient:
    global _client
    if _client is None:
        _client = GraphClient()
    return _client


# ------------------------------------------------------------------
# Tool schemas
# ------------------------------------------------------------------

GRAPH_TOOLS = [
    {
        "name": "fetch_emails",
        "description": (
            "Fetch recent emails from Outlook. Returns a structured summary of each email "
            "including sender, subject, timestamp, importance, and a body preview. "
            "Use this to understand what has landed in the inbox recently."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to fetch (default: 1)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of emails to return (default: 20, max: 50)",
                },
                "filter_importance": {
                    "type": "string",
                    "enum": ["all", "high", "normal"],
                    "description": "Filter by importance level (default: all)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "fetch_calendar",
        "description": (
            "Fetch calendar events — upcoming meetings and recent past meetings. "
            "Returns event title, time, attendees, organiser, and any notes. "
            "Use this to understand the day/week schedule and prepare for meetings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to look (default: 2)",
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to include (default: 1)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "fetch_teams",
        "description": (
            "Fetch recent Microsoft Teams messages — both 1:1 chats and channel messages. "
            "Highlights @mentions. Use this to catch up on async communication and "
            "identify anything that needs a response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to fetch (default: 1)",
                },
                "chats_only": {
                    "type": "boolean",
                    "description": "If true, only return 1:1 chats (exclude channels)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "fetch_transcript",
        "description": (
            "Fetch the transcript or notes for a specific meeting, identified by its subject/title. "
            "Useful for recapping what was discussed and what action items were agreed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "meeting_subject": {
                    "type": "string",
                    "description": "The subject/title of the meeting to retrieve a transcript for",
                },
            },
            "required": ["meeting_subject"],
        },
    },
    {
        "name": "read_memory",
        "description": (
            "Read a memory file that stores persistent context across sessions. "
            "Flat keys: 'people' (org roster), 'projects' (project statuses), "
            "'action_items' (open commitments), 'context' (rolling narrative), "
            "'decisions' (key decisions log), 'briefing_YYYY-MM-DD' (daily briefing). "
            "Per-person history: 'people/<alias>' e.g. 'people/jordan_rivera'. "
            "Per-project history: 'projects/<name>' e.g. 'projects/copilot_integration'. "
            "Use search_memory first if you don't know the exact key."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Memory key to read (people, projects, action_items, context, briefing_YYYY-MM-DD)",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "update_memory",
        "description": (
            "Update a memory file with new information. "
            "For 'context': provide a text string to prepend to the narrative log. "
            "For 'action_items': provide {add: [...], close: [ids], update: [...]}. "
            "For 'people' or 'projects': provide a dict to deep-merge into the existing data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Memory key to update (context, action_items, people, projects)",
                },
                "patch": {
                    "description": "The data to write. Type depends on key — see description.",
                },
            },
            "required": ["key", "patch"],
        },
    },
    {
        "name": "search_memory",
        "description": (
            "Search across all memory files for a keyword or phrase. "
            "Returns matching excerpts with file context. "
            "Use this to quickly find information about a person, project, or topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for",
                },
            },
            "required": ["query"],
        },
    },
]

GRAPH_TOOL_NAMES = {t["name"] for t in GRAPH_TOOLS}


# ------------------------------------------------------------------
# Tool execution
# ------------------------------------------------------------------

def execute(name: str, params: dict) -> str:
    """Dispatch a graph/memory tool call. Returns a string result."""
    try:
        match name:
            case "fetch_emails":
                return _fetch_emails(params)
            case "fetch_calendar":
                return _fetch_calendar(params)
            case "fetch_teams":
                return _fetch_teams(params)
            case "fetch_transcript":
                return _fetch_transcript(params)
            case "read_memory":
                return memory_store.read_memory(params["key"])
            case "update_memory":
                return memory_store.update_memory(params["key"], params["patch"])
            case "search_memory":
                return memory_store.search_memory(params["query"])
            case _:
                return f"Error: unknown graph tool '{name}'"
    except Exception as e:
        return f"Error in {name}: {e}"


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------

def _fetch_emails(params: dict) -> str:
    days = int(params.get("days", 1))
    max_results = min(int(params.get("max_results", 20)), 50)
    filter_imp = params.get("filter_importance", "all")

    emails = _get_client().get_emails(days=days, max_results=max_results)

    if filter_imp != "all":
        emails = [e for e in emails if e.get("importance") == filter_imp]

    if not emails:
        return f"No emails found in the last {days} day(s)."

    lines = [f"Emails — last {days} day(s) ({len(emails)} results):\n"]
    for i, e in enumerate(emails, 1):
        read_tag = "" if e.get("is_read") else " [UNREAD]"
        imp_tag = " [HIGH]" if e.get("importance") == "high" else ""
        lines.append(
            f"{i}. {e.get('subject', '(no subject)')}{read_tag}{imp_tag}\n"
            f"   From: {e.get('from', '?')} — {_fmt_time(e.get('received', ''))}\n"
            f"   {e.get('preview', '')[:250]}\n"
        )
    return "\n".join(lines)


def _fetch_calendar(params: dict) -> str:
    days_ahead = int(params.get("days_ahead", 2))
    days_back = int(params.get("days_back", 1))

    events = _get_client().get_calendar(days_ahead=days_ahead, days_back=days_back)

    if not events:
        return "No calendar events found."

    lines = [f"Calendar — {days_back}d back / {days_ahead}d ahead ({len(events)} events):\n"]
    for i, e in enumerate(events, 1):
        attendees = ", ".join(e.get("attendees", [])[:5])
        if len(e.get("attendees", [])) > 5:
            attendees += f" +{len(e['attendees']) - 5} more"
        lines.append(
            f"{i}. {e.get('subject', '(no title)')}\n"
            f"   {_fmt_time(e.get('start', ''))} → {_fmt_time(e.get('end', ''))}\n"
            f"   Organiser: {e.get('organizer', '?')} | Attendees: {attendees or 'just you'}\n"
            f"   Notes: {e.get('notes', '')[:150] or '(none)'}\n"
        )
    return "\n".join(lines)


def _fetch_teams(params: dict) -> str:
    days = int(params.get("days", 1))
    chats_only = bool(params.get("chats_only", False))

    messages = _get_client().get_teams_messages(days=days, chats_only=chats_only)

    if chats_only:
        messages = [m for m in messages if m.get("type") == "chat"]

    if not messages:
        return f"No Teams messages found in the last {days} day(s)."

    lines = [f"Teams messages — last {days} day(s) ({len(messages)} messages):\n"]
    for i, m in enumerate(messages, 1):
        mention_tag = " [@MENTION]" if m.get("is_mention") else ""
        msg_type = "DM" if m.get("type") == "chat" else "Channel"
        lines.append(
            f"{i}. [{msg_type}]{mention_tag} {m.get('from', '?')} — {_fmt_time(m.get('timestamp', ''))}\n"
            f"   {m.get('body', '')[:300]}\n"
        )
    return "\n".join(lines)


def _fetch_transcript(params: dict) -> str:
    subject = params.get("meeting_subject", "")
    if not subject:
        return "Error: meeting_subject is required."
    return _get_client().get_meeting_transcript(subject)


def _fmt_time(iso: str) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.date() == now.date():
            return f"Today {dt.strftime('%H:%M')}"
        elif (now.date() - dt.date()).days == 1:
            return f"Yesterday {dt.strftime('%H:%M')}"
        else:
            return dt.strftime("%b %d %H:%M")
    except (ValueError, AttributeError):
        return iso[:16]
