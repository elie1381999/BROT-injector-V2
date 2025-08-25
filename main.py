"""
main.py — Main entry and connection with Instagram.
"""
import os
import logging
import asyncio
import urllib.request
import urllib.error
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, PleaseWaitFewMinutes
from telegram.ext import Application
import time

import aboutteleg
import aboutadmin

# ---------------- env & logging ----------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID")  # optional

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("insta_bot")

# parse admin id
ADMIN_CHAT_ID_INT: int | None = None
if ADMIN_CHAT_ID_RAW:
    try:
        ADMIN_CHAT_ID_INT = int(ADMIN_CHAT_ID_RAW.strip())
        logger.info("Admin notifications enabled for chat_id=%s", ADMIN_CHAT_ID_INT)
    except Exception:
        logger.exception("ADMIN_CHAT_ID in .env is invalid; admin notifications disabled.")
        ADMIN_CHAT_ID_INT = None
else:
    logger.info("ADMIN_CHAT_ID not set; admin notifications disabled.")

# ---------------- Instagram wrapper ----------------
class InstagramWrapper:
    def __init__(self):
        self.client: Client | None = None
        self._lock = asyncio.Lock()
        self.login_attempts = 0
        self.last_attempt_ts = 0

    async def ensure_login(self) -> bool:
        async with self._lock:
            now = time.time()
            if self.client:
                return True
            if self.login_attempts >= 3 and now - self.last_attempt_ts < 60:
                logger.warning("Too many IG login attempts.")
                return False
            await asyncio.sleep(1)  # Delay to avoid rate limiting
            try:
                logger.info("Initializing IG client (threaded).")
                self.client = await asyncio.to_thread(Client)
                ok = await asyncio.to_thread(self.client.login, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                if ok:
                    logger.info("✅ IG login success")
                    self.login_attempts = 0
                    return True
                logger.error("IG login returned False")
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                return False
            except (LoginRequired, ChallengeRequired, PleaseWaitFewMinutes) as e:
                logger.error("IG login special error: %s", e)
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                return False
            except Exception as e:
                logger.exception("Unexpected IG login error: %s", e)
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                return False

    async def search_users(self, query: str, limit: int = 5):
        if not await self.ensure_login():
            return None
        try:
            users = await asyncio.to_thread(self.client.search_users, query)
            return (users or [])[:limit]
        except Exception:
            logger.exception("search_users failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    users = await asyncio.to_thread(self.client.search_users, query)
                    return (users or [])[:limit]
                except Exception:
                    logger.exception("search_users retry failed")
            return None

    async def get_user_info(self, user_id: int):
        if not await self.ensure_login():
            return None
        try:
            return await asyncio.to_thread(self.client.user_info, user_id)
        except KeyError as e:
            logger.warning("KeyError in user_info_gql (missing 'data' key): %s", e)
            try:
                username = await asyncio.to_thread(self.client.username_from_user_id, user_id)
                if username:
                    return await asyncio.to_thread(self.client.user_info_by_username, username)
            except Exception:
                logger.exception("Fallback user_info_by_username failed")
            return None
        except Exception:
            logger.exception("get_user_info failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    return await asyncio.to_thread(self.client.user_info, user_id)
                except Exception:
                    logger.exception("get_user_info retry failed")
            return None

    async def get_user_medias(self, user_id: int, amount: int = 40):
        if not await self.ensure_login():
            return []
        try:
            medias = await asyncio.to_thread(self.client.user_medias, user_id, amount)
            return list(medias) if medias else []
        except Exception:
            logger.exception("get_user_medias failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    medias = await asyncio.to_thread(self.client.user_medias, user_id, amount)
                    return list(medias) if medias else []
                except Exception:
                    logger.exception("get_user_medias retry failed")
            return []

    async def get_user_stories(self, user_id: int):
        if not await self.ensure_login():
            return []
        try:
            stories = await asyncio.to_thread(self.client.user_stories, user_id)
            return list(stories) if stories else []
        except Exception:
            logger.exception("get_user_stories failed")
            self.client = None
            return []

    async def get_user_highlights(self, user_id: int):
        if not await self.ensure_login():
            return []
        try:
            highlights = await asyncio.to_thread(self.client.user_highlights, user_id)
            return list(highlights) if highlights else []
        except Exception:
            logger.exception("get_user_highlights failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    highlights = await asyncio.to_thread(self.client.user_highlights, user_id)
                    return list(highlights) if highlights else []
                except Exception:
                    logger.exception("get_user_highlights retry failed")
            return []

    async def get_highlight_info(self, highlight_pk: int):
        if not await self.ensure_login():
            return None
        try:
            return await asyncio.to_thread(self.client.highlight_info, highlight_pk)
        except Exception:
            logger.exception("highlight_info failed")
            self.client = None
            return None

# ---------------- bootstrap helpers ----------------
def delete_webhook_sync():
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            _ = resp.read()
            logger.info("Called deleteWebhook() (sync) at startup.")
    except urllib.error.HTTPError as e:
        logger.warning("deleteWebhook HTTPError: %s", e)
    except Exception as e:
        logger.debug("deleteWebhook() non-fatal failure: %s", e)

# ---------------- main ----------------
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN required in .env")
        return

    delete_webhook_sync()

    insta = InstagramWrapper()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data['insta'] = insta
    app.bot_data['admin_chat_id'] = ADMIN_CHAT_ID_INT

    app.add_handler(aboutteleg.conv)
    app.add_handler(aboutteleg.help_cmd_handler)
    app.add_handler(aboutteleg.dump_media_cmd_handler)
    app.add_error_handler(aboutadmin.handle_error)

    # startup test message to admin (if configured) WITHOUT parse_mode
    async def _startup_test():
        await asyncio.sleep(1)
        if ADMIN_CHAT_ID_INT:
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID_INT,
                    text="🔔 Admin notifications enabled (startup test)."
                )
                logger.info("Startup test message sent to admin.")
            except Exception:
                logger.exception(
                    "Failed to send startup admin test message. "
                    "Make sure admin started the bot and ADMIN_CHAT_ID is correct."
                )

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_startup_test())
    except Exception:
        logger.exception("Failed to schedule admin startup test message.")

    logger.info("🚀 Bot starting polling...")
    try:
        app.run_polling(allowed_updates="all")
    except SystemExit:
        logger.info("Bot exiting.")
    except Exception as e:
        logger.exception("Unhandled exception in main polling loop: %s", e)

if __name__ == "__main__":
    main()
