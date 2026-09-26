from pathlib import Path

from .base import Tool
from .file_tools import ListDirectoryTool, ReadFileTool, WriteFileTool
from .shell_tools import RunCommandTool

# Maps config.yaml `tools.enabled` entries -> constructor.
# Add new tools here (and as a new module) to make them available.
_TOOL_BUILDERS = {
    "write_file": WriteFileTool,
    "read_file": ReadFileTool,
    "list_directory": ListDirectoryTool,
    "run_command": RunCommandTool,
}


def get_enabled_tools(enabled_names: list[str], output_dir: Path) -> list[Tool]:
    tools = []
    for name in enabled_names:
        builder = _TOOL_BUILDERS.get(name)
        if builder is None:
            raise ValueError(f"Unknown tool '{name}' in config.yaml tools.enabled")
        tools.append(builder(output_dir))
    return tools
