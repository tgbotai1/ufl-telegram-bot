import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
AGENT_API_URL = os.environ.get("AGENT_API_URL", "https://pkjzktabbahfqfh3jbrfc7rv.agents.do-ai.run")
AGENT_API_KEY = os.environ["AGENT_API_KEY"]

# Comma-separated Telegram user IDs with admin access (e.g. "123456,789012")
ADMIN_TG_IDS = set(
    int(x.strip()) for x in os.environ.get("ADMIN_TG_IDS", "").split(",") if x.strip()
)

# Whitelist: only these users can use the bot. Empty = everyone allowed.
ALLOWED_TG_IDS = set(
    int(x.strip()) for x in os.environ.get("ALLOWED_TG_IDS", "").split(",") if x.strip()
)

# Number of previous messages to include in agent context
HISTORY_CONTEXT_SIZE = int(os.environ.get("HISTORY_CONTEXT_SIZE", "10"))
