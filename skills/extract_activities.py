"""Skill: Claude-powered HTML → structured activity data extraction."""
from __future__ import annotations

import json
import logging
import anthropic
import config
from brain.orchestrator import register_skill

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract ALL kids activities (classes, events, camps, programs) from this HTML page.
Return a JSON array where each element has these fields (use null if not found):
- name: string (activity/class name)
- description: string (brief description)
- category: string (music/sports/art/STEM/dance/theater/coding/swimming/martial_arts/gymnastics/tutoring/language/cooking/nature)
- subcategory: string (e.g., "piano", "soccer", "painting")
- age_range: string (e.g., "3-5", "6-12", "all ages")
- location_name: string (venue/school name)
- address: string (full street address)
- price: string (e.g., "$30/class", "free", "$250/semester")
- schedule: string (e.g., "Saturdays 10am-12pm", "Mon/Wed 3-4pm")
- contact_email: string
- contact_phone: string
- website: string (URL)
- tags: array of strings (relevant keywords)

IMPORTANT:
- Extract EVERY activity you can find, even if some fields are missing
- Infer category from context when not explicit
- Return ONLY the JSON array, no other text
- If no activities found, return []

HTML content:
"""


@register_skill({
    "name": "extract_activities",
    "description": "Extract structured activity data from HTML content using Claude. Returns a JSON array of activities found on the page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "Cleaned HTML content to extract activities from",
            },
            "source_url": {
                "type": "string",
                "description": "The URL this HTML came from (for context)",
            },
        },
        "required": ["html"],
    },
})
async def extract_activities_skill(html: str, source_url: str | None = None) -> str:
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    context = f"\nSource URL: {source_url}\n" if source_url else ""

    try:
        response = await client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + context + html,
            }],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        activities = json.loads(text)
        tokens = response.usage.input_tokens + response.usage.output_tokens

        return json.dumps({
            "activities": activities,
            "count": len(activities),
            "tokens_used": tokens,
        })

    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Failed to parse extraction result: {e}", "raw": text[:500]})
    except Exception as e:
        return json.dumps({"error": f"Extraction failed: {e}"})
