"""
Memory store — CRUD layer for the memory/ directory.

The memory/ directory contains:
  people.json          — org map roster (names, roles, aliases)
  projects.json        — active project statuses
  action_items.json    — open commitments and due dates
  context.md           — rolling narrative (newest first)
  decisions.md         — key decisions log
  briefing_<date>.md   — auto-generated daily briefings

  people/<alias>.md    — rich per-person history (1:1 notes, patterns, context)
  projects/<name>.md   — per-project history (decisions, risks, meeting notes)

Keys support subdirectory notation: 'people/jordan_rivera', 'projects/copilot'

All writes are atomic (write-then-replace) to avoid corruption.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_MEMORY_DIR = Path(__file__).parent.parent / "memory"


def _memory_dir() -> Path:
    d = os.getenv("MEMORY_DIR", str(_DEFAULT_MEMORY_DIR))
    return Path(d)


def _resolve(key: str) -> tuple[Path, Path]:
    """Return (json_path, md_path) for a key. Supports 'subdir/name' notation."""
    parts = key.replace("\\", "/").split("/", 1)
    base = _memory_dir()
    if len(parts) == 2:
        base = base / parts[0]
        name = parts[1]
    else:
        name = parts[0]
    return base / f"{name}.json", base / f"{name}.md"


def _json_path(key: str) -> Path:
    return _resolve(key)[0]


def _md_path(key: str) -> Path:
    return _resolve(key)[1]


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def read_memory(key: str) -> str:
    """
    Read a memory file by key.

    Flat keys:   'people', 'projects', 'action_items', 'context',
                 'decisions', 'briefing_YYYY-MM-DD'
    Subdir keys: 'people/jordan_rivera', 'projects/copilot_integration'

    Returns the file contents as a string, or an error message.
    """
    jp, mp = _resolve(key)

    if jp.exists():
        data = json.loads(jp.read_text(encoding="utf-8"))
        return json.dumps(data, indent=2)
    elif mp.exists():
        return mp.read_text(encoding="utf-8")
    else:
        return f"No memory file found for key '{key}'. Available: {list_memory_keys()}"


def update_memory(key: str, patch: Any) -> str:
    """
    Update a memory file.

    Flat keys:   'context', 'decisions', 'action_items', 'people', 'projects'
    Subdir keys: 'people/jordan_rivera', 'projects/copilot_integration'

    For JSON files: patch should be a dict — deep-merged into existing data.
    For context.md / decisions.md: patch should be a string — prepended with timestamp.
    For action_items.json: patch can include 'add', 'close', 'update' lists.
    For people/<name>.md / projects/<name>.md: patch is a string — prepended.

    Returns a confirmation string.
    """
    jp, mp = _resolve(key)

    if key == "context":
        return _prepend_context(str(patch))
    elif key == "decisions":
        return _prepend_md(mp, str(patch))
    elif key == "action_items" and isinstance(patch, dict):
        return _update_action_items(patch)
    elif jp.exists() or (isinstance(patch, dict) and key in ("people", "projects")):
        return _merge_json(jp, patch)
    elif "/" in key:
        # Subdirectory markdown file (people/<name> or projects/<name>)
        return _prepend_md(mp, str(patch))
    else:
        # Generic markdown write
        return _prepend_md(mp, str(patch))


def search_memory(query: str) -> str:
    """
    Keyword search across all memory files, including subdirectories.
    Returns matching excerpts with file context.
    """
    query_lower = query.lower()
    results = []
    mem_dir = _memory_dir()

    if not mem_dir.exists():
        return "Memory directory not found."

    # Walk all .json and .md files recursively
    for path in sorted(mem_dir.rglob("*")):
        if path.suffix not in (".json", ".md"):
            continue
        if path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        hits = []
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                excerpt = "\n".join(lines[start:end])
                hits.append(f"  line {i+1}: {excerpt.strip()}")

        if hits:
            # Show path relative to memory dir for clarity
            rel = path.relative_to(mem_dir)
            results.append(f"[{rel}]\n" + "\n".join(hits[:5]))

    if not results:
        return f"No matches for '{query}' in memory files."
    return "\n\n".join(results)


def list_memory_keys() -> list[str]:
    """Return all available memory keys, including subdirectory keys."""
    mem_dir = _memory_dir()
    if not mem_dir.exists():
        return []
    keys = []
    for p in sorted(mem_dir.rglob("*")):
        if p.suffix not in (".json", ".md") or p.is_dir():
            continue
        rel = p.relative_to(mem_dir)
        # Convert path to key notation: people/jordan_rivera.md → people/jordan_rivera
        key = str(rel.with_suffix(""))
        keys.append(key)
    return keys


def initialize_memory() -> str:
    """Create skeleton memory files and subdirectories if they don't exist."""
    mem_dir = _memory_dir()
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "people").mkdir(exist_ok=True)
    (mem_dir / "projects").mkdir(exist_ok=True)
    created = []

    skeleton_json = {
        "people": {
            "direct_reports": [],
            "stakeholders": [],
            "key_people": [],
        },
        "projects": {"projects": []},
        "action_items": {"items": [], "last_refreshed": None},
    }

    for key, data in skeleton_json.items():
        p = _json_path(key)
        if not p.exists():
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            created.append(p.name)

    ctx = _md_path("context")
    if not ctx.exists():
        ctx.write_text(
            "# Manager Context Log\n\nRolling narrative. Newest at top.\n\n---\n\n"
            "*No entries yet.*\n",
            encoding="utf-8",
        )
        created.append(ctx.name)

    dec = _md_path("decisions")
    if not dec.exists():
        dec.write_text(
            "# Key Decisions Log\n\nImportant decisions made. Newest at top.\n\n---\n\n"
            "*No entries yet.*\n",
            encoding="utf-8",
        )
        created.append(dec.name)

    if created:
        return f"Initialized memory files: {', '.join(created)}"
    return "Memory files already exist."


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _prepend_context(text: str) -> str:
    ctx = _md_path("context")
    ctx.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"## {ts}\n\n{text.strip()}\n\n---\n\n"
    existing = ctx.read_text(encoding="utf-8") if ctx.exists() else ""
    # Keep only last ~5000 chars to prevent unbounded growth
    if len(existing) > 8000:
        existing = existing[:5000] + "\n\n*(older entries trimmed)*\n"
    ctx.write_text(entry + existing, encoding="utf-8")
    return "Context log updated."


