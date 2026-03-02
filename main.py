#!/usr/bin/env python3
"""Agent Orchestrator — entry point."""

import sys

import anthropic

from config import Config
from skill_loader import SkillLoader
from manager import memory_store
from orchestrator import Orchestrator


def main():
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=config.api_key)
    loader = SkillLoader(config.skills_dir, mcp_servers_file=config.mcp_servers_file)
    memory_store.initialize_memory()

    Orchestrator(config, client, loader).run()


if __name__ == "__main__":
    main()
