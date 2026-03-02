#!/usr/bin/env python3
"""
sync.py — fetch O365 data via PowerShell and seed it into memory.

Runs all data sources (or a subset) and writes results to DATA_DIR.
Safe to run repeatedly — all writes are idempotent.

Usage:
    python sync.py                         # fetch everything
    python sync.py --source calendar       # one source only
    python sync.py --dry-run               # print what would be fetched, no writes
    python sync.py --days 7                # override lookback window

Sources: calendar, reports, email, people, teams
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from config import Config
from manager import memory_store, ps_client


def _write(key: str, data, dry_run: bool) -> None:
    """Write data to a memory key (JSON). Prints what's happening either way."""
    if isinstance(data, (dict, list)):
        summary = (
            f"{len(data)} items" if isinstance(data, list)
            else ", ".join(f"{k}: {len(v) if isinstance(v, list) else v}" for k, v in list(data.items())[:4])
        )
    else:
        summary = str(data)[:80]

    print(f"  → {key}: {summary}")
    if not dry_run:
        memory_store.update_memory(key, data)


def sync_calendar(days: int, dry_run: bool) -> int:
    print("Fetching calendar...")
    events = ps_client.fetch_calendar(days=days)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days_ahead": days,
        "events": events,
    }
    _write("calendar", payload, dry_run)
    return len(events)


def sync_reports(dry_run: bool) -> int:
    print("Fetching direct reports...")
    data = ps_client.fetch_direct_reports()
    _write("org", data, dry_run)

    # Also merge into people.json so the assistant can look people up
    reports = data.get("reports", [])
    people_patch = {}
    for r in reports:
        alias = r.get("email", "").split("@")[0].lower().replace(".", "_")
        if alias:
            people_patch[alias] = {
                "name": r.get("name"),
                "email": r.get("email"),
                "title": r.get("title"),
                "department": r.get("department"),
                "direct_report": True,
            }
    if people_patch:
        _write("people", people_patch, dry_run)

    return len(reports)


def sync_email(days: int, dry_run: bool) -> int:
    print("Fetching email signals...")
    data = ps_client.fetch_email(days=days)
    _write("email_signals", data, dry_run)
    total = (
        len(data.get("flagged", []))
        + len(data.get("high_priority", []))
        + len(data.get("direct_unread", []))
    )
    return total


def sync_people(dry_run: bool) -> int:
    print("Fetching relevant people...")
    people = ps_client.fetch_people()
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "people": people,
    }
    _write("network_people", payload, dry_run)
    return len(people)


def sync_teams(days: int, dry_run: bool) -> int:
    print("Fetching Teams mentions...")
    mentions = ps_client.fetch_teams_mentions(days=days)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days_window": days,
        "mentions": mentions,
    }
    _write("teams_mentions", payload, dry_run)
    return len(mentions)


SOURCES = {
    "calendar": sync_calendar,
    "reports":  sync_reports,
    "email":    sync_email,
    "people":   sync_people,
    "teams":    sync_teams,
}


def main():
    parser = argparse.ArgumentParser(description="Sync O365 data into memory via PowerShell")
    parser.add_argument("--source", choices=list(SOURCES), help="Run only this source")
    parser.add_argument("--days", type=int, default=3, help="Lookback/lookahead window in days (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to memory")
    args = parser.parse_args()

    try:
        Config.from_env()   # validates DATA_DIR is set
        memory_store.initialize_memory()
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    if args.dry_run:
        print("[dry-run mode — no writes]\n")

    to_run = [args.source] if args.source else list(SOURCES)
    results = {}

    for name in to_run:
        fn = SOURCES[name]
        try:
            # Calendar uses days as lookahead; email/teams use it as lookback
            if name in ("calendar",):
                count = fn(days=7, dry_run=args.dry_run)
            elif name in ("email", "teams"):
                count = fn(days=args.days, dry_run=args.dry_run)
            else:
                count = fn(dry_run=args.dry_run)
            results[name] = f"ok ({count} items)"
        except RuntimeError as e:
            print(f"  [error] {e}")
            results[name] = f"error: {e}"

    print()
    print("Sync complete:")
    for name, status in results.items():
        print(f"  {name:12s} {status}")

    if not args.dry_run:
        # Write a brief sync summary to context so the assistant knows when data was refreshed
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary_lines = [f"O365 data synced at {ts}:"]
        for name, status in results.items():
            summary_lines.append(f"  - {name}: {status}")
        memory_store.update_memory("context", "\n".join(summary_lines))
        print("\nContext updated with sync timestamp.")


if __name__ == "__main__":
    main()
