"""
aboutadmin.py — Admin logic and notifications.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import time
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
import sys                 # <<< ADD THIS

logger = logging.getLogger("insta_bot")

# ---------------- centralized admin send helper ----------------
async def _send_admin_message(context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode: str = "Markdown") -> bool:
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    if not admin_chat_id:
        logger.debug("Skipping admin message because admin_chat_id is not configured.")
        return False
    try:
        await context.bot.send_message(chat_id=admin_chat_id, text=text, parse_mode=parse_mode)
        return True
    except Exception:
        logger.exception("Failed sending admin message")
        return False

# Minimal markdown-escape for backticks and asterisks to reduce parse errors
def _md_escape_short(s: str) -> str:
    return s.replace("`", "\\`").replace("*", "\\*")

# Build actor dict from Update (prefer explicit contact if shared)
def _actor_from_update(update: Update | None) -> Dict[str, Any]:
    actor = {"id": None, "username": None, "name": None, "phone": None, "language": None}
    user = None
    if update and update.effective_user:
        user = update.effective_user
    # callback_query.from_user may be more accurate in callbacks
    if update and hasattr(update, "callback_query") and update.callback_query and update.callback_query.from_user:
        user = update.callback_query.from_user
    if user:
        actor["id"] = getattr(user, "id", None)
        actor["username"] = getattr(user, "username", None)
        actor["name"] = getattr(user, "full_name", None) or (
            getattr(user, "first_name", "") + (
                " " + getattr(user, "last_name", "") if getattr(user, "last_name", "") else ""
            )
        ).strip()
    # contact phone (if user shared contact in message)
    if update and update.message and update.message.contact:
        actor["phone"] = getattr(update.message.contact, "phone_number", None)
    # language from user_data (if available)
    if update and hasattr(update, "_user_data") and update._user_data:
        actor["language"] = update._user_data.get("language", "en")
    return actor

# Immediate admin alert (detailed)
async def _immediate_admin_alert(context: ContextTypes.DEFAULT_TYPE, actor: Dict[str, Any], action: str, target: Optional[str] = None, extra: Optional[str] = None):
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    if not admin_chat_id:
        return
    ts = datetime.utcnow().isoformat() + "Z"
    name = actor.get("name") or "unknown"
    username = actor.get("username") or "unknown"
    uid = actor.get("id") or "unknown"
    phone = actor.get("phone") or "N/A"
    language = actor.get("language") or "unknown"
    target_s = target or ""
    extra_s = f"\nExtra: {extra}" if extra else ""
    text = (
        f"🔔 *User action* — `{_md_escape_short(action)}`\n"
        f"• Name: {_md_escape_short(str(name))}\n"
        f"• Username: @{_md_escape_short(str(username))}\n"
        f"• ID: `{_md_escape_short(str(uid))}`\n"
        f"• Phone: `{_md_escape_short(str(phone))}`\n"
        f"• Language: `{_md_escape_short(str(language))}`\n"
        f"• Target: `{_md_escape_short(str(target_s)[:300])}`\n"
        f"• Date (UTC): `{ts}`{extra_s}"
    )
    try:
        await _send_admin_message(context, text)
    except Exception:
        logger.exception("Failed to send immediate admin alert")

# ---------------- buffered admin-notification system (global) ----------------
async def buffer_admin_action(context: ContextTypes.DEFAULT_TYPE, actor: Optional[dict], action: str, target: Optional[str] = None, extra: Optional[str] = None):
    """
    Stores events in application-level buffer (context.application.bot_data) and schedules
    a delayed summary ~60s after the last activity. Aggregates across all users.
    """
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    if not admin_chat_id:
        return

    app_data = context.application.bot_data
    buf: List[Dict] = app_data.setdefault("admin_action_buffer", [])
    buf.append({
        "ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "actor": actor or {},
        "action": action,
        "target": target,
        "extra": extra,
    })
    app_data["admin_last_activity_ts"] = time.time()

    prev_task: Optional[asyncio.Task] = app_data.get("_admin_timer_task")
    if prev_task and not prev_task.done():
        try:
            prev_task.cancel()
        except Exception:
            logger.debug("Previous admin summary task cancellation failed or was already done.")

    async def _delayed_send():
        try:
            await asyncio.sleep(60)
            last_ts = app_data.get("admin_last_activity_ts", 0)
            if time.time() - last_ts < 60:
                logger.debug("Activity updated; skipping sending admin summary now.")
                return
            buffer = app_data.get("admin_action_buffer", [])
            if not buffer:
                logger.debug("No buffered admin actions to send (global).")
                return
            lines = []
            lines.append(f"🗂 *User activity summary* — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            for e in buffer:
                a = e.get("actor") or {}
                uname = a.get("username") or "unknown"
                name = a.get("name") or ""
                uid = a.get("id") or ""
                phone = a.get("phone") or ""
                lang = a.get("language") or "unknown"
                act = e.get("action")
                tgt = e.get("target") or ""
                extra = e.get("extra") or ""
                lines.append(f"• {name} (@{uname}) id={uid} phone={phone} lang={lang} — {act} — target: {tgt} {('· ' + extra) if extra else ''}")
            text = "\n".join(lines)
            ok = await _send_admin_message(context, text)
            if not ok:
                logger.warning("Admin summary failed to send; check bot permissions and that admin started the bot.")
        except asyncio.CancelledError:
            logger.debug("Admin summary task cancelled due to new activity.")
            return
        except Exception:
            logger.exception("Error in admin delayed send (global)")
        finally:
            app_data["admin_action_buffer"] = []
            app_data["_admin_timer_task"] = None

    task = asyncio.create_task(_delayed_send())
    app_data["_admin_timer_task"] = task

# ---------------- error handler (409 detection) ----------------
async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    logger.exception("An error occurred: %s", err)
    try:
        s = str(err)
        if "Conflict: terminated by other getUpdates request" in s or "terminated by other getUpdates request" in s:
            msg_text = (
                "⚠️ *Telegram 409 Conflict detected*\n\n"
                "Another getUpdates (polling) request or webhook is using this token. "
                "Make sure only one bot instance is running and remove any webhook."
            )
            logger.error("Telegram 409 Conflict: stopping application.")
            admin_chat_id = context.application.bot_data.get('admin_chat_id')
            if admin_chat_id:
                try:
                    await _send_admin_message(context, msg_text)
                except Exception:
                    logger.warning("Failed to notify admin about 409.")
            try:
                await context.application.stop()
            except Exception:
                pass
            time.sleep(0.3)
            sys.exit(1)
    except Exception:
        logger.exception("Error while processing exception context.")
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ An unexpected error occurred.")
    except Exception:
        pass
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    if admin_chat_id:
        try:
            await _send_admin_message(context, f"🚨 Bot error: `{_md_escape_short(str(err)[:1000])}`")
        except Exception:

            pass
