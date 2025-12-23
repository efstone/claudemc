"""
RCON client for communicating with the Minecraft server.
"""

from dataclasses import dataclass
from typing import Optional

from mcrcon import MCRcon

from django.conf import settings

from .commands import validate_command, CommandNotAllowedError
from .parsers import parse_position_from_rcon, PlayerPosition


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


def get_player_position(player: str) -> Optional[PlayerPosition]:
    """
    Get a player's current position by querying entity data via RCON.

    Sends 'data get entity <player> Pos' and parses the response directly.

    Args:
        player: The player's username.

    Returns:
        PlayerPosition if found, None otherwise.
    """
    try:
        # Send the data command and get the response directly
        response = send_command(f'data get entity {player} Pos')

        # Parse the RCON response
        position = parse_position_from_rcon(response)

        if position is None:
            return None

        # Verify it's for the correct player (case-insensitive)
        if position.username.lower() != player.lower():
            return None

        return position

    except RconError:
        return None


@dataclass
class SaveLocationResult:
    """Result of saving a location."""
    success: bool
    message: str
    location_name: Optional[str] = None
    coordinates: Optional[str] = None


def save_player_location(
    player: str,
    name: str,
    description: str = ''
) -> SaveLocationResult:
    """
    Save a player's current location to the database.

    Performs duplicate checking:
    - Rejects if the location name already exists (case-insensitive)
    - Rejects if a location within 10 blocks of x OR z already exists

    Args:
        player: The player's username.
        name: The name for the location.
        description: Optional description for the location.

    Returns:
        SaveLocationResult with success status and message.
    """
    from .models import Location  # Import here to avoid circular import

    # Get the player's current position (latest matching entry from log)
    position = get_player_position(player)
    if position is None:
        error_msg = f"Could not get position for {player}. Make sure you're in the game!"
        say(error_msg)
        return SaveLocationResult(success=False, message=error_msg)

    # Check if location name already exists (case-insensitive)
    existing_name = Location.objects.filter(name__iexact=name).first()
    if existing_name:
        error_msg = f"Location '{name}' already exists at {existing_name.coordinates}. Choose a different name!"
        say(error_msg)
        return SaveLocationResult(success=False, message=error_msg)

    # Check for nearby locations (within 10 blocks of x OR z)
    # This prevents saving essentially the same spot with different names
    nearby_threshold = 10
    for loc in Location.objects.all():
        x_diff = abs(loc.x - position.x)
        z_diff = abs(loc.z - position.z)
        if x_diff <= nearby_threshold and z_diff <= nearby_threshold:
            error_msg = (
                f"There's already a location nearby! '{loc.name}' is at {loc.coordinates}, "
                f"only {x_diff} blocks away in X and {z_diff} blocks away in Z. "
                f"Move further away or use a different spot!"
            )
            say(error_msg)
            return SaveLocationResult(success=False, message=error_msg)

    # Create the location
    try:
        location = Location.objects.create(
            name=name,
            x=position.x,
            y=position.y,
            z=position.z,
            description=description or ''
        )

        # Build success message
        coords_str = f"{position.x} {position.y} {position.z}"
        if description:
            success_msg = f"Saved location '{name}' at {coords_str}. Description: {description}"
        else:
            success_msg = f"Saved location '{name}' at {coords_str}!"

        say(success_msg)
        return SaveLocationResult(
            success=True,
            message=success_msg,
            location_name=name,
            coordinates=coords_str
        )

    except Exception as e:
        error_msg = f"Failed to save location: {str(e)}"
        say(error_msg)
        return SaveLocationResult(success=False, message=error_msg)
