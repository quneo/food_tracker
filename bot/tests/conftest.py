import os

os.environ.update(
    TELEGRAM_BOT_TOKEN="123456:TEST",
    BOT_API_SECRET="test-bot-secret-" * 3,
    BACKEND_URL="http://backend.test/api",
)
