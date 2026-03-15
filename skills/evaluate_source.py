"""Skill: Evaluate if a discovered URL is worth crawling."""

import json
import logging
import anthropic
import config
from brain.orchestrator import register_skill

logger = logging.getLogger(__name__)

EVAL_PROMPT = """You are evaluating whether a web page is a good source for kids activity listings in NYC.

URL: {url}
Page HTML (first portion):
{html}

Evaluate this page and return a JSON object:
{{
  "is_good_source": true/false,
  "reason": "1-2 sentence explanation",
  "estimated_activities": number (how many activities could be extracted),
  "has_structured_listings": true/false (are activities listed in a structured/repeating format),
  "has_nyc_focus": true/false,
  "suggested_category": "category name or null",
  "reliability_score": 0.0 to 1.0 (how reliable/maintained does this site look)
}}

A good source has: multiple activity listings, NYC focus, structured format, maintained/updated content.
A bad source has: few/no listings, national scope without NYC filter, unstructured blog posts, outdated content.
"""


@register_skill({
    "name": "evaluate_source",
    "description": "Evaluate whether a URL is a good source for kids activity listings. Analyzes page content and returns an assessment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to evaluate",
            },
            "html": {
                "type": "string",
                "description": "HTML content of the page (from crawl_source)",
            },
        },
        "required": ["url", "html"],
    },
})
async def evaluate_source_skill(url: str, html: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    # Use first 40KB for evaluation (don't need the full page)
    html_sample = html[:40_000]

    try:
        response = await client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": EVAL_PROMPT.format(url=url, html=html_sample),
            }],
        )

        text = response.content[0].text.strip()
        if "```" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            text = text[start:end]
        elif "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            text = text[start:end]

        evaluation = json.loads(text)
        evaluation["url"] = url
        return json.dumps(evaluation)

    except Exception as e:
        logger.exception(f"Evaluation failed for {url}")
        return json.dumps({"error": str(e), "url": url, "is_good_source": False})
