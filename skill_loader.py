import re
from pathlib import Path
from typing import Optional

import yaml

from manager.mcp_skills import load_mcp_servers


class SkillLoader:
    """
    Loads skills from two sources, merged into a single registry:

    1. Local files — skills/*.md (YAML frontmatter + markdown body)
    2. MCP servers — prompts exposed by remote MCP servers via JSON-RPC

    Local skills take precedence: if a remote skill has the same name as a
    local one, the local version wins.

    Skill file format (skills/my_skill.md):

        ---
        name: my_skill
        description: What this skill does
        triggers:
          - keyword1
          - keyword2
        tools:
          - bash
          - read_file
        always: false
        priority: 10
        ---

        # Skill content injected into system prompt when active.
        You are an expert at...
    """

    def __init__(self, skills_dir: str, mcp_servers_file: str = "mcp_servers.md"):
        self.skills_dir = Path(skills_dir)
        self._mcp_sources = load_mcp_servers(mcp_servers_file)
        self._skills: dict[str, dict] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self):
        self._skills.clear()

        # 1. Local skills (highest precedence)
        local: dict[str, dict] = {}
        if self.skills_dir.exists():
            for path in sorted(self.skills_dir.glob("*.md")):
                skill = self._parse_file(path)
                if skill:
                    local[skill["name"]] = skill
        self._skills.update(local)

        # 2. Remote MCP skills (only added if name not already taken by local)
        for source in self._mcp_sources:
            remote_skills = source.fetch_skills()
            added = 0
            for skill in remote_skills:
                if skill["name"] not in self._skills:
                    self._skills[skill["name"]] = skill
                    added += 1
            if remote_skills:
                n_total = len(remote_skills)
                n_skipped = n_total - added
                msg = f"[mcp_skills] {source.url}: loaded {added}/{n_total} skill(s)"
                if n_skipped:
                    msg += f" ({n_skipped} overridden by local)"
                print(msg)

    def _parse_file(self, path: Path) -> Optional[dict]:
        text = path.read_text(encoding="utf-8")

        # Extract YAML frontmatter between --- delimiters
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not m:
            return None

        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            print(f"[skill_loader] YAML error in {path.name}: {e}")
            return None

        name = meta.get("name")
        if not name:
            print(f"[skill_loader] Skipping {path.name}: missing 'name' in frontmatter")
            return None

        body = text[m.end():].strip()

        return {
            "name": str(name),
            "description": str(meta.get("description", "")),
            "triggers": [str(t).lower() for t in meta.get("triggers", [])],
            "tools": [str(t) for t in meta.get("tools", [])],
            "always": bool(meta.get("always", False)),
            "priority": int(meta.get("priority", 0)),
            "content": body,
            "source": "local",
        }

    def reload(self):
        """Reload all skills — re-reads local files and re-fetches from MCP servers."""
        self._load_all()
        local_count = sum(1 for s in self._skills.values() if s.get("source") == "local")
        remote_count = len(self._skills) - local_count
        parts = [f"{local_count} local"]
        if remote_count:
            parts.append(f"{remote_count} remote")
        print(f"[skill_loader] Loaded {len(self._skills)} skill(s): {', '.join(parts)}")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict]:
        return sorted(self._skills.values(), key=lambda s: -s["priority"])

    def get(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def match(self, user_message: str) -> list[dict]:
        """
        Return skills relevant to user_message, sorted by priority.

        Selection rules (in order):
          1. always=true  → always included
          2. Explicit invocation: @skill-name or /skill:skill-name in message
          3. Trigger keyword appears in the message (case-insensitive)
        """
        msg_lower = user_message.lower()
        matched: list[dict] = []

        for skill in self._skills.values():
            if skill["always"]:
                matched.append(skill)
                continue

            if (f"@{skill['name']}" in user_message
                    or f"/skill:{skill['name']}" in user_message):
                matched.append(skill)
                continue

            for trigger in skill["triggers"]:
                if trigger in msg_lower:
                    matched.append(skill)
                    break

        return sorted(matched, key=lambda s: -s["priority"])
