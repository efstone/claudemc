"""
Database models for metaboop image tagging.
"""

from django.db import models


class ProcessedImage(models.Model):
    """Track images processed for keyword tagging."""

    file_path = models.CharField(max_length=1024, unique=True, db_index=True)
    file_hash = models.CharField(max_length=64)  # SHA-256 for change detection
    file_size = models.BigIntegerField()

    keywords = models.JSONField(default=list)  # Generated keywords
    is_minecraft = models.BooleanField(default=False)

    processed_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)

    # API usage tracking
    tokens_used = models.IntegerField(default=0)

    class Meta:
        ordering = ['-processed_at']

    def __str__(self):
        status = "OK" if self.success else "FAILED"
        return f"{self.file_path} [{status}] - {len(self.keywords)} keywords"
