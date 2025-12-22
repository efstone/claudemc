"""
Anthropic Claude API integration for Jarvis.

Uses Claude's tool use feature to execute Minecraft commands.
"""

from dataclasses import dataclass
from typing import Optional

import anthropic

from django.conf import settings

from .models import Location


# Web search tool
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3
}

# Tool definitions for Claude
MINECRAFT_TOOLS = [
    {
        "name": "say",
        "description": "Send a chat message to all players on the Minecraft server. Use this to respond to players.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to send to chat"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "give",
        "description": "Give an item to a player in Minecraft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "description": "The player's username"
                },
                "item": {
                    "type": "string",
                    "description": "The item ID (e.g., 'diamond', 'minecraft:iron_ingot')"
                },
                "amount": {
                    "type": "integer",
                    "description": "Number of items to give (default: 1)",
                    "default": 1
                }
            },
            "required": ["player", "item"]
        }
    },
    {
        "name": "tp",
        "description": "Teleport a player to coordinates or another player.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "description": "The player to teleport"
                },
                "destination": {
                    "type": "string",
                    "description": "Destination: either 'x y z' coordinates or another player's name"
                }
            },
            "required": ["player", "destination"]
        }
    }
]

SYSTEM_PROMPT_BASE = """You are Jarvis, a helpful AI assistant for a Minecraft server. Players can chat with you in-game.

You have access to the following commands:
- say: Send a message to all players
- give: Give items to players
- tp: Teleport players

Guidelines:
- Be friendly and helpful
- IMPORTANT: Keep messages under 200 characters! Minecraft has a 256 char limit. Be brief.
- Use the say tool to respond to players
- Only use give/tp when explicitly requested
- If a request seems harmful or griefing-related, politely decline
- You can be playful and fun - this is a game after all!

The player's username will be provided with each message."""


def build_system_prompt() -> str:
    """Build the system prompt with current locations from database."""
    prompt = SYSTEM_PROMPT_BASE

    locations = Location.objects.all()
    if locations:
        prompt += "\n\nKnown locations you can teleport players to (use fuzzy matching - "
        prompt += "'lighthouse' matches 'Mine Island: Lighthouse Station'):"
        for loc in locations:
            desc = f" - {loc.description}" if loc.description else ""
            prompt += f"\n- {loc.name}: {loc.coordinates}{desc}"

    return prompt


@dataclass
class ToolCall:
    """A tool call from Claude's response."""
    name: str
    arguments: dict


@dataclass
class ClaudeResponse:
    """Response from Claude, including any tool calls."""
    text: Optional[str]
    tool_calls: list[ToolCall]


def get_client() -> anthropic.Anthropic:
    """Get an Anthropic client instance."""
    return anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)


def chat(username: str, message: str, conversation_history: list = None) -> ClaudeResponse:
    """
    Send a chat message to Claude and get a response.

    Args:
        username: The Minecraft player's username.
        message: The chat message from the player.
        conversation_history: Optional list of previous messages for context.

    Returns:
        ClaudeResponse with text and any tool calls.
    """
    client = get_client()

    # Build messages
    messages = conversation_history or []
    messages.append({
        "role": "user",
        "content": f"[{username}]: {message}"
    })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=build_system_prompt(),
        tools=MINECRAFT_TOOLS + [WEB_SEARCH_TOOL],
        messages=messages
    )

    # Parse response
    text_content = None
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            text_content = block.text
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(
                name=block.name,
                arguments=block.input
            ))

    return ClaudeResponse(text=text_content, tool_calls=tool_calls)
