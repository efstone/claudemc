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
# Bedrock players show as: [HH:MM:SS] [Async Chat Thread - #N/INFO]: [Not Secure] <.username> message
CHAT_PATTERN = re.compile(
    r'^\[(\d{2}:\d{2}:\d{2})\] '  # timestamp
    r'\[Async Chat Thread - #\d+/INFO\]: '  # thread info
    r'(?:\[Not Secure\] )?'  # optional [Not Secure] prefix for Bedrock
    r'<([\w.]+)> '  # username (allowing dots for Bedrock)
    r'(.+)$'  # message content
)


@dataclass
class PlayerPosition:
    """Parsed player position."""
    username: str
    x: int
    y: int
    z: int


# Pattern for RCON response: <player> has the following entity data: [...]
# No timestamp prefix - this is the direct RCON response
RCON_POSITION_PATTERN = re.compile(
    r'^(\w+) has the following entity data: '  # username
    r'\[(.+)\]$'  # coordinate data in brackets
)


def parse_position_from_rcon(response: str) -> Optional[PlayerPosition]:
    """
    Parse player position from an RCON response.

    The RCON response looks like:
    username has the following entity data: [ ;3m42.865 ;9md , ;3m-17.369 ;9md , ;3m1627.268 ;9md ]

    Args:
        response: The RCON response string from 'data get entity <player> Pos'.

    Returns:
        PlayerPosition if the response contains position data, None otherwise.
    """
    match = RCON_POSITION_PATTERN.match(response.strip())
    if not match:
        return None

    username, coords_raw = match.groups()

    # Clean up the coordinate string
    # Remove 'd' suffix (double type indicator), color codes, and spaces
    coords_clean = coords_raw
    coords_clean = re.sub(r'd\b', '', coords_clean)  # Remove 'd' suffix from numbers
    coords_clean = re.sub(r';[0-9]+m?d?', '', coords_clean)  # Remove ;3m, ;9md color codes
    coords_clean = coords_clean.replace(' ', '')  # Remove spaces

    # Split by comma and parse as floats, then truncate to int
    try:
        parts = coords_clean.split(',')
        if len(parts) != 3:
            return None
        x = int(float(parts[0]))
        y = int(float(parts[1]))
        z = int(float(parts[2]))
    except (ValueError, IndexError):
        return None

    return PlayerPosition(
        username=username,
        x=x,
        y=y,
        z=z
    )


@dataclass
class PlayerLogin:
    """Parsed player login event with coordinates."""
    username: str
    x: int
    y: int
    z: int
    timestamp: datetime


# Pattern for player login: [HH:MM:SS] [Server thread/INFO]: PlayerName[/IP:port] logged in with entity id X at (X.X, Y.Y, Z.Z)
LOGIN_PATTERN = re.compile(
    r'^\[(\d{2}:\d{2}:\d{2})\] '  # timestamp
    r'\[Server thread/INFO\]: '  # thread info
    r'(\w+)\[.+\] logged in with entity id \d+ at '  # username
    r'\((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\)'  # coordinates
)


def parse_login(line: str, log_date: Optional[date] = None) -> Optional[PlayerLogin]:
    """
    Parse a player login event from a log line.

    Args:
        line: A single line from the Minecraft server log.
        log_date: The date to use for the timestamp. Defaults to today.

    Returns:
        PlayerLogin if the line is a login event, None otherwise.
    """
    match = LOGIN_PATTERN.match(line.strip())
    if not match:
        return None

    time_str, username, x_str, y_str, z_str = match.groups()

    # Combine time from log with provided date (or today in Eastern time)
    if log_date is None:
        log_date = datetime.now(EASTERN).date()

    time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
    timestamp = datetime.combine(log_date, time_obj, tzinfo=EASTERN)

    return PlayerLogin(
        username=username,
        x=int(float(x_str)),
        y=int(float(y_str)),
        z=int(float(z_str)),
        timestamp=timestamp
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
