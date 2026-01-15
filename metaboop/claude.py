"""
Claude Vision API integration for image keyword analysis.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import anthropic
from django.conf import settings


@dataclass
class AnalysisResult:
    """Result from Claude image analysis."""

    keywords: list[str]
    tokens_used: int
    success: bool
    error: str | None = None


STANDARD_PROMPT = """Analyze this image and generate descriptive keywords for organizing a photo library.

Generate 5-8 specific, descriptive keywords covering:
- Main subjects (people, animals, objects)
- Actions or activities shown
- Setting/location type (indoor/outdoor, urban/rural, beach, forest, etc.)
- Time of day/lighting if discernible
- Weather/atmospheric conditions if visible
- Mood or atmosphere
- Prominent colors
- Photography style if notable

Return ONLY a JSON array of lowercase keyword strings.
Example: ["sunset", "beach", "silhouette", "orange sky", "peaceful"]

If this is a screenshot, graphic, or non-photograph, include keywords about the content type."""

MINECRAFT_PROMPT = """Analyze this Minecraft screenshot and generate descriptive keywords.

Generate 5-8 specific keywords covering:
- Biome type (plains, desert, jungle, ocean, nether, end, etc.)
- Visible blocks and materials
- Structures (village, temple, fortress, player-built, etc.)
- Mobs if visible
- Items if visible
- In-game time of day and weather
- Activity shown (mining, building, exploring, combat, farming)
- Notable terrain features

Return ONLY a JSON array of lowercase keyword strings.
Example: ["jungle biome", "treehouse", "oak wood", "parrot", "daytime", "building"]"""


def get_client() -> anthropic.Anthropic:
    """Get Anthropic client using existing project settings."""
    return anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)


def analyze_image(image_path: str, is_minecraft: bool = False) -> AnalysisResult:
    """
    Analyze image with Claude Vision API and extract keywords.

    Args:
        image_path: Path to the image file
        is_minecraft: If True, use Minecraft-specific analysis prompt

    Returns:
        AnalysisResult with keywords and metadata
    """
    path = Path(image_path)

    # Determine media type
    suffix = path.suffix.lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
    }
    media_type = media_types.get(suffix)
    if not media_type:
        return AnalysisResult(
            keywords=[],
            tokens_used=0,
            success=False,
            error=f"Unsupported format: {suffix}",
        )

    # Read and encode image
    with open(path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    prompt = MINECRAFT_PROMPT if is_minecraft else STANDARD_PROMPT

    client = get_client()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        # Parse response
        text = response.content[0].text

        # Try to extract JSON from the response
        # Claude might wrap it in markdown code blocks
        if '```' in text:
            # Extract content between code blocks
            import re

            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)

        keywords = json.loads(text)

        return AnalysisResult(
            keywords=keywords,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            success=True,
        )

    except json.JSONDecodeError as e:
        return AnalysisResult(
            keywords=[],
            tokens_used=0,
            success=False,
            error=f"Failed to parse keywords JSON: {e}",
        )
    except anthropic.APIError as e:
        return AnalysisResult(
            keywords=[], tokens_used=0, success=False, error=f"API error: {e}"
        )
