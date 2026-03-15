"""Telegram bot gateway — message routing and command handlers."""

import logging
from collections import defaultdict

import anthropic
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import skills  # noqa: F401 — registers all skills
from brain import orchestrator
from db.queries.activities import get_stats

logger = logging.getLogger(__name__)

# Per-user conversation history (in-memory, resets on restart)
_conversations: dict[int, list[dict]] = defaultdict(list)

MAX_HISTORY = 20  # messages per user


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _conversations[user_id] = []
    await update.message.reply_text(
        "Hey! I'm NYC Kids Activities Bot.\n\n"
        "I help you find classes, camps, events, and programs for kids across all five NYC boroughs.\n\n"
        "Try asking me things like:\n"
        '• "Music classes in Brooklyn for 5 year olds"\n'
        '• "STEM programs in Queens"\n'
        '• "Dance classes near 10023"\n'
        '• "Art camps in Manhattan for teens"\n\n'
        "Commands: /stats /help"
    )


async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**NYC Kids Activities Bot**\n\n"
        "Just type what you're looking for! I can search by:\n"
        "• Category (music, sports, art, STEM, dance, etc.)\n"
        "• Borough (Manhattan, Brooklyn, Queens, Bronx, Staten Island)\n"
        "• Neighborhood or ZIP code\n"
        "• Age range\n\n"
        "Commands:\n"
        "/start — Reset conversation\n"
        "/stats — Database statistics\n"
        "/help — This message",
        parse_mode="Markdown",
    )


async def _cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stats = await get_stats()
        await update.message.reply_text(
            f"📊 **Database Stats**\n\n"
            f"Activities: {stats['total_activities']}\n"
            f"Categories: {stats['categories']}\n"
            f"Boroughs: {stats['boroughs']}\n"
            f"Sources: {stats['active_sources']} active / {stats['total_sources']} total",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Stats command failed")
        await update.message.reply_text(f"Error fetching stats: {e}")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if not text:
        return

    client: anthropic.AsyncAnthropic = context.bot_data["anthropic_client"]

    # Manage conversation history
    history = _conversations[user_id]
    history.append({"role": "user", "content": text})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        _conversations[user_id] = history

    try:
        response = await orchestrator.run(
            client=client,
            messages=list(history),  # copy so orchestrator can mutate
            mode="query",
        )
    except Exception as e:
        logger.exception("Orchestrator error")
        response = "Sorry, something went wrong. Please try again."

    history.append({"role": "assistant", "content": response})

    # Split long messages for Telegram's 4096 char limit
    for chunk in _split_message(response):
        await update.message.reply_text(chunk, parse_mode="Markdown")


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find a good split point
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def build_application() -> Application:
    """Build the Telegram Application (does not start polling)."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Store shared resources
    app.bot_data["anthropic_client"] = anthropic.AsyncAnthropic(
        api_key=config.ANTHROPIC_API_KEY
    )

    # Register handlers
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("help", _cmd_help))
    app.add_handler(CommandHandler("stats", _cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    return app
