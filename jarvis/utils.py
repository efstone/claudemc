"""
Utility functions for Jarvis.
"""

from django.contrib.auth.models import Group, User

from .models import MinecraftPlayer


def create_jarvis_player(username: str) -> MinecraftPlayer:
    """
    Create a Django user, MinecraftPlayer, and add to Jarvis group.

    Args:
        username: The Minecraft username (also used for Django user).

    Returns:
        The created MinecraftPlayer instance.

    Raises:
        ValueError: If user or player already exists.
    """
    # Check if already exists
    if User.objects.filter(username=username).exists():
        raise ValueError(f"User '{username}' already exists")
    if MinecraftPlayer.objects.filter(username=username).exists():
        raise ValueError(f"MinecraftPlayer '{username}' already exists")

    # Create user (no password - can't log in directly)
    user = User.objects.create_user(username=username)

    # Create MinecraftPlayer linked to user
    player = MinecraftPlayer.objects.create(username=username, user=user)

    # Get or create Jarvis group and add user
    jarvis_group, _ = Group.objects.get_or_create(name='Jarvis')
    user.groups.add(jarvis_group)

    return player
