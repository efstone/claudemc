"""
Minecraft log parsers.

Extensible parsing system for Minecraft server log events.
Each event type has its own parser function that returns a typed dict or None.
"""

import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

# US Eastern timezone
EASTERN = ZoneInfo('America/Detroit')


@dataclass
class ChatMessage:
    """Parsed chat message from Minecraft log."""
    username: str
    content: str
    timestamp: datetime  # timezone-aware (America/Detroit)


# Pattern for chat messages: [HH:MM:SS] [Async Chat Thread - #N/INFO]: <username> message
CHAT_PATTERN = re.compile(
    r'^\[(\d{2}:\d{2}:\d{2})\] '  # timestamp
    r'\[Async Chat Thread - #\d+/INFO\]: '  # thread info
    r'<(\w+)> '  # username
    r'(.+)$'  # message content
)


def parse_chat(line: str, log_date: Optional[date] = None) -> Optional[ChatMessage]:
    """
    Parse a chat message from a log line.

    Args:
        line: A single line from the Minecraft server log.
        log_date: The date to use for the timestamp. Defaults to today.

    Returns:
        ChatMessage if the line is a chat message, None otherwise.
    """
    match = CHAT_PATTERN.match(line.strip())
    if not match:
        return None

    time_str, username, content = match.groups()

    # Combine time from log with provided date (or today in Eastern time)
    if log_date is None:
        log_date = datetime.now(EASTERN).date()

    time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
    timestamp = datetime.combine(log_date, time_obj, tzinfo=EASTERN)

    return ChatMessage(
        username=username,
        content=content,
        timestamp=timestamp
    )
