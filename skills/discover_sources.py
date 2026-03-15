"""Skill: Autonomous web search to discover new activity listing sources."""

import json
import logging
import anthropic
import config
from brain.orchestrator import register_skill

logger = logging.getLogger(__name__)

DISCOVERY_PROMPT = """Search for websites that list kids {category} activities, classes, or programs in New York City.

Find 3-5 DIFFERENT websites that are directories or listing pages (not individual business pages).

For each, return:
- url: the specific listing/directory page URL
- name: short name for the source
- category: the activity category
- reason: why this is a good source (1 sentence)

Return a JSON array. Only include sites that actually list multiple programs/activities with details.
Do NOT include social media, PDFs, or paywalled sites.
"""


@register_skill({
    "name": "discover_sources",
    "description": "Search the web for new websites that list kids activities in NYC for a given category. Returns candidate URLs to evaluate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Activity category to search for (e.g., music, sports, art, STEM, dance)",
            },
        },
        "required": ["category"],
    },
})
async def discover_sources_skill(category: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    try:
        response = await client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            tools=[{
                "name": "web_search",
                "type": "web_search_20250305",
            }],
            messages=[{
                "role": "user",
                "content": DISCOVERY_PROMPT.format(category=category),
            }],
        )

        # Extract text from response (may have multiple content blocks due to web search)
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Try to parse JSON from the response
        text = text.strip()
        if "```" in text:
            # Extract from code block
            start = text.index("```") + 3
            if text[start:].startswith("json"):
                start = text.index("\n", start) + 1
            end = text.index("```", start)
            text = text[start:end].strip()

        # Try to find JSON array in text
        if "[" in text:
            json_start = text.index("[")
            json_end = text.rindex("]") + 1
            text = text[json_start:json_end]

        sources = json.loads(text)
        return json.dumps({
            "sources": sources,
            "count": len(sources),
            "category": category,
        })

    except Exception as e:
        logger.exception(f"Discovery failed for category {category}")
        return json.dumps({"error": str(e), "category": category})
