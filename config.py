import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    api_key: str
    data_dir: str
    model: str = "claude-opus-4-6"
    max_tokens: int = 8096
    system_prompt_file: str = "system_prompt.md"
    skills_dir: str = "skills"
    mcp_servers_file: str = "mcp_servers.md"
    base_tools: list = field(default_factory=lambda: [
        "bash", "read_file", "write_file", "list_files", "search_files"
    ])

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        data_dir = os.getenv("DATA_DIR")
        if not data_dir:
            raise ValueError(
                "DATA_DIR is not set. "
                "Set it in .env to a directory outside the source tree, e.g. DATA_DIR=/home/you/orchestrator-data"
            )

        raw_tools = os.getenv("BASE_TOOLS", "bash,read_file,write_file,list_files,search_files")
        base_tools = [t.strip() for t in raw_tools.split(",") if t.strip()]

        return cls(
            api_key=api_key,
            data_dir=data_dir,
            model=os.getenv("MODEL", "claude-opus-4-6"),
            max_tokens=int(os.getenv("MAX_TOKENS", "8096")),
            system_prompt_file=os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.md"),
            skills_dir=os.getenv("SKILLS_DIR", "skills"),
            mcp_servers_file=os.getenv("MCP_SERVERS_FILE", "mcp_servers.md"),
            base_tools=base_tools,
        )
