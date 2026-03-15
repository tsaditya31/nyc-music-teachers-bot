"""Skill: Read/write agent's persistent markdown memory files."""

import json
import os
from brain.orchestrator import register_skill

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")


def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)


@register_skill({
    "name": "memory_read",
    "description": "Read a markdown memory file. Available files: sources.md, crawl_log.md, decisions.md.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Memory file name (e.g., 'sources.md', 'crawl_log.md', 'decisions.md')",
            },
        },
        "required": ["file"],
    },
})
async def memory_read_skill(file: str) -> str:
    _ensure_dir()
    # Sanitize filename
    safe_name = os.path.basename(file)
    path = os.path.join(MEMORY_DIR, safe_name)
    if os.path.exists(path):
        with open(path) as f:
            content = f.read()
        return json.dumps({"file": safe_name, "content": content})
    return json.dumps({"file": safe_name, "content": "", "note": "File does not exist yet."})


@register_skill({
    "name": "memory_write",
    "description": "Write or append to a markdown memory file. Use mode='append' to add to existing content, 'write' to replace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Memory file name (e.g., 'sources.md', 'crawl_log.md', 'decisions.md')",
            },
            "content": {
                "type": "string",
                "description": "Content to write or append",
            },
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "description": "Write mode: 'write' replaces, 'append' adds to end. Default: 'append'",
            },
        },
        "required": ["file", "content"],
    },
})
async def memory_write_skill(file: str, content: str, mode: str = "append") -> str:
    _ensure_dir()
    safe_name = os.path.basename(file)
    path = os.path.join(MEMORY_DIR, safe_name)

    if mode == "append":
        existing = ""
        if os.path.exists(path):
            with open(path) as f:
                existing = f.read()
        with open(path, "w") as f:
            f.write(existing + "\n" + content if existing else content)
    else:
        with open(path, "w") as f:
            f.write(content)

    return json.dumps({"file": safe_name, "action": mode, "success": True})
