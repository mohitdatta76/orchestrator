#!/usr/bin/env python3
"""
seed_ces.py — find and seed all synthesis files under ce_* directories.

Usage:
    python seed_ces.py                  # scans all ce_* dirs in current directory
    python seed_ces.py ce_2_20          # specific directory
    python seed_ces.py --dry-run        # preview without writing
"""

import subprocess
import sys
from pathlib import Path


def find_synthesis_files(root: Path) -> list[Path]:
    weekly = sorted(root.rglob("*_weekly_synthesis.json"))
    daily  = sorted(root.rglob("*_daily_synthesis.json"))
    # Weekly first (broad context), then daily (detail)
    return weekly + daily


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if args:
        roots = [Path(a) for a in args]
    else:
        roots = sorted(Path(".").glob("ce_*"))

    if not roots:
        print("No ce_* directories found.")
        sys.exit(1)

    files = []
    for root in roots:
        files.extend(find_synthesis_files(root))

    if not files:
        print("No synthesis files found.")
        sys.exit(1)

    print(f"Found {len(files)} synthesis file(s):\n")
    for f in files:
        print(f"  {f}")
    print()

    for f in files:
        cmd = [sys.executable, "seed.py", "--file", str(f)] + flags
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"[error] seed.py failed on {f} — stopping.")
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
