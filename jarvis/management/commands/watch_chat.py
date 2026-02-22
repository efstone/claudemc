"""
Management command to watch Minecraft chat in real-time.

Usage:
    python manage.py watch_chat
"""

import random
import re
import signal
import sys
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from jarvis.claude import chat as claude_chat, random_event_message, clawed_eagle_joke, ToolCall
from jarvis.commands import CommandNotAllowedError
from jarvis.explorer import check_all_players_for_rewards
from jarvis.models import ChatMessage, Location, MinecraftPlayer, ClaudeResponse, ToolExecution
from jarvis.rcon import say, give, teleport, set_time, weather, save_player_location, get_online_players, send_command_threadsafe, get_player_dimension, RconError
from jarvis.tailer import tail_log


def normalize_player_name(claude_player: str, requesting_user: str) -> str:
    """
    Correct Claude's player argument if it's a mangled version of requesting_user.

    Handles cases where Claude:
    - Strips the leading dot: ".eugrcants" -> "eugrcants"
    - Adds a leading dot: "Steve" -> ".Steve"
    - Gets it right (no change needed)
    """
    if not requesting_user:
        return claude_player

    # Check if Claude's answer matches the requesting user (with or without dot)
    claude_normalized = claude_player.lstrip('.')
    user_normalized = requesting_user.lstrip('.')

    if claude_normalized.lower() == user_normalized.lower():
        # Claude was referring to the requesting user - use the actual username
        return requesting_user

    # Different player entirely - trust Claude's output
    return claude_player


VALID_DIMENSIONS = {'overworld', 'the_nether', 'the_end'}


def validate_tp_args(arguments: dict) -> str | None:
    """
    Validate tp tool call arguments.

    Returns None if valid, or an error message string if invalid.
    """
    dimension = arguments.get('dimension', 'overworld')
    if dimension not in VALID_DIMENSIONS:
        return f"Invalid dimension '{dimension}'. Must be one of: {', '.join(sorted(VALID_DIMENSIONS))}"

    destination = arguments.get('destination', '')
    if not destination.strip():
        return "Empty destination"

    return None


