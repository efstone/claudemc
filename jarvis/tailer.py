"""
Log file tailer using subprocess.

Uses `tail -F` to follow the Minecraft server log file and yields
parsed events as they occur.
"""

import subprocess
from typing import Iterator, Optional

from django.conf import settings

from .parsers import parse_chat, ChatMessage


def tail_chat(log_path: Optional[str] = None) -> Iterator[ChatMessage]:
    """
    Tail a Minecraft log file and yield chat messages as they appear.

    Uses `tail -F` which follows by filename, so it handles log rotation
    (when the server restarts and creates a new latest.log).

    Args:
        log_path: Path to the Minecraft server's latest.log file.
                  Defaults to settings.MINECRAFT_LOG_PATH.

    Yields:
        ChatMessage objects as chat lines appear in the log.
    """
    if log_path is None:
        log_path = settings.MINECRAFT_LOG_PATH

    proc = subprocess.Popen(
        ['tail', '-F', log_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )

    try:
        for line in proc.stdout:
            message = parse_chat(line)
            if message:
                yield message
    finally:
        proc.terminate()
        proc.wait()
