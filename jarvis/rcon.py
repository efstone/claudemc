"""
RCON client for communicating with the Minecraft server.
"""

import re
from dataclasses import dataclass
from typing import Optional

from mcrcon import MCRcon

from django.conf import settings

from .commands import validate_command, CommandNotAllowedError
from .parsers import parse_position_from_rcon, parse_dimension_from_rcon, PlayerPosition


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
            print(f"  -> RCON sent: {command}")
            print(f"  -> RCON response: {repr(response)}")
            return response
    except Exception as e:
        raise RconError(f"RCON error: {e}") from e


def split_message(message: str, max_chunk_length: int = 200, max_chunks: int = 3) -> list[str]:
    """
    Split a message into chunks without breaking words.

    Args:
        message: The message to split.
        max_chunk_length: Maximum characters per chunk.
        max_chunks: Maximum number of chunks to create.

    Returns:
        List of message chunks.
    """
    chunks = []
    remaining = message.strip()

    while remaining and len(chunks) < max_chunks:
        if len(remaining) <= max_chunk_length:
            chunks.append(remaining)
            break

        # Find a good break point (space) within the limit
        chunk = remaining[:max_chunk_length]
        last_space = chunk.rfind(' ')

        if last_space > max_chunk_length // 2:
            # Break at the space
            chunks.append(chunk[:last_space])
            remaining = remaining[last_space + 1:]
        else:
            # No good space found, just cut at limit (rare edge case)
            chunks.append(chunk)
            remaining = remaining[max_chunk_length:]

        remaining = remaining.strip()

    return chunks


def say(message: str) -> str:
    """Send a chat message to the server using tellraw. Splits long messages into max 3 parts."""
    # Sanitize message - escape quotes and remove newlines
    safe_message = message.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')

    # Split into chunks (max 200 chars each, max 3 chunks)
    chunks = split_message(safe_message, max_chunk_length=200, max_chunks=3)

    responses = []
    for chunk in chunks:
        responses.append(send_command(f'tellraw @a {{"text":"[Jarvis] {chunk}"}}'))

    return ' | '.join(responses) if responses else ''


def give(player: str, item: str, amount: int = 1) -> str:
    """Give an item to a player."""
    return send_command(f'give {player} {item} {amount}')


# Regex to detect coordinate destinations (e.g., "100 64 -200", "-50 70 300")
_COORDINATE_PATTERN = re.compile(r'^-?\d+\s+-?\d+\s+-?\d+$')


def teleport(player: str, destination: str, dimension: str = 'overworld') -> str:
    """
    Teleport a player to a destination (coordinates or another player).

    For coordinate destinations, uses 'execute as <player> in minecraft:<dimension> run teleport'
    to ensure the teleport lands in the correct dimension.
    For player-name destinations, uses plain 'tp' since Minecraft handles cross-dimension natively.
    """
    if _COORDINATE_PATTERN.match(destination.strip()):
        # Coordinate teleport — use execute to target the correct dimension
        return send_command(
            f'execute as {player} in minecraft:{dimension} run teleport {player} {destination}'
        )
    else:
        # Player-to-player teleport — plain tp handles cross-dimension
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


def give_loot(player: str, loot_table: str = 'minecraft:chests/simple_dungeon') -> str:
    """
    Give random loot from a loot table to a player.

    Args:
        player: The player's username.
        loot_table: The loot table to use. Defaults to simple_dungeon.

    Returns:
        RCON response.
    """
    return send_command(f'loot give {player} loot {loot_table}')


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
            print(f"  -> DEBUG: Failed to parse position from response")
            return None

        return position

    except RconError:
        return None


def get_player_dimension(player: str) -> Optional[str]:
    """
    Get a player's current dimension by querying entity data via RCON.

    Sends 'data get entity <player> Dimension' and parses the response.

    Args:
        player: The player's username.

    Returns:
        Dimension string (e.g., 'overworld', 'the_nether', 'the_end') if found, None otherwise.
    """
    try:
        response = send_command(f'data get entity {player} Dimension')
        result = parse_dimension_from_rcon(response)
        if result is None:
            print(f"  -> DEBUG: Failed to parse dimension from response: {repr(response)}")
            return None
        return result.dimension
    except RconError:
        return None


