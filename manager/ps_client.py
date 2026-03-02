"""
ps_client.py — runs PowerShell scripts via pwsh and returns parsed JSON.

pwsh (PowerShell Core) works on macOS, Linux, and Windows.
Install: https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell
"""

import json
import shutil
import subprocess
from pathlib import Path

# Repo-relative location of the PS scripts
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "ps"


def _pwsh_available() -> bool:
    return shutil.which("pwsh") is not None


def run_script(script_name: str, params: dict | None = None, timeout: int = 60) -> dict | list:
    """
    Run a .ps1 script from scripts/ps/ and return the parsed JSON output.

    Args:
        script_name: filename, e.g. "get_calendar.ps1"
        params:      optional dict of -ParamName value pairs passed to the script
        timeout:     seconds before killing the process

    Returns:
        Parsed JSON (dict or list)

    Raises:
        RuntimeError: if pwsh is not installed, script fails, or output isn't valid JSON
    """
    if not _pwsh_available():
        raise RuntimeError(
            "pwsh (PowerShell Core) is not installed or not on PATH.\n"
            "Install from: https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell"
        )

    script_path = _SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise RuntimeError(f"PS script not found: {script_path}")

    cmd = ["pwsh", "-NonInteractive", "-NoProfile", "-File", str(script_path)]

    if params:
        for k, v in params.items():
            cmd += [f"-{k}", str(v)]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Script {script_name} failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Script {script_name} produced no output")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Script {script_name} output is not valid JSON: {e}\n{stdout[:500]}")


# ------------------------------------------------------------------
# Convenience functions — one per data source
# ------------------------------------------------------------------

def fetch_calendar(days: int = 7) -> list[dict]:
    """Calendar events for the next `days` days."""
    data = run_script("get_calendar.ps1", {"Days": days})
    return data if isinstance(data, list) else []


def fetch_direct_reports() -> dict:
    """Your profile + direct reports (two levels deep)."""
    return run_script("get_direct_reports.ps1")


def fetch_email(days: int = 3) -> dict:
    """Flagged, high-priority, and direct-unread emails for the last `days` days."""
    return run_script("get_email.ps1", {"Days": days})


def fetch_people(top: int = 25) -> list[dict]:
    """Top N people Graph considers most relevant to you."""
    data = run_script("get_people.ps1", {"Top": top})
    return data.get("people", []) if isinstance(data, dict) else []


def fetch_teams_mentions(days: int = 3) -> list[dict]:
    """Teams chat messages where you were @mentioned in the last `days` days."""
    data = run_script("get_teams_mentions.ps1", {"Days": days})
    return data.get("mentions", []) if isinstance(data, dict) else []
