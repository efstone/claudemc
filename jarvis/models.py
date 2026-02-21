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

    # Explorer rewards tracking
    loot_last_given = models.DateTimeField(null=True, blank=True)
    last_login_x = models.IntegerField(null=True, blank=True)
    last_login_y = models.IntegerField(null=True, blank=True)
    last_login_z = models.IntegerField(null=True, blank=True)

    def is_jarvis_user(self) -> bool:
        """Check if this player's Django user is in the Jarvis group."""
        if self.user is None:
            return False
        return self.user.groups.filter(name='Jarvis').exists()

    def can_receive_loot(self) -> bool:
        """Check if player can receive loot (not given in last hour)."""
        if self.loot_last_given is None:
            return True
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() - self.loot_last_given > timedelta(hours=1)

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
        constraints = [
            models.UniqueConstraint(
                fields=['player', 'timestamp', 'content'],
                name='unique_chat_message'
            )
        ]

    def __str__(self):
        return f"<{self.player.username}> {self.content[:50]}"


class Location(models.Model):
    """A named location for teleportation."""

    name = models.CharField(max_length=50, unique=True)  # e.g., "spawn", "shop"
    x = models.IntegerField()
    y = models.IntegerField()
    z = models.IntegerField()
    dimension = models.CharField(max_length=20, default='overworld')
    description = models.CharField(max_length=300, blank=True)  # Optional description
    screenshot = models.ImageField(upload_to='location_screenshots/', blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.z})"

    @property
    def coordinates(self) -> str:
        """Return coordinates as a string for RCON."""
        return f"{self.x} {self.y} {self.z}"

    @property
    def display_coordinates(self) -> str:
        """Return coordinates with dimension label for non-overworld locations."""
        coords = f"{self.x} {self.y} {self.z}"
        if self.dimension != 'overworld':
            coords += f" [{self.dimension}]"
        return coords


class ClaudeResponse(models.Model):
    """A response from Claude to a user's message."""

    username = models.CharField(max_length=16)  # Who triggered this response
    prompt = models.TextField()  # The user's message
    response_text = models.TextField(blank=True, null=True)  # Claude's text response
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        text_preview = (self.response_text or '')[:50]
        return f"[{self.username}] {text_preview}"


class ToolExecution(models.Model):
    """A tool call executed as part of a Claude response."""

    response = models.ForeignKey(
        ClaudeResponse,
        on_delete=models.CASCADE,
        related_name='tool_executions'
    )
    tool_name = models.CharField(max_length=50)  # say, give, tp, etc.
    arguments = models.JSONField()  # Tool arguments
    rcon_result = models.TextField(blank=True, null=True)  # RCON response
    success = models.BooleanField(default=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.tool_name}({self.arguments})"


class MinecraftTrivia(models.Model):
    fact = models.CharField(max_length=250, default='')
    last_used = models.DateTimeField(default=None, null=True)

    class Meta:
        ordering = ['last_used']

    def __str__(self):
        return f"{self.fact} ({self.last_used})"
