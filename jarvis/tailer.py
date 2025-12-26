"""
Log file tailer using subprocess.

Uses `tail -F` to follow the Minecraft server log file and yields
parsed events as they occur.
"""

import subprocess
from dataclasses import dataclass
from typing import Iterator, Optional, Union

from django.conf import settings

from .parsers import parse_chat, parse_login, ChatMessage, PlayerLogin


@dataclass
class LogEvent:
    """Wrapper for log events with type info."""
    event_type: str  # 'chat' or 'login'
    data: Union[ChatMessage, PlayerLogin]


def tail_log(log_path: Optional[str] = None) -> Iterator[LogEvent]:
    """
    Tail a Minecraft log file and yield parsed events as they appear.

    Uses `tail -F` which follows by filename, so it handles log rotation
    (when the server restarts and creates a new latest.log).

    Args:
        log_path: Path to the Minecraft server's latest.log file.
                  Defaults to settings.MINECRAFT_LOG_PATH.

    Yields:
        LogEvent objects for chat messages and login events.
    """
    if log_path is None:
        log_path = settings.MINECRAFT_LOG_PATH

    proc = subprocess.Popen(
        ['tail', '-F', '-n', '0', log_path],  # -n 0: start at end, don't read existing lines
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )

    try:
        for line in proc.stdout:
            # Try parsing as chat message
            chat = parse_chat(line)
            if chat:
                yield LogEvent(event_type='chat', data=chat)
                continue

            # Try parsing as login event
            login = parse_login(line)
            if login:
                yield LogEvent(event_type='login', data=login)
    finally:
        proc.terminate()
        proc.wait()


def tail_chat(log_path: Optional[str] = None) -> Iterator[ChatMessage]:
    """
    Tail a Minecraft log file and yield chat messages as they appear.

    Legacy wrapper around tail_log for backwards compatibility.
    """
    for event in tail_log(log_path):
        if event.event_type == 'chat':
            yield event.data
