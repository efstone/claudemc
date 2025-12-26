"""
Explorer rewards system.

Gives random loot to players who are exploring far from known locations.
"""

import random
from dataclasses import dataclass
from math import sqrt
from typing import Optional

from django.utils import timezone

from .models import MinecraftPlayer, Location
from .rcon import get_player_position_threadsafe, get_online_players, send_command_threadsafe


# Minimum distance (blocks) from known locations to qualify as "exploring"
MIN_EXPLORER_DISTANCE = 250


@dataclass
class ExplorerRewardResult:
    """Result of attempting to give explorer rewards."""
    player: str
    success: bool
    reason: str
    distance_from_nearest_location: Optional[int] = None
    distance_from_login: Optional[int] = None


def calculate_distance(x1: int, z1: int, x2: int, z2: int) -> int:
    """Calculate 2D distance between two points (ignoring Y)."""
    return int(sqrt((x2 - x1) ** 2 + (z2 - z1) ** 2))


def get_distance_from_nearest_location(x: int, z: int) -> Optional[int]:
    """
    Calculate distance from coordinates to nearest saved location.

    Uses 2D distance (x, z) since y is vertical.

    Returns:
        Distance in blocks, or None if no locations exist.
    """
    locations = Location.objects.all()
    if not locations:
        return None

    min_distance = float('inf')
    for loc in locations:
        dist = calculate_distance(x, z, loc.x, loc.z)
        min_distance = min(min_distance, dist)

    return int(min_distance)


def try_give_explorer_reward(
    player: MinecraftPlayer,
    min_distance: int = MIN_EXPLORER_DISTANCE,
    chance: float = 0.25,
    loot_table: str = 'minecraft:chests/simple_dungeon'
) -> ExplorerRewardResult:
    """
    Attempt to give explorer rewards to a player.

    Checks:
    1. Player's current position can be retrieved
    2. Player is far enough from all saved Locations
    3. Player is far enough from their login position
    4. Player hasn't received loot in the last hour
    5. Random 25% chance

    Args:
        player: The MinecraftPlayer to reward.
        min_distance: Minimum distance from known locations (default 250 blocks).
        chance: Probability of giving loot (default 0.25 = 25%).
        loot_table: The Minecraft loot table to use.

    Returns:
        ExplorerRewardResult with success status and reason.
    """
    # Get player's current position via RCON
    current_pos = get_player_position_threadsafe(player.username)
    if current_pos is None:
        return ExplorerRewardResult(
            player=player.username,
            success=False,
            reason="Could not get current position"
        )

    # Check distance from nearest saved Location
    dist_from_location = get_distance_from_nearest_location(current_pos.x, current_pos.z)

    if dist_from_location is not None and dist_from_location < min_distance:
        return ExplorerRewardResult(
            player=player.username,
            success=False,
            reason=f"Too close to saved location ({dist_from_location} blocks)",
            distance_from_nearest_location=dist_from_location
        )

    # Check distance from player's login position
    dist_from_login = None
    if player.last_login_x is not None and player.last_login_z is not None:
        dist_from_login = calculate_distance(
            current_pos.x, current_pos.z,
            player.last_login_x, player.last_login_z
        )
        if dist_from_login < min_distance:
            return ExplorerRewardResult(
                player=player.username,
                success=False,
                reason=f"Too close to login position ({dist_from_login} blocks)",
                distance_from_nearest_location=dist_from_location,
                distance_from_login=dist_from_login
            )

    # Check cooldown (1 hour)
    if not player.can_receive_loot():
        return ExplorerRewardResult(
            player=player.username,
            success=False,
            reason="Loot cooldown active (received within last hour)",
            distance_from_nearest_location=dist_from_location,
            distance_from_login=dist_from_login
        )

    # Random chance check
    if random.random() > chance:
        return ExplorerRewardResult(
            player=player.username,
            success=False,
            reason=f"Random chance failed ({int(chance * 100)}% chance)",
            distance_from_nearest_location=dist_from_location,
            distance_from_login=dist_from_login
        )

    # Place a loot chest at a random location within 100 blocks
    try:
        # Generate random offset within 100 blocks
        offset_x = random.randint(-100, 100)
        offset_z = random.randint(-100, 100)
        # Y offset smaller range - could be underground or in air
        offset_y = random.randint(-30, 30)

        chest_x = current_pos.x + offset_x
        chest_y = max(1, min(255, current_pos.y + offset_y))  # Keep within world bounds
        chest_z = current_pos.z + offset_z

        # Place a chest and fill it with loot
        send_command_threadsafe(f'setblock {chest_x} {chest_y} {chest_z} minecraft:chest replace')
        send_command_threadsafe(f'loot insert {chest_x} {chest_y} {chest_z} loot {loot_table}')

        # Tell the player where to find it
        safe_msg = f"Explorer's reward! I've hidden a chest of supplies at {chest_x}, {chest_y}, {chest_z}. Happy hunting!"
        send_command_threadsafe(f'tellraw {player.username} {{"text":"[Jarvis] {safe_msg}"}}')

        # Update loot timestamp
        player.loot_last_given = timezone.now()
        player.save()

        return ExplorerRewardResult(
            player=player.username,
            success=True,
            reason=f"Chest placed at {chest_x}, {chest_y}, {chest_z}",
            distance_from_nearest_location=dist_from_location,
            distance_from_login=dist_from_login
        )

    except Exception as e:
        return ExplorerRewardResult(
            player=player.username,
            success=False,
            reason=f"RCON error: {e}",
            distance_from_nearest_location=dist_from_location,
            distance_from_login=dist_from_login
        )


def check_all_players_for_rewards() -> list[ExplorerRewardResult]:
    """
    Check all online players for explorer rewards.

    This is the main function to call periodically (e.g., every 5 minutes).

    Returns:
        List of ExplorerRewardResult for each online player.
    """
    results = []

    # Get online players
    online = get_online_players()

    for username in online:
        try:
            player = MinecraftPlayer.objects.get(username__iexact=username)
            result = try_give_explorer_reward(player)
            results.append(result)
        except MinecraftPlayer.DoesNotExist:
            results.append(ExplorerRewardResult(
                player=username,
                success=False,
                reason="Player not in database"
            ))

    return results
