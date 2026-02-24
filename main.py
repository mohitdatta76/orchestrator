#!/usr/bin/env python3
"""
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

import sys
from pathlib import Path

import anthropic

from config import Config
from skill_loader import SkillLoader
import tools as tool_module
from manager import memory_store


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def load_system_prompt(path: str) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    print(f"[warn] system prompt file not found: {path!r} — using default")
    return "You are a helpful assistant."


def build_system_prompt(base: str, active_skills: list[dict]) -> str:
    if not active_skills:
        return base
    skill_sections = "\n\n".join(
        f"## Skill: {s['name']}\n\n{s['content']}" for s in active_skills
    )
    return f"{base}\n\n---\n\n# Active Skills\n\n{skill_sections}"


def resolve_tools(base_tool_names: list[str], active_skills: list[dict]) -> list[dict]:
    """Union of base tools + tools requested by active skills."""
    enabled = set(base_tool_names)
    for skill in active_skills:
        enabled.update(skill.get("tools", []))
    return tool_module.get_tools(list(enabled))


def print_help():
    print(__doc__)


# ------------------------------------------------------------------
# Agentic loop (handles recursive tool calls)
# ------------------------------------------------------------------

def run_turn(
    client: anthropic.Anthropic,
    messages: list[dict],
    system_prompt: str,
    active_tools: list[dict],
    config: Config,
) -> str:
    """
    Run one user turn to completion, executing tool calls as needed.
    Returns the final text response.
    """
    while True:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system_prompt,
            messages=messages,
            tools=active_tools,
        )

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # No more tool calls — extract text
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return text

        # Handle tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  [tool] {block.name}({_summarise_input(block.input)})")
            result = tool_module.execute(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({"role": "user", "content": tool_results})
        # Loop back to get next response


def _summarise_input(inp: dict) -> str:
    """One-line summary of tool input for display."""
    parts = []
    for k, v in inp.items():
        s = str(v)
        parts.append(f"{k}={s[:60]!r}{'...' if len(s) > 60 else ''}")
    return ", ".join(parts)


# ------------------------------------------------------------------
# Main REPL
# ------------------------------------------------------------------

def main():
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=config.api_key)
    loader = SkillLoader(config.skills_dir, mcp_servers_file=config.mcp_servers_file)
    memory_store.initialize_memory()

    print("Agent Orchestrator")
    print(f"  model    : {config.model}")
    print(f"  data     : {config.data_dir}")
    print(f"  skills   : {config.skills_dir}/  ({len(loader.list_skills())} loaded)")
    if loader._mcp_sources:
        print(f"  mcp      : {len(loader._mcp_sources)} server(s) from {config.mcp_servers_file}")
    print(f"  prompt   : {config.system_prompt_file}")
    print("Type /help for commands, or 'exit' to quit.\n")

    messages: list[dict] = []
    # Skills pinned for the next turn only (via /skill <name>)
    pinned_skills: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # ---------- REPL commands ----------

        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if user_input in ("/help", "/?"):
            print_help()
            continue

        if user_input == "/clear":
            messages.clear()
            pinned_skills.clear()
            print("[conversation cleared]")
            continue

        if user_input.startswith("/model"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 2:
                config.model = parts[1].strip()
                print(f"[model set to {config.model}]")
            else:
                print(f"[current model: {config.model}]")
            continue

        if user_input.startswith("/skills"):
            parts = user_input.split()
            if len(parts) > 1 and parts[1] == "reload":
                loader.reload()
            else:
                skill_list = loader.list_skills()
                if not skill_list:
                    print("  (no skills found)")
                else:
                    for s in skill_list:
                        always_tag = " [always]" if s["always"] else ""
                        print(f"  {s['name']}{always_tag}: {s['description']}")
            continue

        if user_input.startswith("/skill "):
            name = user_input[7:].strip()
            skill = loader.get(name)
            if skill:
                pinned_skills.append(skill)
                print(f"[skill '{name}' pinned for next turn]")
            else:
                print(f"[skill '{name}' not found — try /skills to list available skills]")
            continue

        if user_input == "/tools":
            active_skills = loader.match(user_input) + pinned_skills
            active_tools = resolve_tools(config.base_tools, active_skills)
            print("  " + ", ".join(t["name"] for t in active_tools))
            continue

        if user_input == "/system":
            base = load_system_prompt(config.system_prompt_file)
            active_skills = loader.match(user_input) + pinned_skills
            print(build_system_prompt(base, active_skills))
            continue

        # ---------- Agent turn ----------

        # Determine active skills for this turn
        auto_skills = loader.match(user_input)
        active_skills = pinned_skills + [
            s for s in auto_skills if s not in pinned_skills
        ]
        pinned_skills = []  # consume pinned skills

        if active_skills:
            names = ", ".join(s["name"] for s in active_skills)
            print(f"  [skills: {names}]")

        base_prompt = load_system_prompt(config.system_prompt_file)
        system_prompt = build_system_prompt(base_prompt, active_skills)
        active_tools = resolve_tools(config.base_tools, active_skills)

        messages.append({"role": "user", "content": user_input})

        try:
            reply = run_turn(client, messages, system_prompt, active_tools, config)
            print(f"\nAssistant: {reply}\n")
        except anthropic.APIError as e:
            print(f"[API error] {e}")
            # Roll back the last user message so the conversation stays valid
            messages.pop()


if __name__ == "__main__":
    main()
