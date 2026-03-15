"""Claude tool-calling orchestrator — the Brain of the agent."""

import json
import logging
import anthropic
import config
from brain.prompts import query_prompt, heartbeat_prompt, crawl_prompt, discovery_prompt

logger = logging.getLogger(__name__)

# Skill registry: name → (function, tool_definition)
_skills: dict[str, tuple] = {}


def register_skill(tool_def: dict):
    """Decorator to register a skill function with its tool definition."""
    def decorator(func):
        _skills[tool_def["name"]] = (func, tool_def)
        return func
    return decorator


def get_tools(mode: str) -> list[dict]:
    """Return tool definitions available for a given mode."""
    mode_skills = {
        "query": [
            "search_activities", "get_stats",
        ],
        "heartbeat": [
            "search_activities", "crawl_source", "extract_activities",
            "discover_sources", "evaluate_source", "tag_location",
            "manage_sources", "memory_read", "memory_write", "get_stats",
        ],
        "crawl": [
            "crawl_source", "extract_activities", "tag_location",
            "manage_sources", "memory_write",
        ],
        "discovery": [
            "discover_sources", "evaluate_source", "manage_sources",
            "memory_read", "memory_write",
        ],
    }
    names = mode_skills.get(mode, mode_skills["query"])
    return [_skills[n][1] for n in names if n in _skills]


def _get_system_prompt(mode: str) -> str:
    prompts = {
        "query": query_prompt,
        "heartbeat": heartbeat_prompt,
        "crawl": crawl_prompt,
        "discovery": discovery_prompt,
    }
    return prompts.get(mode, query_prompt)()


async def run(
    client: anthropic.AsyncAnthropic,
    messages: list[dict],
    mode: str = "query",
    max_turns: int = 15,
) -> str:
    """Run the agentic tool-calling loop. Returns final text response."""
    system = _get_system_prompt(mode)
    tools = get_tools(mode)
    total_tokens = 0

    for turn in range(max_turns):
        response = await client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
        )
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # Collect text and tool_use blocks
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if not tool_calls:
            # No more tool calls — return final text
            return "\n".join(text_parts)

        # Execute tool calls
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            skill_name = tc.name
            if skill_name not in _skills:
                result = json.dumps({"error": f"Unknown skill: {skill_name}"})
            else:
                func, _ = _skills[skill_name]
                try:
                    result = await func(**tc.input)
                    if not isinstance(result, str):
                        result = json.dumps(result, default=str)
                except Exception as e:
                    logger.exception(f"Skill {skill_name} failed")
                    result = json.dumps({"error": str(e)})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return "I've reached the maximum number of steps. Here's what I found so far."
