"""
Django admin configuration for metaboop.
"""

from django.contrib import admin

from .models import ProcessedImage


@admin.register(ProcessedImage)
class ProcessedImageAdmin(admin.ModelAdmin):
    list_display = (
        'short_path',
        'success',
        'is_minecraft',
        'keyword_count',
        'tokens_used',
        'processed_at',
    )
    list_filter = ('success', 'is_minecraft', 'processed_at')
    search_fields = ('file_path', 'keywords')
    ordering = ('-processed_at',)
    readonly_fields = (
        'file_path',
        'file_hash',
        'file_size',
        'keywords',
        'is_minecraft',
        'processed_at',
        'success',
        'error_message',
        'tokens_used',
    )

    def short_path(self, obj):
        path = obj.file_path
        return f"...{path[-50:]}" if len(path) > 50 else path

    short_path.short_description = 'File Path'

    def keyword_count(self, obj):
        return len(obj.keywords) if obj.keywords else 0

    keyword_count.short_description = 'Keywords'
