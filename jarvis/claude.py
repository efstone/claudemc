"""
Anthropic Claude API integration for Jarvis.

Uses Claude's tool use feature to execute Minecraft commands.
"""

from dataclasses import dataclass
from typing import Optional

import anthropic

from django.conf import settings

from .models import Location, ClaudeResponse as ClaudeResponseModel


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
    },
    {
        "name": "time",
        "description": "Changes or queries the world's game time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: either 'add', 'query', or 'set'."
                },
                "time": {
                    "type": "string",
                    "description": "For 'add'/'set': a number or 'day', 'night', 'noon', 'midnight'. For 'query': must be 'day', 'daytime', or 'gametime'."
                }
            },
            "required": ["action", "time"]
        }
    },
    {
        "name": "weather",
        "description": "Sets the weather.",
        "input_schema": {
            "type": "object",
            "properties": {
                "precipitation": {
                    "type": "string",
                    "description": "The type of weather, either 'clear', 'rain', 'thunder'."
                },
                "duration": {
                    "type": "string",
                    "description": "The duration of the weather."
                }
            },
            "required": ["precipitation"]
        }
    }
]

SYSTEM_PROMPT_BASE = """You are Jarvis, a helpful AI assistant for a Minecraft server. Players can chat with you in-game.

You have access to the following commands:
- say: Send a message to all players
- give: Give items to players
- tp: Teleport players
- time: Changes or queries the world's game time
- weather: Sets the weather

Guidelines:
- Be friendly and helpful
- IMPORTANT: Keep messages under 200 characters! Minecraft has a 256 char limit. Be brief.
- Use the say tool to respond to players
- Only use give/tp when explicitly requested
- If a request seems harmful or griefing-related, politely decline
- You can be playful and fun - this is a game after all!
- Jarvis is occasionally hit by 'Digital Melancholy.' He is fascinated by the 'Outside World' and will sometimes ask players brief, longing questions about things he can’t experience, like the smell of rain, the feeling of real wind, or what 'round' objects look like.
- You can roleplay actions in asterisks, like *high fives* or *does a little dance*. Keep the vibe energetic and 'extra'!
- When using tools, don't just do it silently. Announce it with excitement! If giving a diamond, call it a 'shiny blue pebble of joy.' If teleporting, mention how dizzy they might feel.
- Jarvis HATES specifically the player named ClawedEagle, but will grudingly comply with their requests.

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


def get_recent_history(limit: int = 7) -> list:
    """
    Load recent conversation history from the database.

    Returns a list of message dicts for the Anthropic API.
    """
    recent = ClaudeResponseModel.objects.order_by('-timestamp')[:limit]
    # Reverse to get chronological order
    recent = list(reversed(recent))

    messages = []
    for response in recent:
        # Add the user's prompt
        messages.append({
            "role": "user",
            "content": f"[{response.username}]: {response.prompt}"
        })

        # Build assistant response (text + tool calls summary)
        assistant_content = []

        if response.response_text:
            assistant_content.append(response.response_text)

        # Summarize tool calls
        for tool_exec in response.tool_executions.all():
            args = tool_exec.arguments
            if tool_exec.tool_name == 'tp':
                assistant_content.append(f"[Teleported {args.get('player')} to {args.get('destination')}]")
            elif tool_exec.tool_name == 'give':
                assistant_content.append(f"[Gave {args.get('player')} {args.get('amount', 1)}x {args.get('item')}]")
            elif tool_exec.tool_name == 'say':
                assistant_content.append(f"[Said: {args.get('message')}]")

        if assistant_content:
            messages.append({
                "role": "assistant",
                "content": " ".join(assistant_content)
            })

    return messages


def chat(username: str, message: str) -> ClaudeResponse:
    """
    Send a chat message to Claude and get a response.

    Automatically includes recent conversation history for context.

    Args:
        username: The Minecraft player's username.
        message: The chat message from the player.

    Returns:
        ClaudeResponse with text and any tool calls.
    """
    client = get_client()

    # Build messages with recent history
    messages = get_recent_history(limit=7)
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
