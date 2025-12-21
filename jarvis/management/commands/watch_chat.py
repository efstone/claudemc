"""
Management command to watch Minecraft chat in real-time.

Usage:
    python manage.py watch_chat
"""

import signal
import sys

from django.core.management.base import BaseCommand

from jarvis.tailer import tail_chat


class Command(BaseCommand):
    help = 'Watch Minecraft server chat in real-time'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True

    def handle(self, *args, **options):
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        self.stdout.write(self.style.SUCCESS('Starting chat watcher...'))
        self.stdout.write('Press Ctrl+C to stop.\n')

        try:
            for message in tail_chat():
                if not self.running:
                    break

                # Print to console (later: save to database)
                self.stdout.write(
                    f"[{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"<{message.username}> {message.content}"
                )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS('\nChat watcher stopped.'))

    def shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.running = False
