import platform
import subprocess

from .base import Tool


class RunCommandTool(Tool):
    """Executes a shell or PowerShell command on the host running the agent.

    Opt-in only (must be listed under tools.enabled in config.yaml) since
    this is what lets the agent actually apply a Kubernetes manifest,
    run git, call the GitHub CLI, etc. - not just generate files.
    """

    name = "run_command"
    description = (
        "Run a shell command (bash on Linux/macOS, PowerShell on Windows unless "
        "shell='cmd' is given) on the host and return combined stdout/stderr. "
        "Use for things like 'kubectl apply -f ...', 'git push', 'gh workflow run', etc. "
        "Timeout is 120 seconds."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command line to execute"},
            "cwd": {"type": "string", "description": "Working directory, relative to output dir. Optional."},
        },
        "required": ["command"],
    }

    def __init__(self, output_dir):
        self._output_dir = output_dir

    def run(self, command: str, cwd: str = ".") -> str:
        workdir = (self._output_dir / cwd).resolve()
        workdir.mkdir(parents=True, exist_ok=True)

        if platform.system() == "Windows":
            args = ["powershell", "-NoProfile", "-Command", command]
        else:
            args = ["bash", "-lc", command]

        result = subprocess.run(
            args,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return f"(exit code {result.returncode})\n{output}".strip()
