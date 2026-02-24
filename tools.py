import subprocess
from pathlib import Path
from typing import Any


# ------------------------------------------------------------------
# Tool schemas (Anthropic tool_use format)
# ------------------------------------------------------------------

TOOLS = [
    {
        "name": "bash",
        "description": (
            "Run a bash command and return stdout + stderr. "
            "Use for running scripts, compiling, testing, package management, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full text content of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (or overwrite) a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory, optionally filtered by a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list (default: current directory)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern, e.g. '*.py' (default: '*')",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search for a regex/text pattern inside files using grep. "
            "Returns matching lines with file name and line number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex to search for"},
                "path": {
                    "type": "string",
                    "description": "Directory or file to search (default: current directory)",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Limit search to files matching this glob, e.g. '*.py'",
                },
            },
            "required": ["pattern"],
        },
    },
]

# Build a lookup by name for fast filtering
_TOOL_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOLS}


def get_tools(names: list[str]) -> list[dict]:
    """Return Anthropic tool schemas for the given tool names."""
    return [_TOOL_BY_NAME[n] for n in names if n in _TOOL_BY_NAME]


# ------------------------------------------------------------------
# Tool execution
# ------------------------------------------------------------------

def execute(name: str, params: dict) -> Any:
    """Dispatch a tool call and return a string result."""
    try:
        match name:
            case "bash":
                return _bash(params)
            case "read_file":
                return _read_file(params)
            case "write_file":
                return _write_file(params)
            case "list_files":
                return _list_files(params)
            case "search_files":
                return _search_files(params)
            case _:
                return f"Error: unknown tool '{name}'"
    except Exception as e:
        return f"Error in {name}: {e}"


def _bash(params: dict) -> str:
    result = subprocess.run(
        params["command"],
        shell=True,
        capture_output=True,
        text=True,
        timeout=params.get("timeout", 30),
    )
    parts = []
    if result.stdout:
        parts.append(result.stdout.rstrip())
    if result.stderr:
        parts.append(f"[stderr]\n{result.stderr.rstrip()}")
    if result.returncode != 0:
        parts.append(f"[exit code: {result.returncode}]")
    return "\n".join(parts) if parts else "(no output)"


def _read_file(params: dict) -> str:
    p = Path(params["path"])
    if not p.exists():
        return f"Error: file not found: {p}"
    return p.read_text(encoding="utf-8")


def _write_file(params: dict) -> str:
    p = Path(params["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(params["content"], encoding="utf-8")
    return f"Wrote {len(params['content'])} chars to {p}"


def _list_files(params: dict) -> str:
    root = Path(params.get("path") or ".")
    pattern = params.get("pattern") or "*"
    if not root.exists():
        return f"Error: path not found: {root}"
    entries = sorted(root.glob(pattern))
    if not entries:
        return "No files found."
    lines = []
    for e in entries:
        tag = "dir " if e.is_dir() else "file"
        size = e.stat().st_size if e.is_file() else 0
        lines.append(f"[{tag}] {e}  ({size:,} bytes)" if e.is_file() else f"[{tag}] {e}")
    return "\n".join(lines)


def _search_files(params: dict) -> str:
    cmd = ["grep", "-rn", params["pattern"], params.get("path") or "."]
    fp = params.get("file_pattern")
    if fp:
        cmd += ["--include", fp]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 1:
        return "No matches found."
    if result.returncode != 0:
        return f"grep error: {result.stderr.strip()}"
    return result.stdout.strip() or "No matches found."
