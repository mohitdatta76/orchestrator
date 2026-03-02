"""Orchestrator class — owns the REPL loop and agentic tool loop."""

from pathlib import Path

import anthropic

from config import Config
from skill_loader import SkillLoader
import tools as tool_module

_HELP = """\
Agent Orchestrator
==================
A minimal but extensible agent loop for experimenting with Anthropic models.

Usage:
    python main.py

REPL commands:
    /skills          - List all available skills
    /skills reload   - Reload skills from disk
    /skill <name>    - Force-activate a skill for the next turn
    /model <name>    - Switch the model mid-session
    /tools           - Show currently enabled tools
    /system          - Show the active system prompt
    /clear           - Clear conversation history
    /help            - Show this help
    exit / quit      - Exit
"""


class Orchestrator:
    def __init__(self, config: Config, client: anthropic.Anthropic, loader: SkillLoader):
        self.config = config
        self.client = client
        self.loader = loader
        self.messages: list[dict] = []
        self.pinned_skills: list[dict] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the REPL; blocks until the user exits."""
        print("Agent Orchestrator")
        print(f"  model    : {self.config.model}")
        print(f"  data     : {self.config.data_dir}")
        print(f"  skills   : {self.config.skills_dir}/  ({len(self.loader.list_skills())} loaded)")
        if self.loader._mcp_sources:
            print(f"  mcp      : {len(self.loader._mcp_sources)} server(s) from {self.config.mcp_servers_file}")
        print(f"  prompt   : {self.config.system_prompt_file}")
        print("Type /help for commands, or 'exit' to quit.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            if self._handle_command(user_input):
                continue

            # ---------- Agent turn ----------
            auto_skills = self.loader.match(user_input)
            active_skills = self.pinned_skills + [
                s for s in auto_skills if s not in self.pinned_skills
            ]
            self.pinned_skills = []  # consume pinned skills

            if active_skills:
                names = ", ".join(s["name"] for s in active_skills)
                print(f"  [skills: {names}]")

            base_prompt = self._load_system_prompt(self.config.system_prompt_file)
            system_prompt = self._build_system_prompt(base_prompt, active_skills)
            active_tools = self._resolve_tools(self.config.base_tools, active_skills)

            self.messages.append({"role": "user", "content": user_input})

            try:
                reply = self._run_turn(system_prompt, active_tools)
                print(f"\nAssistant: {reply}\n")
            except anthropic.APIError as e:
                print(f"[API error] {e}")
                self.messages.pop()

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def _handle_command(self, user_input: str) -> bool:
        """Return True if the input was a REPL command (consumed), False otherwise."""
        if user_input in ("/help", "/?"):
            self._print_help()
            return True

        if user_input == "/clear":
            self._cmd_clear()
            return True

        if user_input.startswith("/model"):
            parts = user_input.split(maxsplit=1)
            self._cmd_model(parts[1].strip() if len(parts) == 2 else None)
            return True

        if user_input.startswith("/skills"):
            parts = user_input.split()
            self._cmd_skills(parts[1] if len(parts) > 1 else None)
            return True

        if user_input.startswith("/skill "):
            self._cmd_skill(user_input[7:].strip())
            return True

        if user_input == "/tools":
            self._cmd_tools()
            return True

        if user_input == "/system":
            self._cmd_system()
            return True

        return False

    # ------------------------------------------------------------------
    # Individual command implementations
    # ------------------------------------------------------------------

    def _cmd_clear(self) -> None:
        self.messages.clear()
        self.pinned_skills.clear()
        print("[conversation cleared]")

    def _cmd_model(self, arg: str | None) -> None:
        if arg:
            self.config.model = arg
            print(f"[model set to {self.config.model}]")
        else:
            print(f"[current model: {self.config.model}]")

    def _cmd_skills(self, arg: str | None) -> None:
        if arg == "reload":
            self.loader.reload()
        else:
            skill_list = self.loader.list_skills()
            if not skill_list:
                print("  (no skills found)")
            else:
                for s in skill_list:
                    always_tag = " [always]" if s["always"] else ""
                    print(f"  {s['name']}{always_tag}: {s['description']}")

    def _cmd_skill(self, name: str) -> None:
        skill = self.loader.get(name)
        if skill:
            self.pinned_skills.append(skill)
            print(f"[skill '{name}' pinned for next turn]")
        else:
            print(f"[skill '{name}' not found — try /skills to list available skills]")

    def _cmd_tools(self) -> None:
        active_skills = self.loader.match("/tools") + self.pinned_skills
        active_tools = self._resolve_tools(self.config.base_tools, active_skills)
        print("  " + ", ".join(t["name"] for t in active_tools))

    def _cmd_system(self) -> None:
        base = self._load_system_prompt(self.config.system_prompt_file)
        active_skills = self.loader.match("/system") + self.pinned_skills
        print(self._build_system_prompt(base, active_skills))

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    def _run_turn(self, system_prompt: str, active_tools: list[dict]) -> str:
        """Run one user turn to completion, executing tool calls as needed.
        Returns the final text response."""
        while True:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system_prompt,
                messages=self.messages,
                tools=active_tools,
            )

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                return text

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"  [tool] {block.name}({self._summarise_input(block.input)})")
                result = tool_module.execute(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

            self.messages.append({"role": "user", "content": tool_results})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_system_prompt(path: str) -> str:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
        print(f"[warn] system prompt file not found: {path!r} — using default")
        return "You are a helpful assistant."

    @staticmethod
    def _build_system_prompt(base: str, active_skills: list[dict]) -> str:
        if not active_skills:
            return base
        skill_sections = "\n\n".join(
            f"## Skill: {s['name']}\n\n{s['content']}" for s in active_skills
        )
        return f"{base}\n\n---\n\n# Active Skills\n\n{skill_sections}"

    @staticmethod
    def _resolve_tools(base_tool_names: list[str], active_skills: list[dict]) -> list[dict]:
        """Union of base tools + tools requested by active skills."""
        enabled = set(base_tool_names)
        for skill in active_skills:
            enabled.update(skill.get("tools", []))
        return tool_module.get_tools(list(enabled))

    @staticmethod
    def _summarise_input(inp: dict) -> str:
        """One-line summary of tool input for display."""
        parts = []
        for k, v in inp.items():
            s = str(v)
            parts.append(f"{k}={s[:60]!r}{'...' if len(s) > 60 else ''}")
        return ", ".join(parts)

    def _print_help(self) -> None:
        print(_HELP)
