from django.contrib.auth.models import User
from django.db import models


class MinecraftPlayer(models.Model):
    """Links a Minecraft username to an optional Django User for permissions."""

    username = models.CharField(max_length=16, unique=True)  # MC username
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='minecraft_player'
    )

    def is_jarvis_user(self) -> bool:
        """Check if this player's Django user is in the Jarvis group."""
        if self.user is None:
            return False
        return self.user.groups.filter(name='Jarvis').exists()

    def __str__(self):
        if self.user:
            return f"{self.username} ({self.user.username})"
        return self.username


class ChatMessage(models.Model):
    """A chat message from the Minecraft server."""

    player = models.ForeignKey(
        MinecraftPlayer,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    content = models.TextField()
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"<{self.player.username}> {self.content[:50]}"
