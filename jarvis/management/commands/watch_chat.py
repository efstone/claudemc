"""
Management command to watch Minecraft chat in real-time.

Usage:
    python manage.py watch_chat
"""

import random
import signal
import sys
import threading
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from jarvis.claude import chat as claude_chat, random_event_message, clawed_eagle_joke, ToolCall
from jarvis.commands import CommandNotAllowedError
from jarvis.models import ChatMessage, MinecraftPlayer, ClaudeResponse, ToolExecution
from jarvis.rcon import say, give, teleport, set_time, weather, save_player_location, get_online_players, send_command_threadsafe, RconError
from jarvis.tailer import tail_chat


class Command(BaseCommand):
    help = 'Watch Minecraft server chat in real-time'

    # Random musing interval: 10-25 minutes (in seconds)
    MUSING_MIN_INTERVAL = 10 * 60
    MUSING_MAX_INTERVAL = 25 * 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True

    def handle(self, *args, **options):
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.stdout.write(self.style.SUCCESS('Starting Jarvis chat watcher...'))
        self.stdout.write('Press Ctrl+C to stop.\n')

        # Start random events thread
        events_thread = threading.Thread(target=self.random_events_loop, daemon=True)
        events_thread.start()
        self.stdout.write(self.style.SUCCESS('Random events thread started.'))

        try:
            for message in tail_chat():
                if not self.running:
                    break

                self.process_message(message)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS('\nJarvis stopped.'))

    def random_events_loop(self):
        """Background thread that triggers random events periodically."""
        while self.running:
            # Sleep for a random interval (10-25 minutes)
            interval = random.randint(self.MUSING_MIN_INTERVAL, self.MUSING_MAX_INTERVAL)
            self.stdout.write(f'[Random Events] Next musing in {interval // 60} minutes...')

            # Sleep in small increments so we can exit quickly
            for _ in range(interval):
                if not self.running:
                    return
                time.sleep(1)

            # Check if players are online
            players = get_online_players()
            if not players:
                self.stdout.write('[Random Events] No players online, skipping musing.')
                continue

            self.stdout.write(f'[Random Events] Players online: {", ".join(players)}')

            # Check if ClawedEagle is online - 1 in 3 chance of a joke about him
            clawed_eagle_online = any(p.lower() == 'clawedeagle' for p in players)
            do_eagle_joke = clawed_eagle_online and random.randint(1, 3) == 1

            # Generate and send a random message (or ClawedEagle joke)
            try:
                if do_eagle_joke:
                    self.stdout.write('[Random Events] ClawedEagle detected, generating joke...')
                    message = clawed_eagle_joke()
                else:
                    message = random_event_message()

                if message:
                    self.stdout.write(self.style.HTTP_INFO(f'[Random Events] Message: {message}'))
                    # Use thread-safe RCON (no signals)
                    safe_message = message.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
                    send_command_threadsafe(f'tellraw @a {{"text":"[Jarvis] {safe_message}"}}')

                    # Log as ChatMessage from Jarvis
                    jarvis_player, _ = MinecraftPlayer.objects.get_or_create(username='Jarvis')
                    ChatMessage.objects.create(
                        player=jarvis_player,
                        content=message,
                        timestamp=timezone.now()
                    )
                else:
                    self.stderr.write('[Random Events] Failed to generate message.')
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'[Random Events] Error: {e}'))

    def process_message(self, message):
        """Process a single chat message."""
        # Log to console
        self.stdout.write(
            f"[{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"<{message.username}> {message.content}"
        )

        # Get or create the player (case-insensitive lookup)
        player, created = MinecraftPlayer.objects.get_or_create(
            username__iexact=message.username,
            defaults={'username': message.username}
        )
        if created:
            self.stdout.write(self.style.NOTICE(f'  -> New player: {message.username}'))

        # Save to database (skip duplicates)
        chat_msg, created = ChatMessage.objects.get_or_create(
            player=player,
            content=message.content,
            timestamp=message.timestamp
        )
        if not created:
            self.stdout.write(self.style.WARNING(f'  -> Duplicate, skipping'))
            return

        # Check if user is in Jarvis group
        is_jarvis = player.is_jarvis_user()
        self.stdout.write(f'  -> Jarvis group: {is_jarvis} (user: {player.user})')
        if not is_jarvis:
            return

        # Only respond if message mentions Jarvis
        has_jarvis_mention = 'jarvis' in message.content.lower()
        self.stdout.write(f'  -> Contains "jarvis": {has_jarvis_mention}')
        if not has_jarvis_mention:
            return

        # Send to Claude and process response
        self.stdout.write(self.style.HTTP_INFO(f'  -> Sending to Claude...'))

        try:
            response = claude_chat(message.username, message.content)

            # Log Claude's response
            self.stdout.write(self.style.HTTP_INFO(f'  -> Claude text: {response.text}'))
            self.stdout.write(self.style.HTTP_INFO(f'  -> Claude tools: {len(response.tool_calls)} call(s)'))

            # Save Claude's response to database
            claude_response = ClaudeResponse.objects.create(
                username=message.username,
                prompt=message.content,
                response_text=response.text
            )

            # Also save as a ChatMessage from "Jarvis" for timeline view
            if response.text:
                jarvis_player, _ = MinecraftPlayer.objects.get_or_create(
                    username='Jarvis'
                )
                ChatMessage.objects.create(
                    player=jarvis_player,
                    content=response.text,
                    timestamp=timezone.now()
                )

            # Execute any tool calls
            for tool_call in response.tool_calls:
                self.execute_tool(tool_call, message.username, claude_response)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'  -> Claude error: {e}'))

    def execute_tool(self, tool_call: ToolCall, requesting_user: str, claude_response: ClaudeResponse):
        """Execute a tool call from Claude and log it."""
        self.stdout.write(
            self.style.WARNING(f'  -> Executing: {tool_call.name}({tool_call.arguments})')
        )

        rcon_result = None
        success = True

        try:
            if tool_call.name == 'say':
                rcon_result = say(tool_call.arguments['message'])
                # Log say messages as ChatMessages from Jarvis
                jarvis_player, _ = MinecraftPlayer.objects.get_or_create(
                    username='Jarvis'
                )
                ChatMessage.objects.create(
                    player=jarvis_player,
                    content=tool_call.arguments['message'],
                    timestamp=timezone.now()
                )
            elif tool_call.name == 'give':
                rcon_result = give(
                    tool_call.arguments['player'],
                    tool_call.arguments['item'],
                    tool_call.arguments.get('amount', 1)
                )
            elif tool_call.name == 'tp':
                rcon_result = teleport(
                    tool_call.arguments['player'],
                    tool_call.arguments['destination']
                )
            elif tool_call.name == 'time':
                rcon_result = set_time(
                    tool_call.arguments['action'],
                    tool_call.arguments['time']
                )
            elif tool_call.name == 'weather':
                rcon_result = weather(
                    tool_call.arguments['precipitation'],
                    tool_call.arguments.get('duration')
                )
            elif tool_call.name == 'save_location':
                # Save the player's current location - this handles its own RCON messaging
                result = save_player_location(
                    player=requesting_user,
                    name=tool_call.arguments['name'],
                    description=tool_call.arguments.get('description', '')
                )
                rcon_result = result.message
                success = result.success
            else:
                self.stderr.write(self.style.ERROR(f'  -> Unknown tool: {tool_call.name}'))
                success = False

            if rcon_result:
                # Check for common error patterns in RCON response
                error_patterns = ['unknown', 'invalid', 'error', 'failed', 'could not', 'no player']
                is_error = any(pattern in rcon_result.lower() for pattern in error_patterns)

                if is_error:
                    self.stderr.write(self.style.ERROR(f'  -> RCON error: {rcon_result}'))
                    success = False
                else:
                    self.stdout.write(self.style.SUCCESS(f'  -> RCON response: {rcon_result}'))

        except CommandNotAllowedError as e:
            self.stderr.write(self.style.ERROR(f'  -> Command blocked: {e}'))
            rcon_result = str(e)
            success = False
        except RconError as e:
            self.stderr.write(self.style.ERROR(f'  -> RCON error: {e}'))
            rcon_result = str(e)
            success = False

        # Log the tool execution
        ToolExecution.objects.create(
            response=claude_response,
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            rcon_result=rcon_result,
            success=success
        )

    def shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.running = False
