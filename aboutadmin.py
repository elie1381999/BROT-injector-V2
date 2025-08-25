"""
aboutadmin.py — Admin logic and notifications (robust, safe).
"""
from datetime import datetime
from typing import Any, Dict, Optional
import time
import asyncio
import logging
import sys
import os
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("insta_bot")


async def _send_admin_message(context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode: str = "Markdown") -> bool:
    try:
        admin_chat_id = context.application.bot_data.get('admin_chat_id')
    except Exception:
        admin_chat_id = None
    if not admin_chat_id:
        logger.debug("Skipping admin message because admin_chat_id is not configured.")
        return False
    try:
        await context.bot.send_message(chat_id=admin_chat_id, text=text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.exception("Failed sending admin message")
        return False


def _md_escape_short(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s.replace("`", "\\`").replace("*", "\\*")


def _actor_from_update(update: Optional[Update]) -> dict:
    actor = {"id": None, "username": None, "name": None}
    try:
        if update and getattr(update, "effective_user", None):
            user = update.effective_user
            actor["id"] = getattr(user, "id", None)
            actor["username"] = getattr(user, "username", None)
            actor["name"] = getattr(user, "full_name", None) or (
                (getattr(user, "first_name", "") or "") + " " + (getattr(user, "last_name", "") or "")
            ).strip()
    except Exception:
        logger.exception("Error while building actor from update")
    return actor


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Central error handler. Detects Telegram 409 conflict and attempts graceful shutdown + admin notification.
    Does NOT call sys.exit() so we avoid throwing SystemExit in event loop tasks.
    """
    err = getattr(context, "error", None) if context is not None else None
    try:
        logger.exception("An error occurred: %s", err)
    except Exception:
        pass

    # If it's the Telegram 409 conflict, notify admin and try to shut down gracefully.
    try:
        s = str(err or "")
        if "Conflict: terminated by other getUpdates request" in s or "terminated by other getUpdates request" in s:
            msg_text = (
                "⚠️ *Telegram 409 Conflict detected*\n\n"
                "Another getUpdates (polling) request or webhook is using this token. "
                "Make sure only one bot instance is running and remove any webhook, or rotate the token."
            )
            logger.error("Telegram 409 Conflict detected.")
            # Try to notify admin
            try:
                if context is not None:
                    await _send_admin_message(context, msg_text)
            except Exception:
                logger.exception("Failed to notify admin about 409.")

            # Attempt graceful stop; if app not running, just log and return
            try:
                if context and getattr(context, "application", None):
                    try:
                        await context.application.stop()
                        logger.info("Requested application.stop() due to 409.")
                    except RuntimeError as e:
                        # "This Application is not running!" or similar — log and continue
                        logger.warning("Application.stop() raised RuntimeError (likely not running): %s", e)
                    except Exception:
                        logger.exception("Error while stopping application after 409.")
            except Exception:
                logger.exception("Unexpected error during shutdown attempt after 409.")

            # Do NOT call sys.exit/os._exit here. Just return and let the Application/task clean up.
            return
    except Exception:
        logger.exception("Error while processing exception context in handle_error.")

    # Generic fallback: try to notify admin about the error (non-409)
    try:
        if context is not None:
            await _send_admin_message(context, f"🚨 Bot error: `{_md_escape_short(str(err)[:1000])}`")
    except Exception:
        logger.exception("Failed to send generic admin error message.")
