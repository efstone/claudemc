# Claude Code Project Guide

## Project Overview

Django application that integrates Claude AI with a Minecraft server via RCON. Players can chat with "Jarvis" in-game by mentioning his name, and Claude responds using tool calls to execute Minecraft commands.

## Architecture

```
Player Chat -> Log Tailing -> Claude API -> Tool Execution -> RCON Commands -> Minecraft Server
```

## Key Files

| File | Purpose |
|------|---------|
| `jarvis/claude.py` | Claude API integration, tool definitions, system prompt |
| `jarvis/management/commands/watch_chat.py` | Main daemon that watches chat and orchestrates responses |
| `jarvis/rcon.py` | RCON client for sending commands to Minecraft server |
| `jarvis/models.py` | Database models (players, locations, chat history, responses) |
| `jarvis/commands.py` | Command whitelist for security |
| `jarvis/parsers.py` | Log file parsing for chat messages and events |
| `jarvis/explorer.py` | Explorer rewards system (hidden loot chests) |

## Claude API Integration

### Tool Definitions (`jarvis/claude.py`)

- **say**: Send chat messages to players (primary response method)
- **give**: Give items to players
- **tp**: Teleport players to coordinates or locations
- **time**: Control day/night cycle (NOT weather)
- **weather**: Control rain/storms/clear skies
- **save_location**: Save player's current position to database
- **web_search**: Search the web for Minecraft info

### Important: `tool_choice={"type": "any"}`

The API call uses `tool_choice={"type": "any"}` to force Claude to always use at least one tool. Without this, Claude sometimes responds with text directly instead of using the `say` tool, which means the message never reaches the Minecraft server.

### Conversation History

- Last 7 messages are included for context (`get_recent_history()`)
- `save_location` requests are excluded from history to ensure fresh tool calls
- History is stored in `ClaudeResponse` and `ToolExecution` models

## Running the Service

```bash
# Main chat daemon
python manage.py watch_chat

# Django dev server (for admin interface)
python manage.py runserver
```

## Security

### Command Whitelist (`jarvis/commands.py`)

Only these RCON commands are allowed:
```python
ALLOWED_COMMANDS = {'say', 'tellraw', 'give', 'tp', 'time', 'weather', 'data', 'list', 'loot', 'setblock'}
```

### Location Name Validation

The `save_location` tool rejects generic names like "home", "base", "mine", "farm" and requires specific/creative names.

## Database Models

- **MinecraftPlayer**: Links Minecraft username to Django User, tracks explorer rewards
- **ChatMessage**: Raw chat messages from log
- **Location**: Saved locations with coordinates
- **ClaudeResponse**: Claude's responses with metadata
- **ToolExecution**: Individual tool calls and RCON results
- **MinecraftTrivia**: Facts for random event messages

## Environment Variables (`.env`)

- `CLAUDE_API_KEY`: Anthropic API key
- `RCON_HOST`, `RCON_PORT`, `RCON_PASSWORD`: Minecraft RCON connection
- `MINECRAFT_LOG_PATH`: Path to server log file
- `PROD_DB_*`: PostgreSQL credentials

## Common Tasks

### Adding a player to Jarvis group
```bash
python manage.py add_jarvis_player <minecraft_username> <django_username>
```

### Testing Claude responses
Use Django shell:
```python
from jarvis.claude import chat
response = chat("TestPlayer", "jarvis, what time is it?")
print(response.tool_calls)
```

## Message Length Guidelines

- General chat/banter: Under 200 characters
- Minecraft questions: Up to 700 characters (auto-split across chat lines)

## Random Events

The daemon periodically generates:
- Trivia facts from database (`MinecraftTrivia` model)
- Special jokes when ClawedEagle is online
- Explorer reward chests in remote areas
