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


@admin.register(ToolExecution)
class ToolExecutionAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'tool_name', 'get_username', 'short_arguments', 'short_result', 'success')
    list_filter = ('tool_name', 'success', 'timestamp')
    search_fields = ('response__username', 'arguments', 'rcon_result')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    readonly_fields = ('response', 'tool_name', 'arguments', 'rcon_result', 'success', 'timestamp')

    def get_username(self, obj):
        return obj.response.username
    get_username.short_description = 'Player'
    get_username.admin_order_field = 'response__username'

    def short_arguments(self, obj):
        args_str = str(obj.arguments)
        return args_str[:60] + '...' if len(args_str) > 60 else args_str
    short_arguments.short_description = 'Arguments'

    def short_result(self, obj):
        result = obj.rcon_result or ''
        return result[:40] + '...' if len(result) > 40 else result
    short_result.short_description = 'RCON Result'


@admin.register(ClaudeResponse)
class ClaudeResponseAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'username', 'short_prompt', 'tools_summary')
    list_filter = ('username', 'timestamp')
    search_fields = ('username', 'prompt', 'response_text')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    inlines = [ToolExecutionInline]
    readonly_fields = ('username', 'prompt', 'response_text', 'timestamp')

    def short_prompt(self, obj):
        return obj.prompt[:50] + '...' if len(obj.prompt) > 50 else obj.prompt
    short_prompt.short_description = 'Prompt'

    def tools_summary(self, obj):
        """Show actual tool calls in the list view."""
        executions = obj.tool_executions.all()
        if not executions:
            return '-'

        summaries = []
        for ex in executions:
            args = ex.arguments
            if ex.tool_name == 'tp':
                summaries.append(f"tp {args.get('player', '?')} → {args.get('destination', '?')[:30]}")
            elif ex.tool_name == 'give':
                summaries.append(f"give {args.get('player', '?')} {args.get('item', '?')} x{args.get('amount', 1)}")
            elif ex.tool_name == 'say':
                msg = args.get('message', '')[:40]
                summaries.append(f'say "{msg}..."' if len(args.get('message', '')) > 40 else f'say "{msg}"')
            else:
                summaries.append(f"{ex.tool_name}(...)")

        return ' | '.join(summaries)
    tools_summary.short_description = 'Tool Calls'
