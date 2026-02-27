"""
Claude agent loop for the NYC Music Teacher Finder Telegram bot.

Exposes db.py query functions as Claude tools and runs an agentic loop
until Claude produces a final text response with no further tool calls.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import anthropic

import db

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

TOOLS: list[dict] = [
    {
        "name": "search_teachers",
        "description": (
            "Search for music teachers in NYC. All filters are optional — "
            "call with no arguments to return up to 10 teachers. "
            "Filters can be combined freely."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": (
                        "Instrument to filter by (e.g. 'Piano', 'Guitar', 'Violin'). "
                        "Case-insensitive substring match."
                    ),
                },
                "remote_only": {
                    "type": "boolean",
                    "description": (
                        "If true, return only teachers who offer remote/virtual lessons "
                        "(remote_virtual = 'Remote' or 'Both')."
                    ),
                },
                "name_query": {
                    "type": "string",
                    "description": "Substring to match against the teacher's name.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_teacher",
        "description": (
            "Get full details for a specific teacher by their numeric ID. "
            "Use the ID returned by search_teachers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "teacher_id": {
                    "type": "integer",
                    "description": "The teacher's numeric database ID.",
                }
            },
            "required": ["teacher_id"],
        },
    },
    {
        "name": "list_instruments",
        "description": (
            "Return a sorted list of all instruments currently offered by teachers "
            "in the database. Use this to answer 'what instruments are available?' "
            "or to show the user their options before searching."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "submit_teacher",
        "description": (
            "Submit a new teacher to the directory for review. "
            "Collect name, at least one instrument, a phone number, and a website URL "
            "from the user before calling this tool. "
            "Ask conversationally — do not use a form. "
            "Once you have all four required fields, call this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Full name of the teacher.",
                },
                "instruments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of instruments the teacher teaches.",
                },
                "phone": {
                    "type": "string",
                    "description": "Teacher's phone number.",
                },
                "website": {
                    "type": "string",
                    "description": "Teacher's website or profile URL.",
                },
                "remote_virtual": {
                    "type": "string",
                    "enum": ["In-Person", "Remote", "Both"],
                    "description": "Whether the teacher teaches in-person, remotely, or both.",
                },
                "address": {
                    "type": "string",
                    "description": "Teacher's address or general neighborhood (optional).",
                },
                "rates": {
                    "type": "string",
                    "description": "Rate information, e.g. '$60/hour' (optional).",
                },
            },
            "required": ["name", "instruments", "phone", "website"],
        },
    },
]


def _build_system_prompt() -> str:
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    return (
        f"You are the NYC Music Teacher Finder assistant. "
        f"You help people find music teachers in New York City. "
        f"You can search by instrument, teaching format (remote vs. in-person), or teacher name. "
        f"Users can also submit new teachers to the directory.\n\n"
        f"Today's date is {today} (UTC).\n\n"
        f"Guidelines:\n"
        f"- Always use the available tools to fetch live data rather than guessing.\n"
        f"- When displaying search results, show the teacher's name, instruments, "
        f"teaching format, and contact details (website and/or phone).\n"
        f"- For submissions, collect name, instruments, phone, and website conversationally "
        f"before calling submit_teacher. Do not ask for everything at once — gather details "
        f"naturally in conversation.\n"
        f"- Keep responses concise and easy to read in a chat interface.\n"
        f"- If no teachers are found, suggest trying a different search."
    )


async def _execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    db_path: str,
    submitted_by: Optional[int],
) -> str:
    """Execute a tool call and return the result as a JSON string."""
    try:
        if tool_name == "search_teachers":
            result = db.search_teachers(
                db_path,
                instrument=tool_input.get("instrument"),
                remote_only=tool_input.get("remote_only", False),
                name_query=tool_input.get("name_query"),
            )
        elif tool_name == "get_teacher":
            result = db.get_teacher(db_path, tool_input["teacher_id"])
            if result is None:
                result = {"error": f"No teacher found with ID {tool_input['teacher_id']}"}
        elif tool_name == "list_instruments":
            instruments = db.list_instruments(db_path)
            result = {"instruments": instruments}
        elif tool_name == "submit_teacher":
            row_id = db.add_pending_submission(
                db_path,
                name=tool_input["name"],
                instruments=tool_input["instruments"],
                phone=tool_input["phone"],
                website=tool_input["website"],
                remote_virtual=tool_input.get("remote_virtual", "In-Person"),
                address=tool_input.get("address"),
                rates=tool_input.get("rates"),
                submitted_by=submitted_by,
            )
            result = {"success": True, "submission_id": row_id}
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"error": str(e)}

    return json.dumps(result)


async def run_agent(
    user_message: str,
    history: list[dict],
    anthropic_client: anthropic.AsyncAnthropic,
    db_path: str,
    submitted_by: Optional[int] = None,
) -> str:
    """
    Run the Claude agent loop for a single user message.

    Args:
        user_message:     The latest message from the user.
        history:          Mutable list of prior messages (modified in-place).
        anthropic_client: Async Anthropic client instance.
        db_path:          Path to the SQLite database file.
        submitted_by:     Telegram user_id of the sender (for submissions).

    Returns:
        Final assistant text response.
    """
    history.append({"role": "user", "content": user_message})

    while True:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(),
            tools=TOOLS,
            messages=history,
        )

        # Collect tool_use blocks and text blocks from the response
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        # Append assistant turn to history
        history.append({"role": "assistant", "content": response.content})

        if not tool_use_blocks:
            # No more tool calls — return the final text
            if text_blocks:
                return text_blocks[0].text
            return "I'm sorry, I couldn't generate a response."

        # Execute all tool calls and build a tool_result turn
        tool_results = []
        for block in tool_use_blocks:
            result_content = await _execute_tool(
                block.name, block.input, db_path, submitted_by
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content,
                }
            )

        history.append({"role": "user", "content": tool_results})
