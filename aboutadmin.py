"""
aboutadmin.py — Admin logic and notifications (minimal, robust).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import time
import asyncio
import logging
import sys
import os
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("insta_bot")

async def _send_admin_message(context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode: str = "Markdown") -> bool:
    admin_chat_id = None
    try:
        admin_chat_id = context.application.bot_data.get('admin_chat_id')
    except Exception:
        # context might be None or malformed when called early; swallow safely
        logger.debug("context.application.bot_data not available when sending admin message.")
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
    return s.replace("`", "\\`").replace("*", "\\*")

# A very small actor builder (keeps safe attribute access)
def _actor_from_update(update: Optional[Update]) -> Dict[str, Any]:
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
    This function MUST exist and be importable by main.py as aboutadmin.handle_error
    """
    # Defensive access
    err = getattr(context, "error", None) if context is not None else None
    try:
        logger.exception("An error occurred: %s", err)
    except Exception:
        # If logger has issues, ignore
        pass

    try:
        s = str(err or "")
        if "Conflict: terminated by other getUpdates request" in s or "terminated by other getUpdates request" in s:
            msg_text = (
                "⚠️ *Telegram 409 Conflict detected*\n\n"
                "Another getUpdates (polling) request or webhook is using this token. "
                "Make sure only one bot instance is running and remove any webhook."
            )
            logger.error("Telegram 409 Conflict detected.")
            # notify admin if possible
            try:
                await _send_admin_message(context, msg_text)
            except Exception:
                logger.exception("Failed to send admin 409 notification.")
            # attempt graceful stop
            try:
                await context.application.stop()
            except Exception:
                logger.exception("Failed to stop application cleanly.")
            # short pause and exit
            time.sleep(0.3)
            try:
                sys.exit(1)
            except Exception:
                os._exit(1)
    except Exception:
        logger.exception("Error while processing exception context in handle_error.")

    # fallback notify admin about other errors
    try:
        if context is not None:
            await _send_admin_message(context, f"🚨 Bot error: `{_md_escape_short(str(err)[:1000])}`")
    except Exception:
        logger.exception("Failed to send generic admin error message.")
