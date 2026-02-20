import re
from pathlib import Path
from typing import Optional

import yaml


class SkillLoader:
    """
    Loads skills from markdown files with YAML frontmatter.

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

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, dict] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self):
        self._skills.clear()
        if not self.skills_dir.exists():
            return
        for path in sorted(self.skills_dir.glob("*.md")):
            skill = self._parse(path)
            if skill:
                self._skills[skill["name"]] = skill

    def _parse(self, path: Path) -> Optional[dict]:
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
            "path": str(path),
        }

    def reload(self):
        """Reload all skills from disk."""
        self._load_all()
        print(f"[skill_loader] Loaded {len(self._skills)} skill(s): "
              f"{', '.join(self._skills) or 'none'}")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict]:
        return sorted(self._skills.values(), key=lambda s: -s["priority"])

    def get(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def match(self, user_message: str) -> list[dict]:
        """
        Return skills relevant to *user_message*, sorted by priority.

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

            # Explicit invocation
            if (f"@{skill['name']}" in user_message
                    or f"/skill:{skill['name']}" in user_message):
                matched.append(skill)
                continue

            # Keyword triggers
            for trigger in skill["triggers"]:
                if trigger in msg_lower:
                    matched.append(skill)
                    break

        return sorted(matched, key=lambda s: -s["priority"])