@dataclass
class SaveLocationResult:
    """Result of saving a location."""
    success: bool
    message: str
    location_name: Optional[str] = None
    coordinates: Optional[str] = None


def _rcon_send(sock, packet_type: int, payload: str, request_id: int = 1) -> str:
    """Send an RCON packet and receive response. Thread-safe (no signals)."""
    import struct

    # Build packet: length (4) + request_id (4) + type (4) + payload + null + null
    payload_bytes = payload.encode('utf-8') + b'\x00\x00'
    packet = struct.pack('<iii', request_id, packet_type, 0)[:8]
    packet = struct.pack('<i', len(payload_bytes) + 8) + struct.pack('<ii', request_id, packet_type) + payload_bytes

    sock.send(packet)

    # Receive response
    response_data = sock.recv(4096)
    if len(response_data) < 12:
        return ''

    # Parse response: length (4) + request_id (4) + type (4) + payload + nulls
    response_payload = response_data[12:-2].decode('utf-8', errors='ignore')
    return response_payload


def send_command_threadsafe(command: str) -> str:
    """
    Send an RCON command using raw sockets. Thread-safe (no signals).

    Use this from background threads instead of send_command().
    """
    import socket

    RCON_LOGIN = 3
    RCON_COMMAND = 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect((settings.RCON_HOST, settings.RCON_PORT))

    # Login
    _rcon_send(sock, RCON_LOGIN, settings.RCON_PASSWORD)

    # Send command
    response = _rcon_send(sock, RCON_COMMAND, command)

    sock.close()
    return response


def get_player_position_threadsafe(player: str) -> Optional[PlayerPosition]:
    """
    Get a player's current position using raw sockets. Thread-safe (no signals).

    Args:
        player: The player's username.

    Returns:
        PlayerPosition if found, None otherwise.
    """
    import socket

    RCON_LOGIN = 3
    RCON_COMMAND = 2

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((settings.RCON_HOST, settings.RCON_PORT))

        # Login
        _rcon_send(sock, RCON_LOGIN, settings.RCON_PASSWORD)

        # Send data command
        response = _rcon_send(sock, RCON_COMMAND, f'data get entity {player} Pos')

        sock.close()

        # Parse the response
        position = parse_position_from_rcon(response)
        return position

    except Exception as e:
        print(f"  -> get_player_position_threadsafe error: {e}")
        return None


def get_online_players() -> list[str]:
    """
    Get a list of currently online players.

    Thread-safe version using raw sockets (no MCRcon library, no signals).

    Returns:
        List of player usernames, empty list if none online.
    """
    import socket

    RCON_LOGIN = 3
    RCON_COMMAND = 2

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((settings.RCON_HOST, settings.RCON_PORT))

        # Login
        _rcon_send(sock, RCON_LOGIN, settings.RCON_PASSWORD)

        # Send 'list' command
        response = _rcon_send(sock, RCON_COMMAND, 'list')

        sock.close()

        print(f"  -> list response: {repr(response)}")
        # Response format: "There are X of a max of Y players online: Player1, Player2"
        if ':' in response:
            players_part = response.split(':', 1)[1].strip()
            if players_part:
                return [p.strip() for p in players_part.split(',') if p.strip()]
        return []
    except Exception as e:
        print(f"  -> get_online_players error: {e}")
        return []


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

    # Query player's current dimension
    dimension = get_player_dimension(player) or 'overworld'

    # Create the location
    try:
        location = Location.objects.create(
            name=name,
            x=position.x,
            y=position.y,
            z=position.z,
            dimension=dimension,
            description=description or ''
        )

        # Build success message
        coords_str = f"{position.x} {position.y} {position.z}"
        dim_label = f" in {dimension}" if dimension != 'overworld' else ""
        if description:
            success_msg = f"Saved location '{name}' at {coords_str}{dim_label}. Description: {description}"
        else:
            success_msg = f"Saved location '{name}' at {coords_str}{dim_label}!"

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