class Command(BaseCommand):
    help = 'Watch Minecraft server chat in real-time'

    # Random musing interval: 10-25 minutes (in seconds)
    MUSING_MIN_INTERVAL = 10 * 60
    MUSING_MAX_INTERVAL = 25 * 60

    # Explorer rewards interval: 5 minutes
    EXPLORER_INTERVAL = 5 * 60

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

        # Start explorer rewards thread
        explorer_thread = threading.Thread(target=self.explorer_rewards_loop, daemon=True)
        explorer_thread.start()
        self.stdout.write(self.style.SUCCESS('Explorer rewards thread started.'))

        try:
            for event in tail_log():
                if not self.running:
                    break

                if event.event_type == 'chat':
                    self.process_message(event.data)
                elif event.event_type == 'login':
                    self.process_login(event.data)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS('\nJarvis stopped.'))

    def process_login(self, login):
        """Process a player login event - save coordinates."""
        self.stdout.write(
            f"[{login.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{login.username} logged in at ({login.x}, {login.y}, {login.z})"
        )

        # Get or create the player
        player, created = MinecraftPlayer.objects.get_or_create(
            username__iexact=login.username,
            defaults={'username': login.username}
        )
        if created:
            self.stdout.write(self.style.NOTICE(f'  -> New player: {login.username}'))

        # Save login coordinates
        player.last_login_x = login.x
        player.last_login_y = login.y
        player.last_login_z = login.z
        player.save()
        self.stdout.write(f'  -> Saved login coords: ({login.x}, {login.y}, {login.z})')

    def explorer_rewards_loop(self):
        """Background thread that checks for explorer rewards periodically."""
        while self.running:
            self.stdout.write(f'[Explorer] Next check in {self.EXPLORER_INTERVAL // 60} minutes...')

            # Sleep in small increments so we can exit quickly
            for _ in range(self.EXPLORER_INTERVAL):
                if not self.running:
                    return
                time.sleep(1)

            # Check all online players for rewards
            self.stdout.write('[Explorer] Checking players for explorer rewards...')
            try:
                results = check_all_players_for_rewards()
                for result in results:
                    if result.success:
                        self.stdout.write(self.style.SUCCESS(
                            f'[Explorer] {result.player}: {result.reason}'
                        ))
                    else:
                        self.stdout.write(f'[Explorer] {result.player}: {result.reason}')
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'[Explorer] Error: {e}'))

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

        # Check if user is in Jarvis group (if enforcement is enabled)
        if settings.ENFORCE_JARVIS_GROUP:
            is_jarvis = player.is_jarvis_user()
            self.stdout.write(f'  -> Jarvis group: {is_jarvis} (user: {player.user})')
            if not is_jarvis:
                return
        else:
            self.stdout.write(f'  -> Jarvis group enforcement disabled, allowing all players')

        # Only respond if message mentions Jarvis
        has_jarvis_mention = 'jarvis' in message.content.lower()
        self.stdout.write(f'  -> Contains "jarvis": {has_jarvis_mention}')
        if not has_jarvis_mention:
            return

        # Query player dimension before Claude call
        player_dimension = get_player_dimension(message.username)
        if player_dimension:
            self.stdout.write(self.style.HTTP_INFO(f'  -> Player dimension: minecraft:{player_dimension}'))
        else:
            player_dimension = 'overworld'
            self.stdout.write(self.style.WARNING(f'  -> Could not query dimension, defaulting to overworld'))

        # Send to Claude and process response
        self.stdout.write(self.style.HTTP_INFO(f'  -> Sending to Claude...'))

        try:
            response = claude_chat(message.username, message.content, player_dimension=player_dimension)

            # Log Claude's response
            self.stdout.write(self.style.HTTP_INFO(f'  -> Claude text: {response.text}'))
            self.stdout.write(self.style.HTTP_INFO(f'  -> Claude tools: {len(response.tool_calls)} call(s)'))

            # Validate tp tool calls — retry once if invalid
            tp_error = None
            for tool_call in response.tool_calls:
                if tool_call.name == 'tp':
                    tp_error = validate_tp_args(tool_call.arguments)
                    if tp_error:
                        self.stderr.write(self.style.ERROR(f'  -> tp validation failed: {tp_error}'))
                        break

            if tp_error:
                # Retry once with error context
                self.stdout.write(self.style.WARNING(f'  -> Retrying Claude with error context...'))
                retry_message = f"{message.content} [SYSTEM: Your previous tp call was invalid: {tp_error}. Please fix the dimension parameter.]"
                response = claude_chat(message.username, retry_message, player_dimension=player_dimension)
                self.stdout.write(self.style.HTTP_INFO(f'  -> Retry Claude tools: {len(response.tool_calls)} call(s)'))

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
                # Correct player name if Claude mangled it
                player = normalize_player_name(
                    tool_call.arguments['player'],
                    requesting_user
                )
                rcon_result = give(
                    player,
                    tool_call.arguments['item'],
                    tool_call.arguments.get('amount', 1)
                )
            elif tool_call.name == 'tp':
                # Correct player name if Claude mangled it
                player = normalize_player_name(
                    tool_call.arguments['player'],
                    requesting_user
                )
                dest = tool_call.arguments['destination']
                dimension = tool_call.arguments.get('dimension', 'overworld')
                # If destination isn't coordinates, try resolving as a location name
                if not re.match(r'^-?\d+\s+-?\d+\s+-?\d+$', dest.strip()):
                    loc = Location.objects.filter(name__icontains=dest.strip()).first()
                    if loc:
                        self.stdout.write(f'  -> Resolved location "{dest}" to {loc.coordinates} [{loc.dimension}]')
                        dest = loc.coordinates
                        dimension = loc.dimension
                self.stdout.write(f'  -> tp dimension: {dimension}, destination: {dest}')
                rcon_result = teleport(
                    player,
                    dest,
                    dimension=dimension
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
