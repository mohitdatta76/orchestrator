#!/usr/bin/env python3
"""
Cron job manager for the daily context refresh.

Commands:
  python cron_manager.py enable    — add a 7am weekday cron job
  python cron_manager.py disable   — remove the cron job
  python cron_manager.py status    — show whether the cron is active
  python cron_manager.py run       — run a manual refresh right now

The cron job runs:  0 7 * * 1-5  (7:00am Mon–Fri)
It runs refresh.py from the same directory as this script.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

CRON_TAG = "# manager-assistant-refresh"
SCRIPT_DIR = Path(__file__).parent.resolve()
REFRESH_SCRIPT = SCRIPT_DIR / "refresh.py"
PYTHON = sys.executable


def _build_cron_line() -> str:
    """Build the full cron line with a unique tag for identification."""
    log_file = SCRIPT_DIR / "logs" / "refresh.log"
    return (
        f"0 7 * * 1-5 cd {SCRIPT_DIR} && {PYTHON} {REFRESH_SCRIPT} "
        f">> {log_file} 2>&1  {CRON_TAG}"
    )


def _read_crontab() -> str:
    """Read the current user's crontab. Returns empty string if none."""
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout
    # crontab -l returns exit code 1 when no crontab exists
    return ""


def _write_crontab(content: str) -> None:
    """Write the given content as the user's crontab."""
    proc = subprocess.run(
        ["crontab", "-"],
        input=content,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr.strip()}")


def cmd_enable() -> None:
    current = _read_crontab()

    if CRON_TAG in current:
        print("Cron job is already enabled.")
        _print_current(current)
        return

    new_line = _build_cron_line()
    log_dir = SCRIPT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    # Append to existing crontab (ensure trailing newline)
    separator = "\n" if current and not current.endswith("\n") else ""
    new_crontab = current + separator + new_line + "\n"
    _write_crontab(new_crontab)

    print("✓ Cron job enabled.")
    print(f"  Schedule : Monday–Friday at 7:00am")
    print(f"  Script   : {REFRESH_SCRIPT}")
    print(f"  Logs     : {log_dir / 'refresh.log'}")


def cmd_disable() -> None:
    current = _read_crontab()

    if CRON_TAG not in current:
        print("Cron job is not currently active.")
        return

    lines = [line for line in current.splitlines() if CRON_TAG not in line]
    new_crontab = "\n".join(lines) + ("\n" if lines else "")
    _write_crontab(new_crontab)
    print("✓ Cron job removed.")


def cmd_status() -> None:
    current = _read_crontab()

    if CRON_TAG in current:
        print("✓ Cron job is ACTIVE (Mon–Fri 7:00am)")
        _print_current(current)
    else:
        print("✗ Cron job is NOT active.")
        print("  Run: python cron_manager.py enable")


def cmd_run() -> None:
    """Run a manual refresh right now."""
    print("Running manual refresh...\n")
    result = subprocess.run(
        [PYTHON, str(REFRESH_SCRIPT)],
        cwd=str(SCRIPT_DIR),
    )
    sys.exit(result.returncode)


def _print_current(crontab: str) -> None:
    for line in crontab.splitlines():
        if CRON_TAG in line:
            print(f"  Entry: {line.strip()}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage the daily manager refresh cron job",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["enable", "disable", "status", "run"],
        help="Action to perform",
    )
    args = parser.parse_args()

    match args.command:
        case "enable":
            cmd_enable()
        case "disable":
            cmd_disable()
        case "status":
            cmd_status()
        case "run":
            cmd_run()


if __name__ == "__main__":
    main()
