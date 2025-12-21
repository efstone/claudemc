"""
Command validation for Minecraft RCON commands.

Only whitelisted commands can be executed.
"""

import re

# Commands that Claude is allowed to execute
ALLOWED_COMMANDS = {'say', 'give', 'tp'}


class CommandNotAllowedError(Exception):
    """Raised when a command is not in the whitelist."""
    pass


def validate_command(command: str) -> None:
    """
    Validate that a command is in the whitelist.

    Args:
        command: The command string (without leading slash).

    Raises:
        CommandNotAllowedError: If the command is not allowed.
    """
    # Extract the base command (first word)
    command = command.strip()
    if not command:
        raise CommandNotAllowedError("Empty command")

    base_command = command.split()[0].lower()

    if base_command not in ALLOWED_COMMANDS:
        raise CommandNotAllowedError(
            f"Command '{base_command}' is not allowed. "
            f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )


def sanitize_argument(arg: str) -> str:
    """
    Sanitize a command argument to prevent injection.

    Args:
        arg: The argument to sanitize.

    Returns:
        Sanitized argument string.
    """
    # Remove any characters that could be used for command injection
    # Allow alphanumeric, spaces, underscores, hyphens, colons (for namespaced items)
    sanitized = re.sub(r'[^\w\s\-:.]', '', arg)
    return sanitized.strip()
