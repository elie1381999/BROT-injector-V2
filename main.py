import os
import logging
import time
import json
import urllib.request
import urllib.error
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- Logging setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("insta_bot")

# --- Env variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# --- Telegram API helpers ---
def _telegram_api_request(path: str, timeout: int = 7) -> Optional[dict]:
    """Low-level Telegram API request."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            logger.warning("HTTPError %s: %s", e, body)
        except Exception:
            logger.warning("HTTPError %s (no body).", e)
        return None
    except Exception as e:
        logger.debug("Non-fatal _telegram_api_request error: %s", e)
        return None


def delete_webhook_sync():
    """Ensure webhook is removed before starting polling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.debug("delete_webhook_sync: TELEGRAM_BOT_TOKEN not set")
        return
    try:
        info = _telegram_api_request("getWebhookInfo")
        result = info.get("result") if info else {}
        url = result.get("url") if result else ""

        if url:
            logger.info("Existing webhook found: %s — deleting...", url)
            res = _telegram_api_request("deleteWebhook")
            logger.info("deleteWebhook response: %s", res)
            time.sleep(1.2)
            info2 = _telegram_api_request("getWebhookInfo")
            url2 = (info2.get("result") or {}).get("url") if info2 else None
            if not url2:
                logger.info("Webhook deletion verified.")
            else:
                logger.warning("Webhook still present after delete: %s", url2)
        else:
            logger.info("No webhook configured; polling is safe.")
    except Exception as e:
        logger.exception("delete_webhook_sync unexpected error: %s", e)


# --- Bot handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    msg = f"Hello {user.first_name}, I'm alive!"
    await update.message.reply_text(msg)

    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"👤 User started bot: {user.id} ({user.username})"
        )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo user messages and notify admin."""
    user = update.effective_user
    text = update.message.text
    await update.message.reply_text(f"You said: {text}")

    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📩 Message from {user.id} ({user.username}): {text}"
        )


# --- Main entrypoint ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set!")

    # Delete any webhook before polling
    delete_webhook_sync()

    # Build bot app
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logger.info("🚀 Bot starting polling mode...")
    app.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
