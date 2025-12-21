"""
Management command to create a Jarvis-enabled player.

Usage:
    python manage.py add_jarvis_player <username>
"""

from django.core.management.base import BaseCommand, CommandError

from jarvis.utils import create_jarvis_player


class Command(BaseCommand):
    help = 'Create a Django user, MinecraftPlayer, and add to Jarvis group'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Minecraft username')

    def handle(self, *args, **options):
        username = options['username']

        try:
            player = create_jarvis_player(username)
            self.stdout.write(self.style.SUCCESS(
                f"Created Jarvis player: {player.username} (user: {player.user.username})"
            ))
        except ValueError as e:
            raise CommandError(str(e))
