import os
import logging
import asyncio
import urllib.request
import urllib.error
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, PleaseWaitFewMinutes, ClientForbiddenError
from telegram.ext import Application
import time
import socket
import random
import json
from urllib.parse import urlparse

import aboutteleg
import aboutadmin

# ---------------- env & logging ----------------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID")  # optional

# webhook-related env vars
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "1") == "1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. "https://brot-injector-v2.onrender.com"
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")  # optional custom path
PORT = int(os.getenv("PORT", "8000"))

# Instagram proxy settings (for cloud deployment)
INSTAGRAM_PROXY = os.getenv("INSTAGRAM_PROXY", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("insta_bot")

# parse admin id
ADMIN_CHAT_ID_INT = None
if ADMIN_CHAT_ID_RAW:
    try:
        ADMIN_CHAT_ID_INT = int(ADMIN_CHAT_ID_RAW.strip())
        logger.info("Admin notifications enabled for chat_id=%s", ADMIN_CHAT_ID_INT)
    except Exception:
        logger.exception("ADMIN_CHAT_ID in .env is invalid; admin notifications disabled.")
        ADMIN_CHAT_ID_INT = None
else:
    logger.info("ADMIN_CHAT_ID not set; admin notifications disabled.")

# Enhanced Markdown-escape for Telegram Markdown V2
def _md_escape_short(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    # Escape all Telegram Markdown V2 special characters
    for char in ('*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'):
        s = s.replace(char, f'\\{char}')
    return s

# ---------------- Instagram wrapper ----------------
class InstagramWrapper:
    def __init__(self):
        self.client: Client | None = None
        self._lock = asyncio.Lock()
        self.login_attempts = 0
        self.last_attempt_ts = 0
        self.session_file = "ig_session.json"
        self.proxy = INSTAGRAM_PROXY
        self.device_settings = {
            "app_version": "270.0.0.0.0",
            "android_version": 29,
            "android_release": "10",
            "dpi": "480dpi",
            "resolution": "1080x1920",
            "manufacturer": "Samsung",
            "device": "SM-G973F",
            "model": "Galaxy S10",
            "cpu": "exynos9820",
            "user_agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"
        }

    def is_valid_proxy(self, proxy_url):
        """Validate proxy URL format"""
        if not proxy_url:
            return False
            
        try:
            parsed = urlparse(proxy_url)
            # Check if scheme and netloc exist, and if port is numeric when present
            if not all([parsed.scheme, parsed.netloc]):
                return False
            if ':' in parsed.netloc:
                host, port = parsed.netloc.rsplit(':', 1)
                if not port.isdigit() or not (1 <= int(port) <= 65535):
                    return False
            return True
        except:
            return False

    async def resolve_challenge(self, challenge_exception):
        """Handle Instagram challenge requirements"""
        try:
            challenge_info = challenge_exception.args[0]
            logger.warning("Challenge required: %s", challenge_info)
            
            # Try to resolve via email (you might need to implement this differently)
            if hasattr(challenge_exception, 'challenge_url'):
                challenge_url = challenge_exception.challenge_url
                logger.info("Challenge URL: %s", challenge_url)
                
                # For now, we'll just reset the client and hope for the best
                # In a real implementation, you might want to prompt the user for a code
                self.client = None
                return False
                
        except Exception as e:
            logger.exception("Error resolving challenge: %s", e)
        return False

    async def ensure_login(self) -> bool:
        async with self._lock:
            now = time.time()
            if self.client:
                return True
            if self.login_attempts >= 3 and now - self.last_attempt_ts < 300:  # 5-minute wait
                logger.warning("Too many IG login attempts. Waiting before retry.")
                return False
            await asyncio.sleep(random.uniform(3, 7))  # Increased random delay
            try:
                logger.info("Initializing IG client (threaded).")
                self.client = await asyncio.to_thread(Client)
                
                # Set device settings
                await asyncio.to_thread(self.client.set_device, self.device_settings)
                
                # Set proxy if configured and valid
                if self.proxy and self.is_valid_proxy(self.proxy):
                    logger.info(f"Using proxy: {self.proxy}")
                    await asyncio.to_thread(self.client.set_proxy, self.proxy)
                elif self.proxy:
                    logger.warning(f"Invalid proxy URL: {self.proxy}. Continuing without proxy.")
                
                # Disable pre-login flow which often causes issues
                settings = await asyncio.to_thread(self.client.get_settings)
                settings["pre_login_flow"] = False
                await asyncio.to_thread(self.client.set_settings, settings)
                
                # Load session if exists
                if os.path.exists(self.session_file):
                    logger.info("Loading Instagram session from file.")
                    await asyncio.to_thread(self.client.load_settings, self.session_file)
                    try:
                        # Verify session with a simple request
                        await asyncio.sleep(random.uniform(2, 4))
                        await asyncio.to_thread(self.client.get_timeline_feed)
                        logger.info("✅ IG session loaded successfully")
                        self.login_attempts = 0
                        return True
                    except Exception:
                        logger.warning("Loaded session is invalid; attempting new login.")
                
                # New login with additional delays
                await asyncio.sleep(random.uniform(3, 5))
                logger.info(f"Attempting login with username: {INSTAGRAM_USERNAME}")
                ok = await asyncio.to_thread(self.client.login, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                if ok:
                    logger.info("✅ IG login success")
                    # Save session
                    await asyncio.to_thread(self.client.dump_settings, self.session_file)
                    self.login_attempts = 0
                    return True
                logger.error("IG login returned False")
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                return False
            except (LoginRequired, ChallengeRequired, PleaseWaitFewMinutes) as e:
                logger.error("IG login special error: %s", e)
                if isinstance(e, ChallengeRequired):
                    await self.resolve_challenge(e)
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                return False
            except ClientForbiddenError as e:
                logger.error("CSRF error: %s", e)
                self.login_attempts += 1
                self.last_attempt_ts = now
                self.client = None
                # Retry login after a short delay
                await asyncio.sleep(5)
                return await self.ensure_login()
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
            await asyncio.sleep(random.uniform(2, 4))  # Increased delay
            users = await asyncio.to_thread(self.client.search_users, query)
            return (users or [])[:limit]
        except Exception:
            logger.exception("search_users failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    await asyncio.sleep(random.uniform(2, 4))
                    users = await asyncio.to_thread(self.client.search_users, query)
                    return (users or [])[:limit]
                except Exception:
                    logger.exception("search_users retry failed")
            return None

    async def get_user_info(self, user_id: int):
        if not await self.ensure_login():
            return None
        try:
            await asyncio.sleep(random.uniform(2, 4))
            return await asyncio.to_thread(self.client.user_info, user_id)
        except KeyError as e:
            logger.warning("KeyError in user_info_gql (missing 'data' key): %s", e)
            try:
                username = await asyncio.to_thread(self.client.username_from_user_id, user_id)
                if username:
                    await asyncio.sleep(random.uniform(2, 4))
                    return await asyncio.to_thread(self.client.user_info_by_username, username)
            except Exception:
                logger.exception("Fallback user_info_by_username failed")
            return None
        except Exception:
            logger.exception("get_user_info failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    await asyncio.sleep(random.uniform(2, 4))
                    return await asyncio.to_thread(self.client.user_info, user_id)
                except Exception:
                    logger.exception("get_user_info retry failed")
            return None

    async def get_user_medias(self, user_id: int, amount: int = 40):
        if not await self.ensure_login():
            return []
        try:
            await asyncio.sleep(random.uniform(2, 4))
            medias = await asyncio.to_thread(self.client.user_medias, user_id, amount)
            return list(medias) if medias else []
        except Exception:
            logger.exception("get_user_medias failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    await asyncio.sleep(random.uniform(2, 4))
                    medias = await asyncio.to_thread(self.client.user_medias, user_id, amount)
                    return list(medias) if medias else []
                except Exception:
                    logger.exception("get_user_medias retry failed")
            return []

    async def get_user_stories(self, user_id: int):
        if not await self.ensure_login():
            return []
        try:
            await asyncio.sleep(random.uniform(2, 4))
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
            await asyncio.sleep(random.uniform(2, 4))
            highlights = await asyncio.to_thread(self.client.user_highlights, user_id)
            return list(highlights) if highlights else []
        except Exception:
            logger.exception("get_user_highlights failed; retrying")
            self.client = None
            if await self.ensure_login():
                try:
                    await asyncio.sleep(random.uniform(2, 4))
                    highlights = await asyncio.to_thread(self.client.user_highlights, user_id)
                    return list(highlights) if highlights else []
                except Exception:
                    logger.exception("get_user_highlights retry failed")
            return []

    async def get_highlight_info(self, highlight_pk: int):
        if not await self.ensure_login():
            return None
        try:
            await asyncio.sleep(random.uniform(2, 4))
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

async def post_start(context):
    if ADMIN_CHAT_ID_INT:
        try:
            hostname = _md_escape_short(socket.gethostname())
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID_INT,
                text=f"🔔 Admin notifications enabled (startup test). host={hostname} pid={os.getpid()}",
                parse_mode="Markdown"
            )
            logger.info("Startup test message sent to admin.")
        except Exception:
            logger.exception("Failed to send startup admin test message.")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN required in .env")
        return

    # Delete webhook at startup to ensure clean state
    delete_webhook_sync()

    insta = InstagramWrapper()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data['insta'] = insta
    app.bot_data['admin_chat_id'] = ADMIN_CHAT_ID_INT

    # Register handlers
    app.add_handler(aboutteleg.conv)
    app.add_handler(aboutteleg.help_cmd_handler)
    app.add_handler(aboutteleg.dump_media_cmd_handler)
    if hasattr(aboutadmin, "handle_error") and callable(aboutadmin.handle_error):
        app.add_error_handler(aboutadmin.handle_error)
    else:
        logger.warning("aboutadmin.handle_error not found; skipping add_error_handler.")

    # Schedule startup test job if job_queue is available
    job_queue_available = getattr(app, "job_queue", None) is not None
    if job_queue_available:
        try:
            app.job_queue.run_once(post_start, when=1)
            logger.info("Scheduled startup test job via JobQueue.")
        except Exception:
            logger.exception("Failed to schedule admin startup test job.")
    else:
        logger.warning("JobQueue not available; startup message will not be sent.")

    # Use webhook mode
    if USE_WEBHOOK and WEBHOOK_URL:
        logger.info("Starting application in WEBHOOK mode.")
        url_path = WEBHOOK_PATH.strip("/") if WEBHOOK_PATH else TELEGRAM_BOT_TOKEN.split(":")[0]
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{url_path}"
        try:
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=url_path,
                webhook_url=webhook_url,
            )
        except Exception as e:
            logger.exception("Failed to start webhook mode: %s", e)
            logger.info("Falling back to polling mode.")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                app.run_polling(allowed_updates="all")
            except SystemExit:
                logger.info("Bot exiting.")
            except Exception as e:
                logger.exception("Failed to start polling mode: %s", e)
                raise
    else:
        logger.warning("Webhook mode disabled (USE_WEBHOOK=%s, WEBHOOK_URL=%s); starting in POLLING mode.", USE_WEBHOOK, WEBHOOK_URL)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app.run_polling(allowed_updates="all")
        except SystemExit:
            logger.info("Bot exiting.")
        except Exception as e:
            logger.exception("Failed to start polling mode: %s", e)
            raise

if __name__ == "__main__":
    main()
