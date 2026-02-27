"""
NYC Music Teacher Finder Telegram Bot — entry point.

Setup:
    cd nyc-music-teachers-bot
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
    cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY
    python bot.py

The bot:
- /start  → welcome message + clears conversation history
- Any text → Claude agent answers using the local SQLite teacher database
- Per-user conversation history kept in memory (resets on bot restart)
- Long responses are split at Telegram's 4096-character limit
"""

import logging
import os
from collections import defaultdict

import anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from agent import run_agent

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Per-user conversation history: user_id → list of message dicts
_histories: dict[int, list[dict]] = defaultdict(list)


def _split_message(text: str) -> list[str]:
    """Split a message into chunks that fit within Telegram's limit."""
    if len(text) <= TELEGRAM_MAX_LENGTH:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:TELEGRAM_MAX_LENGTH])
        text = text[TELEGRAM_MAX_LENGTH:]
    return chunks


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _histories[user_id].clear()
    await update.message.reply_text(
        "Hi! I'm the NYC Music Teacher Finder. I can help you find music teachers "
        "across New York City. Try asking:\n\n"
        "• Find piano teachers near me\n"
        "• Who offers remote guitar lessons?\n"
        "• Show me violin teachers in Brooklyn\n"
        "• What instruments are available?\n"
        "• I want to add a teacher to the directory"
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text

    # Show typing indicator while processing
    await update.message.chat.send_action("typing")

    anthropic_client: anthropic.AsyncAnthropic = context.bot_data["anthropic_client"]
    db_path: str = context.bot_data["db_path"]
    history = _histories[user_id]

    try:
        reply = await run_agent(
            user_text,
            history,
            anthropic_client,
            db_path,
            submitted_by=user_id,
        )
    except Exception as e:
        logger.exception("Agent error for user %s: %s", user_id, e)
        reply = "Sorry, something went wrong. Please try again in a moment."

    for chunk in _split_message(reply):
        await update.message.reply_text(chunk)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]
    db_path = os.environ.get("DB_PATH", "teachers.db")

    # Initialize the database (creates tables if they don't exist)
    db.init_db(db_path)
    logger.info("Database initialized at %s", db_path)

    anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)

    app = Application.builder().token(token).build()
    app.bot_data["anthropic_client"] = anthropic_client
    app.bot_data["db_path"] = db_path

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot started")
    print("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
