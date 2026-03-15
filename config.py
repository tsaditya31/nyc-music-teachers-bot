"""Configuration from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))

# Database
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    os.environ.get("DB_URL", "postgresql://localhost:5432/nyc_kids"),
)
# Railway Postgres uses postgres:// but asyncpg needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Heartbeat
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "3600"))

# Health check
PORT = int(os.getenv("PORT", "8080"))

# Crawling
MAX_PAGE_HTML_BYTES = 80_000
MAX_PAGINATION_PAGES = 10
STALE_SOURCE_HOURS = 24
EXPIRE_ACTIVITY_DAYS = 30

# Discovery
DISCOVERY_INTERVAL_CYCLES = 6  # every 6th heartbeat
EXPIRE_INTERVAL_CYCLES = 24   # every 24th heartbeat
ACTIVITY_CATEGORIES = [
    "music", "sports", "art", "STEM", "dance", "theater",
    "coding", "swimming", "martial arts", "gymnastics",
    "tutoring", "language", "cooking", "nature",
]
