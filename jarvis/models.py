from django.db import models


class ChatMessage(models.Model):
    """A chat message from the Minecraft server."""

    username = models.CharField(max_length=16, db_index=True)  # MC usernames max 16 chars
    content = models.TextField()
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"<{self.username}> {self.content[:50]}"
