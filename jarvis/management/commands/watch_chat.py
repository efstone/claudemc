"""
Management command to watch Minecraft chat in real-time.

Usage:
    python manage.py watch_chat
"""

import signal
import sys

from django.core.management.base import BaseCommand

from jarvis.claude import chat as claude_chat, ToolCall
from jarvis.commands import CommandNotAllowedError
from jarvis.models import ChatMessage, MinecraftPlayer
from jarvis.rcon import say, give, teleport, RconError
from jarvis.tailer import tail_chat


class Command(BaseCommand):
    help = 'Watch Minecraft server chat in real-time'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True

    def handle(self, *args, **options):
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.stdout.write(self.style.SUCCESS('Starting Jarvis chat watcher...'))
        self.stdout.write('Press Ctrl+C to stop.\n')

        try:
            for message in tail_chat():
                if not self.running:
                    break

                self.process_message(message)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS('\nJarvis stopped.'))

    def process_message(self, message):
        """Process a single chat message."""
        # Log to console
        self.stdout.write(
            f"[{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"<{message.username}> {message.content}"
        )

        # Save to database
        ChatMessage.objects.create(
            username=message.username,
            content=message.content,
            timestamp=message.timestamp
        )

        # Check if user is in Jarvis group
        if not self.is_jarvis_user(message.username):
            return

        # Send to Claude and process response
        self.stdout.write(self.style.HTTP_INFO(f'  -> Sending to Claude...'))

        try:
            response = claude_chat(message.username, message.content)

            # Execute any tool calls
            for tool_call in response.tool_calls:
                self.execute_tool(tool_call, message.username)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  -> Claude error: {e}'))

    def is_jarvis_user(self, username: str) -> bool:
        """Check if a Minecraft username is linked to a Jarvis group user."""
        try:
            player = MinecraftPlayer.objects.get(username=username)
            return player.is_jarvis_user()
        except MinecraftPlayer.DoesNotExist:
            return False

    def execute_tool(self, tool_call: ToolCall, requesting_user: str):
        """Execute a tool call from Claude."""
        self.stdout.write(
            self.style.WARNING(f'  -> Executing: {tool_call.name}({tool_call.arguments})')
        )

        try:
            if tool_call.name == 'say':
                response = say(tool_call.arguments['message'])
            elif tool_call.name == 'give':
                response = give(
                    tool_call.arguments['player'],
                    tool_call.arguments['item'],
                    tool_call.arguments.get('amount', 1)
                )
            elif tool_call.name == 'tp':
                response = teleport(
                    tool_call.arguments['player'],
                    tool_call.arguments['destination']
                )
            else:
                self.stderr.write(self.style.ERROR(f'  -> Unknown tool: {tool_call.name}'))
                return

            if response:
                self.stdout.write(self.style.SUCCESS(f'  -> RCON response: {response}'))

        except CommandNotAllowedError as e:
            self.stderr.write(self.style.ERROR(f'  -> Command blocked: {e}'))
        except RconError as e:
            self.stderr.write(self.style.ERROR(f'  -> RCON error: {e}'))

    def shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.running = False
