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
    # Check if already exists (case-insensitive)
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError(f"User '{username}' already exists")
    if MinecraftPlayer.objects.filter(username__iexact=username).exists():
        raise ValueError(f"MinecraftPlayer '{username}' already exists")

    # Create user (no password - can't log in directly)
    user = User.objects.create_user(username=username)

    # Create MinecraftPlayer linked to user
    player = MinecraftPlayer.objects.create(username=username, user=user)

    # Get or create Jarvis group and add user
    jarvis_group, _ = Group.objects.get_or_create(name='Jarvis')
    user.groups.add(jarvis_group)

    return player


def enable_jarvis_player(username: str) -> MinecraftPlayer:
    """
    Enable Jarvis for an existing MinecraftPlayer, or create if needed.

    Handles the case where a player already exists from chatting before
    being onboarded. Creates/links Django user and adds to Jarvis group.

    Args:
        username: The Minecraft username.

    Returns:
        The MinecraftPlayer instance with Jarvis access enabled.
    """
    # Get or create Django user (case-insensitive)
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        user = User.objects.create_user(username=username)

    # Check if user already has a linked player (via direct query)
    existing_linked = MinecraftPlayer.objects.filter(user=user).first()
    if existing_linked:
        player = existing_linked
    else:
        # Find existing player (case-insensitive) or create new one
        player = MinecraftPlayer.objects.filter(username__iexact=username, user__isnull=True).first()
        if player is None:
            player = MinecraftPlayer.objects.create(username=username, user=user)
        else:
            player.user = user
            player.save()

    # Get or create Jarvis group and add user
    jarvis_group, _ = Group.objects.get_or_create(name='Jarvis')
    user.groups.add(jarvis_group)

    return player
