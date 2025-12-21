from django.contrib import admin

from .models import MinecraftPlayer, ChatMessage


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
