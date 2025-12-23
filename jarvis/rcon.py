"""
RCON client for communicating with the Minecraft server.
"""

from mcrcon import MCRcon

from django.conf import settings

from .commands import validate_command, CommandNotAllowedError


class RconError(Exception):
    """Base exception for RCON errors."""
    pass


def send_command(command: str, validate: bool = True) -> str:
    """
    Send a command to the Minecraft server via RCON.

    Args:
        command: The command to send (without leading slash).
        validate: Whether to validate against the command whitelist.

    Returns:
        The server's response.

    Raises:
        CommandNotAllowedError: If the command is not in the whitelist.
        RconError: If there's a connection or communication error.
    """
    if validate:
        validate_command(command)  # Raises CommandNotAllowedError if invalid

    try:
        with MCRcon(
            host=settings.RCON_HOST,
            password=settings.RCON_PASSWORD,
            port=settings.RCON_PORT
        ) as mcr:
            response = mcr.command(command)
            return response
    except Exception as e:
        raise RconError(f"RCON error: {e}") from e


def say(message: str) -> str:
    """Send a chat message to the server. Splits long messages automatically."""
    # Sanitize message - remove any command injection attempts
    safe_message = message.replace('"', "'").replace('\n', ' ')

    # Minecraft limit is 256 chars total, "say " prefix is 4 chars, leave buffer
    max_length = 240
    responses = []

    # Split into chunks if too long
    while safe_message:
        chunk = safe_message[:max_length]
        safe_message = safe_message[max_length:]

        # Try to break at a space if there's more to send
        if safe_message and ' ' in chunk:
            last_space = chunk.rfind(' ')
            if last_space > max_length // 2:  # Only break if space is in latter half
                safe_message = chunk[last_space+1:] + safe_message
                chunk = chunk[:last_space]

        responses.append(send_command(f'say {chunk}'))

    return ' | '.join(responses) if responses else ''


def give(player: str, item: str, amount: int = 1) -> str:
    """Give an item to a player."""
    return send_command(f'give {player} {item} {amount}')


def teleport(player: str, destination: str) -> str:
    """Teleport a player to a destination (coordinates or another player)."""
    return send_command(f'tp {player} {destination}')

def set_time(action: str, value: str) -> str:
    """Set or query the world time (day/night or numerical value)."""
    return send_command(f'time {action} {value}')


def weather(precipitation: str, duration: str = None) -> str:
    """Set the world weather (clear/rain/thunder)."""
    # Workaround: '/weather clear' only lasts briefly before rain returns.
    # Starting a 1-tick thunderstorm that "ends naturally" gives longer clear weather.
    if precipitation == 'clear':
        return send_command('weather thunder 1')
    if duration:
        return send_command(f'weather {precipitation} {duration}')
    return send_command(f'weather {precipitation}')
