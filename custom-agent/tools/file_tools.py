from pathlib import Path

from .base import Tool


def _resolve_within(output_dir: Path, relative_path: str) -> Path:
    """Resolve `relative_path` under output_dir, refusing to escape it."""
    target = (output_dir / relative_path).resolve()
    if output_dir.resolve() not in target.parents and target != output_dir.resolve():
        raise ValueError(f"Path '{relative_path}' escapes the output directory")
    return target


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write text content to a file, relative to the agent's output directory. "
        "Creates parent directories as needed. Use this for generated manifests, "
        "workflow YAML, shell/PowerShell scripts, code, docs, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path, e.g. 'k8s/deployment.yaml'"},
            "content": {"type": "string", "description": "Full file content to write"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    def run(self, path: str, content: str) -> str:
        target = _resolve_within(self._output_dir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {target.relative_to(self._output_dir)}"


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a text file's contents, relative to the agent's output directory."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path to read"},
        },
        "required": ["path"],
    }

    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    def run(self, path: str) -> str:
        target = _resolve_within(self._output_dir, path)
        if not target.exists():
            return f"Error: {path} does not exist"
        return target.read_text(encoding="utf-8")


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List files and folders under a path relative to the agent's output directory."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path, '.' for the output root"},
        },
        "required": [],
    }

    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    def run(self, path: str = ".") -> str:
        target = _resolve_within(self._output_dir, path)
        if not target.exists():
            return f"Error: {path} does not exist"
        entries = sorted(p.relative_to(self._output_dir).as_posix() for p in target.rglob("*"))
        return "\n".join(entries) if entries else "(empty)"