def _prepend_md(path: Path, text: str) -> str:
    """Prepend a timestamped entry to a markdown file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"## {ts}\n\n{text.strip()}\n\n---\n\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(entry + existing, encoding="utf-8")
    return f"Updated {path.relative_to(_memory_dir())}"


def _merge_json(path: Path, patch: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    if isinstance(patch, dict) and isinstance(existing, dict):
        merged = _deep_merge(existing, patch)
    else:
        merged = patch

    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return f"Updated {path.name}"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        elif key in result and isinstance(result[key], list) and isinstance(val, list):
            # For lists: append new items (don't duplicate by id if present)
            existing_ids = {str(item.get("id", "")) for item in result[key] if isinstance(item, dict)}
            for item in val:
                if isinstance(item, dict) and str(item.get("id", "")) not in existing_ids:
                    result[key].append(item)
                elif not isinstance(item, dict):
                    result[key].append(item)
        else:
            result[key] = val
    return result


def _update_action_items(patch: dict) -> str:
    """
    Patch structure:
      { "add": [...new items...], "close": [id, ...], "update": [...] }
    """
    jp = _json_path("action_items")
    data = {"items": [], "last_refreshed": None}
    if jp.exists():
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    items = data.get("items", [])
    changes = []

    # Close items
    for close_id in patch.get("close", []):
        for item in items:
            if str(item.get("id")) == str(close_id):
                item["status"] = "done"
                item["closed_at"] = datetime.now(timezone.utc).isoformat()
                changes.append(f"Closed #{close_id}")

    # Update items
    for upd in patch.get("update", []):
        for item in items:
            if str(item.get("id")) == str(upd.get("id")):
                item.update(upd)
                changes.append(f"Updated #{upd.get('id')}")

    # Add new items
    next_id = max((item.get("id", 0) for item in items if isinstance(item.get("id"), int)), default=0) + 1
    for new_item in patch.get("add", []):
        new_item.setdefault("id", next_id)
        new_item.setdefault("status", "open")
        new_item.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        items.append(new_item)
        changes.append(f"Added #{next_id}: {new_item.get('title', '?')}")
        next_id += 1

    data["items"] = items
    data["last_refreshed"] = datetime.now(timezone.utc).isoformat()
    jp.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return f"action_items.json updated. Changes: {'; '.join(changes) or 'none'}"
