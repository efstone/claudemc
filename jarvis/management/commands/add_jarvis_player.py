"""
Management command to enable Jarvis for a player.

Usage:
    python manage.py add_jarvis_player <username>
"""

from django.core.management.base import BaseCommand

from jarvis.utils import enable_jarvis_player


class Command(BaseCommand):
    help = 'Enable Jarvis access for a player (creates user/player if needed)'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Minecraft username')

    def handle(self, *args, **options):
        username = options['username']

        player = enable_jarvis_player(username)
        self.stdout.write(self.style.SUCCESS(
            f"Enabled Jarvis for: {player.username} (user: {player.user.username})"
        ))
