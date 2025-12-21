from django.contrib import admin

from .models import MinecraftPlayer, ChatMessage, Location, ClaudeResponse, ToolExecution


@admin.register(MinecraftPlayer)
class MinecraftPlayerAdmin(admin.ModelAdmin):
    list_display = ('username', 'user', 'is_jarvis_user')
    list_filter = ('user__groups',)
    search_fields = ('username', 'user__username')

    def is_jarvis_user(self, obj):
        return obj.is_jarvis_user()
    is_jarvis_user.boolean = True
    is_jarvis_user.short_description = 'Jarvis Access'


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'player', 'short_content')
    list_filter = ('player', 'timestamp')
    search_fields = ('player__username', 'content')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    def short_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    short_content.short_description = 'Message'


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'x', 'y', 'z', 'description')
    search_fields = ('name', 'description')
    ordering = ('name',)


class ToolExecutionInline(admin.TabularInline):
    model = ToolExecution
    extra = 0
    readonly_fields = ('tool_name', 'arguments', 'rcon_result', 'success', 'timestamp')
    can_delete = False


@admin.register(ClaudeResponse)
class ClaudeResponseAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'username', 'short_prompt', 'short_response', 'tool_count')
    list_filter = ('username', 'timestamp')
    search_fields = ('username', 'prompt', 'response_text')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    inlines = [ToolExecutionInline]
    readonly_fields = ('username', 'prompt', 'response_text', 'timestamp')

    def short_prompt(self, obj):
        return obj.prompt[:50] + '...' if len(obj.prompt) > 50 else obj.prompt
    short_prompt.short_description = 'Prompt'

    def short_response(self, obj):
        text = obj.response_text or ''
        return text[:50] + '...' if len(text) > 50 else text
    short_response.short_description = 'Response'

    def tool_count(self, obj):
        return obj.tool_executions.count()
    tool_count.short_description = 'Tools'
