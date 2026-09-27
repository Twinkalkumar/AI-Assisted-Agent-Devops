import platform
from datetime import datetime

import psutil

from .base import Tool


class GetSystemMetricsTool(Tool):
    """Structured CPU/memory/disk/process snapshot, cross-platform.

    Exists so a small/local model doesn't have to guess the right
    top/free/ps/Get-Counter incantation for whatever OS it's running on -
    it gets one consistent, pre-parsed reading to reason over.
    """

    name = "get_system_metrics"
    description = (
        "Return a snapshot of this machine's CPU, memory, disk and top-process "
        "usage. Use this first when troubleshooting performance issues instead "
        "of guessing shell commands - works the same on Linux, macOS and Windows."
    )
    parameters = {
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "How many top processes to include, sorted by CPU usage. Default 5.",
            },
        },
        "required": [],
    }

    def __init__(self, output_dir):
        # No file access needed, but kept for a uniform constructor across tools.
        pass

    def run(self, top_n: int = 5) -> str:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")

        try:
            load1, load5, load15 = psutil.getloadavg()
            load_line = f"Load average (1/5/15m): {load1:.2f} / {load5:.2f} / {load15:.2f}"
        except (AttributeError, OSError):
            load_line = "Load average: not available on this OS"

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.sort(key=lambda p: p.get("cpu_percent") or 0, reverse=True)
        top_processes = processes[: max(top_n, 0)]
        process_lines = "\n".join(
            f"  PID {p['pid']:>6}  CPU {p.get('cpu_percent') or 0:5.1f}%  "
            f"MEM {p.get('memory_percent') or 0:5.1f}%  {p.get('name')}"
            for p in top_processes
        ) or "  (none)"

        return (
            f"Host: {platform.node()} ({platform.system()} {platform.release()})\n"
            f"Captured: {datetime.now().isoformat(timespec='seconds')}\n"
            f"CPU: {cpu_percent:.1f}% used across {cpu_count} logical cores\n"
            f"{load_line}\n"
            f"Memory: {mem.percent:.1f}% used "
            f"({mem.used // (1024**2)} MiB / {mem.total // (1024**2)} MiB)\n"
            f"Swap: {swap.percent:.1f}% used "
            f"({swap.used // (1024**2)} MiB / {swap.total // (1024**2)} MiB)\n"
            f"Disk (/): {disk.percent:.1f}% used "
            f"({disk.used // (1024**3)} GiB / {disk.total // (1024**3)} GiB)\n"
            f"Top {len(top_processes)} processes by CPU:\n{process_lines}"
        )
