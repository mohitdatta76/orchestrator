"""
MCP skill source — fetches skills from a remote MCP server's prompts endpoint.

MCP servers expose reusable prompt templates via:
  prompts/list  → list available prompts (name + description)
  prompts/get   → retrieve a specific prompt's content

Skill prompt content should be a markdown skill file with YAML frontmatter,
same format as local skills/*.md files:

    ---
    name: my_remote_skill
    description: Does something useful
    always: true
    priority: 80
    tools:
      - read_memory
    ---

    You are an expert at...

If a prompt has no YAML frontmatter, it is still loaded as a skill using the
prompt's name and description as metadata and the full text as content.

Configure in .env:
  MCP_SKILL_SERVERS=https://your-server.com/mcp,https://other-server.com/mcp
  MCP_SKILL_AUTH_TOKEN=your-bearer-token   (optional, shared across all servers)
"""

import re
from pathlib import Path
from typing import Optional

import requests
import yaml


def load_mcp_servers(path: str | Path) -> list["MCPSkillSource"]:
    """
    Parse an mcp_servers.md file and return one MCPSkillSource per [MCP_SERVER] block.

    Format:
        [MCP_SERVER]
        ServerURL = https://example.com/mcp
        AuthToken = optional-bearer-token   # omit if not needed

    Lines starting with # are comments. Unknown keys are ignored.
    Blocks missing ServerURL are skipped with a warning.
    Returns an empty list if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return []

    sources = []
    current: dict[str, str] = {}

    def _flush(block: dict) -> None:
        url = block.get("serverurl", "").strip()
        if not url:
            return
        token = block.get("authtoken", "").strip() or None
        sources.append(MCPSkillSource(url, auth_token=token))

    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        if line == "[MCP_SERVER]":
            if current:
                _flush(current)
            current = {}
            continue

        if "=" in line and current is not None:
            key, _, value = line.partition("=")
            # Strip inline comments
            value = value.split("#")[0].strip()
            current[key.strip().lower()] = value

    if current:
        _flush(current)

    return sources


class MCPSkillSource:
    """
    Fetches skills from a single MCP server using JSON-RPC over HTTP.
    Errors are non-fatal: if the server is unreachable, an empty list is returned.
    """

    def __init__(self, url: str, auth_token: Optional[str] = None, timeout: int = 5):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if auth_token:
            self._headers["Authorization"] = f"Bearer {auth_token}"
        self._req_id = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_skills(self) -> list[dict]:
        """
        Return all skills available on this MCP server.
        Returns an empty list (with a warning) if the server is unreachable or errors.
        """
        try:
            result = self._rpc("prompts/list")
        except Exception as e:
            print(f"[mcp_skills] {self.url}: could not list prompts — {e}")
            return []

        skills = []
        for prompt_meta in result.get("prompts", []):
            skill = self._fetch_one(prompt_meta)
            if skill:
                skills.append(skill)
        return skills

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        """Make a JSON-RPC 2.0 call and return the result."""
        self._req_id += 1
        body: dict = {"jsonrpc": "2.0", "id": self._req_id, "method": method}
        if params:
            body["params"] = params
        resp = requests.post(self.url, json=body, headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data.get("result", {})

    def _fetch_one(self, prompt_meta: dict) -> Optional[dict]:
        name = prompt_meta.get("name", "").strip()
        if not name:
            return None
        try:
            result = self._rpc("prompts/get", {"name": name})
        except Exception as e:
            print(f"[mcp_skills] {self.url}: could not fetch prompt '{name}' — {e}")
            return None

        text = self._extract_text(result)
        return self._parse(name, prompt_meta.get("description", ""), text)

    def _extract_text(self, result: dict) -> str:
        """Pull plain text from a prompts/get result."""
        for msg in result.get("messages", []):
            content = msg.get("content", {})
            if isinstance(content, dict) and content.get("type") == "text":
                return content.get("text", "")
            if isinstance(content, str):
                return content
        return result.get("description", "")

    def _parse(self, name: str, description: str, text: str) -> Optional[dict]:
        """
        Build a skill dict from prompt content.

        Tries YAML frontmatter first (preferred — full control over all fields).
        Falls back to plain text with prompt metadata as defaults.
        """
        if not text.strip():
            return None

        # Attempt YAML frontmatter parse (same format as local skills/*.md)
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
                body = text[m.end():].strip()
                return {
                    "name": str(meta.get("name", name)),
                    "description": str(meta.get("description", description)),
                    "triggers": [str(t).lower() for t in meta.get("triggers", [])],
                    "tools": [str(t) for t in meta.get("tools", [])],
                    "always": bool(meta.get("always", False)),
                    "priority": int(meta.get("priority", 0)),
                    "content": body,
                    "source": f"mcp:{self.url}",
                }
            except yaml.YAMLError as e:
                print(f"[mcp_skills] YAML error in prompt '{name}': {e}")

        # No frontmatter — use prompt metadata, full text as content
        return {
            "name": name,
            "description": description,
            "triggers": [],
            "tools": [],
            "always": False,
            "priority": 0,
            "content": text.strip(),
            "source": f"mcp:{self.url}",
        }
