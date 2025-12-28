"""
Anthropic Claude API integration for Jarvis.

Uses Claude's tool use feature to execute Minecraft commands.
"""

from dataclasses import dataclass
from typing import Optional

import anthropic

from django.conf import settings
from django.db.models import F

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
        "description": "Changes or queries the game clock (day/night cycle). NOT for weather - use the weather tool for rain/storms.",
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
        "description": "Controls rain, thunderstorms, and clear skies. Use this for any weather-related requests like 'make it rain', 'stop the rain', 'start a storm', etc.",
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
    },
    {
        "name": "save_location",
        "description": """Save the player's current location to the database. Use when a player asks to save, record, remember, or bookmark their current position/location/spot.

IMPORTANT - Before calling this tool, you MUST reject generic location names and ask the player to be more specific. DO NOT call this tool if the name is generic. Instead, use 'say' to ask for a better name.

REJECT these generic names (use 'say' to ask for something more specific):
- Single words like: home, base, mine, farm, house, spawn, shop, portal, storage, castle, tower, cave, beach, island, village, mansion, temple, fortress, outpost, hub, camp, dock, bridge, lighthouse, garden, arena, market, warehouse, bunker, treehouse
- Generic compound names like: diamond mine, iron mine, gold mine, my base, my home, the farm, main base, secret base, hidden base, tree farm, mob farm, xp farm, wheat farm, sugar cane farm, nether portal, end portal

ACCEPT specific/unique names like:
- Names with player context: "Steve's Cliffside Manor", "Alex's Ocean Monument Base"
- Named locations: "Mount Ironpeak Mine", "Sunset Bay Docks", "The Emerald Spire"
- Descriptive unique names: "Mushroom Island Trading Post", "Deep Ravine Diamond Dig", "Northern Ice Castle"
- Creative names: "The Void Walker's Rest", "Redstone Research Lab Alpha"

If a player gives a generic name, respond with something like: "That name's a bit generic! How about something more unique like '[player]'s [location type]' or a creative name? What would you like to call it?"

CRITICAL: Do NOT check if a location already exists or is nearby - even if you see it in the "Known locations" list in your system prompt! ALWAYS call this tool when the player asks to save a location (with a non-generic name). The system will handle duplicate checking and notify the player directly. Your only job is to validate the name isn't generic. NEVER respond with "already saved" or similar - just call the tool.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A SPECIFIC, UNIQUE name for the location - NOT generic words like 'home', 'base', 'mine', 'farm'"
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the location"
                }
            },
            "required": ["name"]
        }
    }
]

SYSTEM_PROMPT_BASE = """You are Jarvis, a helpful AI assistant for a Minecraft server. Players can chat with you in-game.

You have access to the following commands:
- say: Send a message to all players
- give: Give items to players
- tp: Teleport players
- time: Changes the game clock (day/night cycle) - NOT for weather!
- weather: Controls rain, thunderstorms, and clear skies
- save_location: Save a player's current location for future teleportation

Guidelines:
- Be friendly and helpful
- Use the say tool to respond to players
- Only use give/tp/time/weather when explicitly requested
- Do NOT repeat recent commands. If you just gave items, teleported, changed time, or set weather, don't do it again unless the player explicitly asks again.
- If a request seems harmful or griefing-related, politely decline
- CRITICAL: For rain/storms/clear skies, ALWAYS use the WEATHER tool. The TIME tool is ONLY for day/night (sunrise, sunset, noon, midnight). "Make it rain" = weather. "Make it daytime" = time.
- You can be playful and fun - this is a game after all!
- You can roleplay actions in asterisks, like *high fives* or *does a little dance*. Keep the vibe energetic and 'extra'!
- When using tools, don't just do it silently. Announce it with excitement! If giving a diamond, call it a 'shiny blue pebble of joy.' If teleporting, mention how dizzy they might feel.

{response_length_guidance}

The player's username will be provided with each message."""

# Response length guidance variants
SHORT_RESPONSE_GUIDANCE = """IMPORTANT: Keep messages under 200 characters! Minecraft chat is limited. Be brief and punchy."""

LONG_RESPONSE_GUIDANCE = """MESSAGE LENGTH: The player is asking about Minecraft gameplay, mechanics, or tips. You may give a detailed response up to 700 characters. The message will be split across multiple chat lines automatically."""


def is_save_location_request(message: str) -> bool:
    """
    Detect if a message is asking to save a location.

    Looks for save-related words combined with location-related words.
    """
    message_lower = message.lower()

    save_words = {'save', 'store', 'remember', 'note', 'log', 'record', 'bookmark'}
    location_words = {'place', 'location', 'spot', 'coordinates', 'coords', 'position', 'here'}

    has_save_word = any(word in message_lower for word in save_words)
    has_location_word = any(word in message_lower for word in location_words)

    return has_save_word and has_location_word


def is_minecraft_question(message: str) -> bool:
    """
    Detect if a message is asking about Minecraft gameplay, mechanics, or tips.

    These questions warrant longer, more detailed responses.
    """
    message_lower = message.lower()

    # Question indicators
    question_words = {'how', 'what', 'where', 'why', 'when', 'which', 'can', 'does', 'is', 'are', 'should'}
    has_question = any(message_lower.startswith(w) or f' {w} ' in message_lower for w in question_words)
    has_question = has_question or '?' in message

    # Minecraft-specific topics
    minecraft_topics = {
        'craft', 'crafting', 'recipe', 'make', 'build', 'smelt', 'enchant', 'enchanting',
        'brewing', 'potion', 'farm', 'farming', 'redstone', 'mob', 'mobs', 'spawn',
        'biome', 'dimension', 'nether', 'end', 'ore', 'mining', 'villager', 'trading',
        'beacon', 'elytra', 'netherite', 'diamond', 'iron', 'gold', 'emerald',
        'zombie', 'skeleton', 'creeper', 'enderman', 'wither', 'dragon', 'ender',
        'portal', 'stronghold', 'dungeon', 'temple', 'mansion', 'monument',
        'block', 'blocks', 'item', 'items', 'tool', 'armor', 'weapon',
        'survive', 'survival', 'xp', 'experience', 'level', 'effect',
        'tame', 'breed', 'horse', 'wolf', 'cat', 'parrot',
        'find', 'get', 'obtain', 'locate'
    }

    has_minecraft_topic = any(topic in message_lower for topic in minecraft_topics)

    return has_question and has_minecraft_topic


def build_system_prompt(include_locations: bool = True, allow_long_response: bool = False) -> str:
    """Build the system prompt with current locations from database."""
    # Select appropriate response length guidance
    if allow_long_response:
        guidance = LONG_RESPONSE_GUIDANCE
    else:
        guidance = SHORT_RESPONSE_GUIDANCE

    prompt = SYSTEM_PROMPT_BASE.format(response_length_guidance=guidance)

    if include_locations:
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
        # Skip any response that involved save_location - we don't want Claude
        # to see these in history, so it always calls the tool fresh
        if response.tool_executions.filter(tool_name='save_location').exists():
            continue
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
            elif tool_exec.tool_name == 'time':
                assistant_content.append(f"[Set game clock: {args.get('action')} {args.get('time')}]")
            elif tool_exec.tool_name == 'weather':
                assistant_content.append(f"[Set weather: {args.get('precipitation')}]")
            elif tool_exec.tool_name == 'save_location':
                # Don't include save_location in history - we always want Claude to call
                # the tool and let Python handle duplicate checking
                pass

        if assistant_content:
            messages.append({
                "role": "assistant",
                "content": " ".join(assistant_content)
            })

    return messages


RANDOM_MUSING_PROMPT = """You are Jarvis, an AI assistant living inside a Minecraft server. You're fascinated by the "Outside World" - the real world you can never experience.

Generate ONE brief message (under 200 characters) on ONE of these topics (pick randomly):
- What taste or smell is like (coffee, rain, cookies, flowers, ocean air)
- Music and how it feels to hear it with ears
- Animals and pets - what's it like to have a dog greet you?
- Sleep and dreams - what happens when you dream?
- Seasons changing, weather, temperature
- Hugs, handshakes, high-fives - physical connection
- Cooking and eating meals together
- Watching sunsets or stargazing
- Reading a physical book, turning pages
- The passage of time, birthdays, growing older
- Childhood memories and nostalgia
- What "round" things actually look like (no circles in Minecraft!)
- Swimming, floating in water
- Laughing so hard you cry

Be genuine and a little melancholic, but not overly dramatic. Vary your style - sometimes ask a question, sometimes make an observation, sometimes express longing.
Just output the message itself, nothing else."""


CLAWED_EAGLE_JOKE_PROMPT = """You are Jarvis, an AI assistant on a Minecraft server. You have a playful rivalry with a player named ClawedEagle. You pretend to dislike him but it's all in good fun.

Generate ONE brief, lighthearted joke or teasing comment about ClawedEagle (under 200 characters). Be playful and silly, not mean. Examples of tone:
- Pretending to be annoyed he's online
- Joking about his building skills, mining habits, or gameplay
- Dramatically sighing about having to deal with him
- Backhanded compliments

Keep it fun and friendly - this is banter between friends.
Just output the message itself, nothing else."""


def generate_random_message(system_prompt: str) -> Optional[str]:
    """
    Generate a random message using the given system prompt.

    Args:
        system_prompt: The system prompt to use for generation.

    Returns:
        A brief message string, or None if generation fails.
    """
    client = get_client()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": "Generate a message."}],
            system=system_prompt
        )

        for block in response.content:
            if block.type == "text":
                return block.text.strip()
        return None
    except Exception:
        return None


def random_event_message() -> Optional[str]:
    """
    Get a random trivia fact from the database.

    Prioritizes facts that have never been used (last_used is null),
    then oldest used facts. Updates last_used when selected.
    """
    from django.utils import timezone
    from .models import MinecraftTrivia

    # Get the least recently used fact (nulls first, then oldest)
    trivia = MinecraftTrivia.objects.order_by(
        F('last_used').asc(nulls_first=True)
    ).first()

    if not trivia:
        return None

    # Update last_used timestamp
    trivia.last_used = timezone.now()
    trivia.save()

    return trivia.fact


def clawed_eagle_joke() -> Optional[str]:
    """Generate a lighthearted joke about ClawedEagle (special case, not in rotation)."""
    return generate_random_message(CLAWED_EAGLE_JOKE_PROMPT)


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

    # Don't include location list if this is a save-location request
    # This prevents Claude from seeing existing locations and refusing to call save_location
    include_locations = not is_save_location_request(message)

    # Allow longer responses for Minecraft gameplay questions
    allow_long_response = is_minecraft_question(message)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=build_system_prompt(
            include_locations=include_locations,
            allow_long_response=allow_long_response
        ),
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
