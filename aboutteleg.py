"""
aboutteleg.py — Logic for conversations and user interactions with language support.
"""
import re
import json
from typing import Any, Dict, List, Optional
import logging
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Message,
)
from telegram.error import BadRequest
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import aboutadmin

logger = logging.getLogger("insta_bot")

# ---------------- conversation states ----------------
SELECTING_LANGUAGE, CHOOSING, REPORTING = range(3)

# ---------------- translations ----------------
TRANSLATIONS = {
    "en": {
        "start_greeting": (
            "BROT injector V2 ...\n\n"
            "🤖 *Instagram Finder*\n\n"
            "Please select your language:"
        ),
        "language_prompt": "Please select your language:",
        "main_menu_search": "Search",
        "main_menu_help": "Help",
        "main_menu_report": "Report",
        "main_menu_yes": "Yes",
        "main_menu_no": "No",
        "quick_menu": "Quick menu:",
        "help_text": (
            "Usage:\n"
            "- Send a username (e.g. `natgeo`) or paste a profile URL.\n"
            "- Bot will auto-find the account and display profile + actions (Posts / Stories / Highlights / Tracking).\n"
            "- Press Posts/Stories/Highlights to see media while keeping the profile visible.\n\n"
            "If Instagram blocks requests, wait a while and try again."
        ),
        "search_prompt": "🔍 Send a username (or paste an Instagram profile URL):",
        "no_text": "Please send a username or choose an option from the menu.",
        "search_failed": "❌ Search failed (Instagram might be blocking requests). Try again later.",
        "no_users_found": "No users found for '{}'.",
        "profile_caption": (
            "👤 [{}](https://instagram.com/{})\n"
            "📛 {}\n"
            "📝 {}\n"
            "• Followers: {}\n"
            "• Following: {}\n"
            "• Posts: {}\n"
            "🔒 Private: {}\n"
            "✅ Verified: {}"
        ),
        "profile_fallback": "👤 *{}*\nFull Name: {}",
        "fetch_failed": "Failed to fetch detailed user info",
        "send_failed": "Failed to deliver profile picture+info; sending text fallback",
        "send_fallback_failed": "Failed to send text fallback",
        "report_prompt": "✉️ Please type your report message; it will be forwarded to the admin.",
        "report_empty": "Empty report. Cancelled.",
        "report_sent": "✅ Report sent. Thank you!",
        "report_failed": "Failed to send report to admin.",
        "no_admin": "No admin configured to receive reports. (ADMIN_CHAT_ID not set)",
        "no_user_selected": "⚠️ No user selected. Start a new search.",
        "fetching_posts": "⏳ Fetching recent posts...",
        "no_posts": "❌ No posts or failed to fetch.",
        "posts_navigation": "Posts — navigation:",
        "no_media": "No sendable media on this page.",
        "fetching_stories": "⏳ Fetching stories...",
        "no_stories": "⚠️ No stories available or cannot fetch.",
        "stories_shown": "Stories shown. (Profile remains above.)",
        "fetching_highlights": "⏳ Fetching highlights...",
        "no_highlights": "⚠️ No highlights found.",
        "select_highlight": "Select a highlight message above to open it.",
        "invalid_highlight": "⚠️ Invalid highlight id.",
        "fetching_highlight": "⏳ Fetching highlight contents...",
        "no_highlight_info": "❌ Failed to fetch highlight info.",
        "no_highlight_items": "⚠️ No items in this highlight.",
        "highlights_shown": "Highlights shown. (Profile remains above.)",
        "tracking_message": "📡 Tracking feature is coming soon!",
        "profile_closed": "Profile closed. Use the menu to search again.",
        "profile_menu": "Profile menu:",
        "unknown_action": "Unknown action.",
        "dump_media_usage": "Usage: /dump_media <index>",
        "no_media_cached": "No cached raw media found. Fetch posts first (view_posts).",
        "index_out_of_range": "Index out of range. Range: 0..{}",
        "dump_media_failed": "Failed to dump media.",
        "not_authorized": "❌ You are not authorized to use this command.",
        "button_posts": "🖼 Posts",
        "button_stories": "📺 Stories",
        "button_highlights": "⭐ Highlights",
        "button_tracking": "📡 Tracking",
        "button_close": "❌ Close",
        "button_prev": "⬅️ Prev",
        "button_next": "Next ➡️",
        "button_back": "⬅️ Back",
        "button_search": "🔎 Search",
        "button_help": "❓ Help",
        "button_report": "✉️ Report",
        "button_open": "Open",
        "lang_en": "English",
        "lang_ru": "Russian",
    },
    "ru": {
        "start_greeting": (
            "BROT injector V2 ...\n\n"
            "🤖 *Поиск в Instagram*\n\n"
            "Пожалуйста, выберите язык:"
        ),
        "language_prompt": "Пожалуйста, выберите язык:",
        "main_menu_search": "Поиск",
        "main_menu_help": "Помощь",
        "main_menu_report": "Сообщить",
        "main_menu_yes": "Да",
        "main_menu_no": "Нет",
        "quick_menu": "Быстрое меню:",
        "help_text": (
            "Использование:\n"
            "- Отправьте имя пользователя (например, `natgeo`) или вставьте URL профиля.\n"
            "- Бот автоматически найдет аккаунт и отобразит профиль + действия (Посты / Истории / Хайлайты / Отслеживание).\n"
            "- Нажмите Посты/Истории/Хайлайты, чтобы просмотреть медиа, сохраняя профиль видимым.\n\n"
            "Если Instagram блокирует запросы, подождите и попробуйте снова."
        ),
        "search_prompt": "🔍 Отправьте имя пользователя (или вставьте URL профиля Instagram):",
        "no_text": "Пожалуйста, отправьте имя пользователя или выберите опцию из меню.",
        "search_failed": "❌ Поиск не удался (Instagram может блокировать запросы). Попробуйте позже.",
        "no_users_found": "Пользователи не найдены для '{}'.",
        "profile_caption": (
            "👤 [{}](https://instagram.com/{})\n"
            "📛 {}\n"
            "📝 {}\n"
            "• Подписчики: {}\n"
            "• Подписки: {}\n"
            "• Посты: {}\n"
            "🔒 Приватный: {}\n"
            "✅ Проверенный: {}"
        ),
        "profile_fallback": "👤 *{}*\nПолное имя: {}",
        "fetch_failed": "Не удалось получить подробную информацию о пользователе",
        "send_failed": "Не удалось отправить фото профиля+информацию; отправляется текстовый вариант",
        "send_fallback_failed": "Не удалось отправить текстовый вариант",
        "report_prompt": "✉️ Введите ваше сообщение для отчета; оно будет отправлено администратору.",
        "report_empty": "Пустой отчет. Отменено.",
        "report_sent": "✅ Отчет отправлен. Спасибо!",
        "report_failed": "Не удалось отправить отчет администратору.",
        "no_admin": "Администратор не настроен для получения отчетов. (ADMIN_CHAT_ID не установлен)",
        "no_user_selected": "⚠️ Пользователь не выбран. Начните новый поиск.",
        "fetching_posts": "⏳ Загрузка последних постов...",
        "no_posts": "❌ Нет постов или не удалось загрузить.",
        "posts_navigation": "Посты — навигация:",
        "no_media": "Нет медиа для отправки на этой странице.",
        "fetching_stories": "⏳ Загрузка историй...",
        "no_stories": "⚠️ Нет доступных историй или не удалось загрузить.",
        "stories_shown": "Истории показаны. (Профиль остается выше.)",
        "fetching_highlights": "⏳ Загрузка хайлайтов...",
        "no_highlights": "⚠️ Хайлайты не найдены.",
        "select_highlight": "Выберите сообщение хайлайта выше, чтобы открыть его.",
        "invalid_highlight": "⚠️ Неверный ID хайлайта.",
        "fetching_highlight": "⏳ Загрузка содержимого хайлайта...",
        "no_highlight_info": "❌ Не удалось загрузить информацию о хайлайте.",
        "no_highlight_items": "⚠️ Нет элементов в этом хайлайте.",
        "highlights_shown": "Хайлайты показаны. (Профиль остается выше.)",
        "tracking_message": "📡 Функция отслеживания скоро появится!",
        "profile_closed": "Профиль закрыт. Используйте меню для нового поиска.",
        "profile_menu": "Меню профиля:",
        "unknown_action": "Неизвестное действие.",
        "dump_media_usage": "Использование: /dump_media <index>",
        "no_media_cached": "Кэшированные медиа не найдены. Сначала загрузите посты (view_posts).",
        "index_out_of_range": "Индекс вне диапазона. Диапазон: 0..{}",
        "dump_media_failed": "Не удалось выгрузить медиа.",
        "not_authorized": "❌ У вас нет прав для использования этой команды.",
        "button_posts": "🖼 Посты",
        "button_stories": "📺 Истории",
        "button_highlights": "⭐ Хайлайты",
        "button_tracking": "📡 Отслеживание",
        "button_close": "❌ Закрыть",
        "button_prev": "⬅️ Назад",
        "button_next": "Далее ➡️",
        "button_back": "⬅️ Вернуться",
        "button_search": "🔎 Поиск",
        "button_help": "❓ Помощь",
        "button_report": "✉️ Сообщить",
        "button_open": "Открыть",
        "lang_en": "Английский",
        "lang_ru": "Русский",
    }
}

# ---------------- reply keyboard (persistent menu) ----------------
def get_main_menu(language: str = "en") -> ReplyKeyboardMarkup:
    t = TRANSLATIONS[language]
    return ReplyKeyboardMarkup(
        [[t["main_menu_search"], t["main_menu_help"], t["main_menu_report"]]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ---------------- helpers ----------------
URL_RE = re.compile(
    r"https?://[^\s'\"\\]+\.(?:jpe?g|png|webp|gif|mp4|m3u8|mov)(\?[^\s'\"\\]*)?",
    re.IGNORECASE,
)

def fmt_num(n: Optional[int]) -> str:
    return "N/A" if n is None else f"{n:,}"

def model_to_dict(obj: Any) -> Dict:
    try:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
    except Exception:
        pass
    d = {}
    for attr in dir(obj):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(obj, attr)
            if callable(val):
                continue
            d[attr] = val
        except Exception:
            continue
    return d

def find_urls_in_obj(obj: Any) -> List[str]:
    found = []
    seen = set()
    def _walk(x):
        if x is None:
            return
        if isinstance(x, str):
            for m in URL_RE.finditer(x):
                url = m.group(0)
                if url not in seen:
                    seen.add(url)
                    found.append(url)
            return
        if isinstance(x, dict):
            keys_order = ("video_url", "display_url", "display_src", "thumbnail_url", "image_url", "url", "src", "secure_url")
            for k in keys_order:
                if k in x:
                    _walk(x[k])
            for v in x.values():
                _walk(v)
            return
        if isinstance(x, (list, tuple, set)):
            for item in x:
                _walk(item)
            return
        try:
            s = str(x)
            for m in URL_RE.finditer(s):
                url = m.group(0)
                if url not in seen:
                    seen.add(url)
                    found.append(url)
        except Exception:
            pass
    _walk(obj)
    return found

def choose_best_url(urls: List[str], prefer_video: bool = False) -> Optional[str]:
    if not urls:
        return None
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    if prefer_video:
        for u in uniq:
            if re.search(r"\.mp4(\?|$)|\.m3u8(\?|$)|/v/", u, re.IGNORECASE):
                return u
    return uniq[0]

def safe_caption(media: Any) -> str:
    try:
        caption = getattr(media, "caption_text", None) or getattr(media, "caption", None) or getattr(media, "title", None)
        if isinstance(caption, str) and caption.strip():
            return caption.strip()
        dd = model_to_dict(media)
        for key in ("caption_text", "caption", "title", "text", "description"):
            v = dd.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        emtc = dd.get("edge_media_to_caption")
        if isinstance(emtc, dict):
            edges = emtc.get("edges") or []
            if edges and isinstance(edges[0], dict):
                node = edges[0].get("node", {})
                text = node.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    except Exception:
        pass
    return "No caption"

def extract_media_items(media: Any) -> List[Dict]:
    items = []
    try:
        dd = model_to_dict(media)
        pk = dd.get("pk") or dd.get("id") or getattr(media, "pk", None) or getattr(media, "id", None)

        carousel_keys = ("carousel_media", "resources", "items", "carousel_items")
        for ck in carousel_keys:
            block = dd.get(ck)
            if isinstance(block, list) and block:
                for sub in block:
                    sdict = model_to_dict(sub)
                    prefer_video = bool(sdict.get("is_video") or sdict.get("media_type") == 2)
                    urls = find_urls_in_obj(sdict)
                    url = choose_best_url(urls, prefer_video=prefer_video)
                    if url is not None:
                        try:
                            url = str(url)
                        except Exception:
                            pass
                    kind = "video" if (prefer_video or (url and re.search(r"\.mp4(\?|$)|\.m3u8", url or "", re.I))) else "photo"
                    caption = safe_caption(sub)
                    items.append({"url": url, "kind": kind, "caption": caption, "pk": pk})
                return items

        prefer_video = bool(dd.get("is_video") or dd.get("media_type") == 2 or dd.get("type") == "video")
        urls = find_urls_in_obj(dd)
        url = choose_best_url(urls, prefer_video=prefer_video)
        if url is not None:
            try:
                url = str(url)
            except Exception:
                pass
        kind = "video" if (prefer_video or (url and re.search(r"\.mp4(\?|$)|\.m3u8", url or "", re.I))) else "photo"
        caption = safe_caption(media)
        items.append({"url": url, "kind": kind, "caption": caption, "pk": pk})
        return items
    except Exception:
        logger.exception("extract_media_items unexpected error")
    try:
        pk = getattr(media, "pk", None) or getattr(media, "id", None)
    except Exception:
        pk = None
    items.append({"url": None, "kind": "photo", "caption": safe_caption(media), "pk": pk})
    logger.debug("extract_media_items: fallback for media pk=%s", pk)
    return items

# ---------------- inline keyboard for profile actions ----------------
def profile_actions_keyboard(language: str = "en", include_stories: bool = True, include_highlights: bool = True) -> InlineKeyboardMarkup:
    t = TRANSLATIONS[language]
    kb = [
        [InlineKeyboardButton(t["button_posts"], callback_data="view_posts")],
        [InlineKeyboardButton(t["button_stories"], callback_data="view_stories")] if include_stories else [],
        [InlineKeyboardButton(t["button_highlights"], callback_data="view_highlights")] if include_highlights else [],
        [InlineKeyboardButton(t["button_tracking"], callback_data="view_tracking")],
        [InlineKeyboardButton(t["button_close"], callback_data="close_profile")],
    ]
    kb = [row for row in kb if row]
    return InlineKeyboardMarkup(kb)

LANGUAGE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton(TRANSLATIONS["en"]["lang_en"], callback_data="lang:en")],
    [InlineKeyboardButton(TRANSLATIONS["ru"]["lang_ru"], callback_data="lang:ru")],
])

START_INLINE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton(TRANSLATIONS["en"]["button_search"], callback_data="start_search")],
    [InlineKeyboardButton(TRANSLATIONS["en"]["button_help"], callback_data="start_help")],
    [InlineKeyboardButton(TRANSLATIONS["en"]["button_report"], callback_data="start_report")],
])

def extract_username_from_text(text: str) -> str:
    text = text.strip()
    m = re.search(r"instagram\.com/([^/?#\s]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip("/")
    return text

# ---------------- profile send helper (prefers HD profile pic) ----------------
async def send_profile_info_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_obj: Any) -> Message | None:
    """
    Fetch user info and send profile picture (HD preferred) + detailed caption.
    Returns the sent Message if possible.
    """
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    insta = context.application.bot_data['insta']
    try:
        info = await insta.get_user_info(user_obj.pk)
    except Exception:
        logger.exception(t["fetch_failed"])
        info = None

    # Use stored actor data
    actor = {
        "id": context.user_data.get("last_actor_id") or None,
        "username": context.user_data.get("last_actor_username") or None,
        "name": context.user_data.get("last_actor_name") or None,
        "phone": context.user_data.get("last_actor_phone") or None,
        "language": language,
    }

    if not info:
        text_out = t["profile_fallback"].format(
            getattr(user_obj, 'username', str(user_obj)),
            getattr(user_obj, 'full_name', 'N/A')
        )
        try:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text_out,
                parse_mode="Markdown",
                reply_markup=profile_actions_keyboard(language=language)
            )
            await aboutadmin.buffer_admin_action(context, actor, "profile_shown", getattr(user_obj, "username", None), "no detailed info (private/blocked)")
            await aboutadmin._immediate_admin_alert(context, actor, "profile_shown", getattr(user_obj, "username", None), "no detailed info (private/blocked)")
            return msg
        except Exception:
            logger.exception(t["send_fallback_failed"])
            return None

    # Prefer HD profile pic when available
    profile_pic_url = getattr(info, "profile_pic_url_hd", None) or getattr(info, "profile_pic_url", None)
    if profile_pic_url is not None:
        try:
            profile_pic_url = str(profile_pic_url)
        except Exception:
            logger.debug("Failed to convert profile_pic_url to string")

    context.user_data["profile_pic_url"] = profile_pic_url
    caption = t["profile_caption"].format(
        info.username,
        info.username,
        info.full_name or 'N/A',
        getattr(info, 'biography', '') or 'N/A',
        fmt_num(getattr(info, 'follower_count', None)),
        fmt_num(getattr(info, 'following_count', None)),
        fmt_num(getattr(info, 'media_count', None)),
        t["main_menu_yes"] if getattr(info, 'is_private', False) else t["main_menu_no"],
        t["main_menu_yes"] if getattr(info, 'is_verified', False) else t["main_menu_no"]
    )
    try:
        if profile_pic_url:
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=profile_pic_url,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=profile_actions_keyboard(language=language)
            )
        else:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=profile_actions_keyboard(language=language)
            )
        extra = "private" if getattr(info, "is_private", False) else None
        await aboutadmin.buffer_admin_action(context, actor, "profile_shown", info.username, extra)
        await aboutadmin._immediate_admin_alert(context, actor, "profile_shown", info.username, extra)
        return msg
    except Exception:
        logger.exception(t["send_failed"])
        try:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=profile_actions_keyboard(language=language)
            )
            extra = "private" if getattr(info, "is_private", False) else None
            await aboutadmin.buffer_admin_action(context, actor, "profile_shown", getattr(user_obj, "username", None), f"text fallback{(' · ' + extra) if extra else ''}")
            await aboutadmin._immediate_admin_alert(context, actor, "profile_shown", getattr(user_obj, "username", None), f"text fallback{(' · ' + extra) if extra else ''}")
            return msg
        except Exception:
            logger.exception(t["send_fallback_failed"])
            return None

# ---------------- start / language selection / help / UI ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    try:
        await update.message.reply_text(t["start_greeting"], parse_mode="Markdown", reply_markup=LANGUAGE_KB)
        await update.message.reply_text(t["quick_menu"], reply_markup=get_main_menu(language))
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=t["start_greeting"],
                parse_mode="Markdown",
                reply_markup=LANGUAGE_KB
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=t["quick_menu"],
                reply_markup=get_main_menu(language)
            )
        except Exception:
            pass
    context.user_data.pop("expecting_username", None)
    return SELECTING_LANGUAGE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest:
        logger.debug("Ignored BadRequest while answering language selection callback.")
    data = query.data or ""
    if not data.startswith("lang:"):
        await query.message.reply_text("Invalid selection. Please choose a language.", reply_markup=LANGUAGE_KB)
        return SELECTING_LANGUAGE
    language = data.split(":", 1)[1]
    if language not in TRANSLATIONS:
        language = "en"
    context.user_data["language"] = language
    t = TRANSLATIONS[language]
    try:
        await query.message.edit_text(
            t["start_greeting"].replace(t["language_prompt"], t["search_prompt"]),
            parse_mode="Markdown",
            reply_markup=START_INLINE_KB
        )
        await query.message.reply_text(t["quick_menu"], reply_markup=get_main_menu(language))
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=t["start_greeting"].replace(t["language_prompt"], t["search_prompt"]),
                parse_mode="Markdown",
                reply_markup=START_INLINE_KB
            )
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=t["quick_menu"],
                reply_markup=get_main_menu(language)
            )
        except Exception:
            pass
    return CHOOSING

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    if update.callback_query:
        await update.callback_query.message.reply_text(t["help_text"], parse_mode="Markdown", reply_markup=get_main_menu(language))
    else:
        await update.message.reply_text(t["help_text"], parse_mode="Markdown", reply_markup=get_main_menu(language))
    return CHOOSING

# ---------------- main text handler ----------------
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(t["no_text"], reply_markup=get_main_menu(language))
        return CHOOSING

    # build actor info (and save to user_data for callbacks)
    actor = aboutadmin._actor_from_update(update)
    if actor.get("phone"):
        context.user_data["last_actor_phone"] = actor.get("phone")
    context.user_data["last_actor_id"] = actor.get("id")
    context.user_data["last_actor_username"] = actor.get("username")
    context.user_data["last_actor_name"] = actor.get("name")
    context.user_data["last_actor_phone"] = context.user_data.get("last_actor_phone")  # keep previous if any

    # handle reply-keyboard shortcuts
    if context.user_data.get("expecting_username"):
        context.user_data.pop("expecting_username", None)
        # allow the message to be treated as username (fall through)
    if text.lower() == t["main_menu_search"].lower():
        context.user_data["expecting_username"] = True
        await update.message.reply_text(t["search_prompt"], reply_markup=get_main_menu(language))
        return CHOOSING
    if text.lower() == t["main_menu_help"].lower():
        return await help_cmd(update, context)
    if text.lower() == t["main_menu_report"].lower():
        await update.message.reply_text(t["report_prompt"], reply_markup=ReplyKeyboardRemove())
        return REPORTING

    try:
        await update.message.chat.send_action("typing")
    except Exception:
        pass

    username_q = extract_username_from_text(text)

    # Buffer and immediately notify admin about the search
    await aboutadmin.buffer_admin_action(context, actor, "searched", username_q, f"chat_id={update.effective_chat.id}")
    await aboutadmin._immediate_admin_alert(context, actor, "searched", username_q, f"chat_id={update.effective_chat.id}")

    insta = context.application.bot_data['insta']
    users = await insta.search_users(username_q)
    if users is None:
        await update.message.reply_text(t["search_failed"], reply_markup=get_main_menu(language))
        return CHOOSING
    if not users:
        await update.message.reply_text(t["no_users_found"].format(username_q), reply_markup=get_main_menu(language))
        return CHOOSING

    selected = users[0]
    context.user_data["current_user"] = selected
    msg = await send_profile_info_to_chat(context, update.effective_chat.id, selected)
    if msg:
        context.user_data["profile_message_id"] = msg.message_id
        context.user_data["profile_chat_id"] = msg.chat.id
    return CHOOSING

# ---------------- report handling ----------------
async def handle_report_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(t["report_empty"], reply_markup=get_main_menu(language))
        return CHOOSING
    actor = aboutadmin._actor_from_update(update)
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    # immediate admin send of report
    if admin_chat_id:
        try:
            report_text = (
                f"📣 *User report*\n"
                f"From: {aboutadmin._md_escape_short(str(actor.get('name') or 'unknown'))} (@{aboutadmin._md_escape_short(str(actor.get('username') or 'unknown'))}) id={actor.get('id')}\n"
                f"Phone: `{aboutadmin._md_escape_short(str(actor.get('phone') or 'N/A'))}`\n"
                f"Language: `{aboutadmin._md_escape_short(actor.get('language') or 'unknown')}`\n"
                f"Chat: {update.effective_chat.id}\n\n"
                f"{aboutadmin._md_escape_short(text[:2000])}"
            )
            await aboutadmin._send_admin_message(context, report_text)
            await aboutadmin.buffer_admin_action(context, actor, "report_sent", None, f"chat_id={update.effective_chat.id}")
            await aboutadmin._immediate_admin_alert(context, actor, "report_sent", None, f"chat_id={update.effective_chat.id}")
            await update.message.reply_text(t["report_sent"], reply_markup=get_main_menu(language))
        except Exception:
            logger.exception(t["report_failed"])
            await update.message.reply_text(t["report_failed"], reply_markup=get_main_menu(language))
    else:
        await update.message.reply_text(t["no_admin"], reply_markup=get_main_menu(language))
    return CHOOSING

# ---------------- Posts paging helper (4 per page) ----------------
async def _send_posts_page_for_query(query, context: ContextTypes.DEFAULT_TYPE, page_index: int):
    """
    Send page_index of posts (4 per page). Each page sent as a media_group where possible.
    """
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    # answer callback but catch BadRequest if old
    try:
        await query.answer()
    except BadRequest:
        logger.debug("Ignored BadRequest while answering callback in posts pager.")
    user = context.user_data.get("current_user")
    actor = {
        "id": context.user_data.get("last_actor_id"),
        "username": context.user_data.get("last_actor_username"),
        "name": context.user_data.get("last_actor_name"),
        "phone": context.user_data.get("last_actor_phone"),
        "language": language,
    }

    if not user:
        try:
            await query.message.reply_text(t["no_user_selected"], reply_markup=get_main_menu(language))
        except Exception:
            pass
        return

    media_items: List[Dict] = context.user_data.get("media_items", [])
    page_size: int = 4
    insta = context.application.bot_data['insta']
    if not media_items:
        try:
            medias = await insta.get_user_medias(user.pk, amount=80)
        except Exception:
            medias = []
        if not medias:
            await query.message.reply_text(t["no_posts"], reply_markup=get_main_menu(language))
            return
        context.user_data["last_medias_raw"] = [model_to_dict(m) for m in medias]
        media_items = []
        for m in medias:
            subs = extract_media_items(m)
            for si in subs:
                if si.get("url"):
                    media_items.append(si)
        context.user_data["media_items"] = media_items

    total_pages = (len(media_items) + page_size - 1) // page_size if media_items else 1
    page_index = max(0, min(page_index, total_pages - 1))
    start = page_index * page_size
    end = start + page_size
    items = media_items[start:end]

    # buffer and immediate admin notification for page view
    await aboutadmin.buffer_admin_action(context, actor, "viewed_posts_page", getattr(user, "username", None), f"page={page_index+1}/{total_pages}")
    await aboutadmin._immediate_admin_alert(context, actor, "viewed_posts_page", getattr(user, "username", None), f"page={page_index+1}/{total_pages}")

    chat_id = query.message.chat.id
    sent_any = False

    group = []
    for mi in items:
        url = mi.get("url")
        if not url:
            continue
        try:
            url = str(url)
        except Exception:
            pass
        kind = mi.get("kind", "photo")
        cap = (mi.get("caption") or "")[:1024]
        try:
            if kind == "video" or re.search(r"\.mp4(\?|$)|\.m3u8", url or "", re.I):
                group.append(InputMediaVideo(media=url, caption=(cap or None)))
            else:
                group.append(InputMediaPhoto(media=url, caption=(cap or None)))
        except Exception:
            logger.exception("Failed to build InputMedia for url: %s", url)

    if group:
        try:
            await context.bot.send_media_group(chat_id=chat_id, media=group)
            sent_any = True
        except Exception:
            logger.exception("send_media_group failed; falling back to individual sends")
            for im in group:
                try:
                    if isinstance(im, InputMediaVideo):
                        await context.bot.send_video(chat_id=chat_id, video=str(im.media), caption=im.caption)
                    else:
                        await context.bot.send_photo(chat_id=chat_id, photo=str(im.media), caption=im.caption)
                    sent_any = True
                except Exception:
                    logger.exception("Failed to send an individual media in fallback")

    nav_buttons = []
    if page_index > 0:
        nav_buttons.append(InlineKeyboardButton(t["button_prev"], callback_data=f"posts_page:{page_index-1}"))
    nav_buttons.append(InlineKeyboardButton(f"Page {page_index+1}/{total_pages}", callback_data="noop"))
    if page_index < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t["button_next"], callback_data=f"posts_page:{page_index+1}"))
    nav_buttons.append(InlineKeyboardButton(t["button_back"], callback_data="profile_menu"))
    nav_kb = InlineKeyboardMarkup([nav_buttons])

    if not sent_any:
        await query.message.reply_text(t["no_media"], reply_markup=nav_kb)
    else:
        await query.message.reply_text(t["posts_navigation"], reply_markup=nav_kb)

    context.user_data["media_page_index"] = page_index
    context.user_data["media_page_size"] = page_size
    return

# ---------------- central callback handler ----------------
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    # answer callback quickly; ignore BadRequest "Query is too old..." errors
    try:
        await query.answer()
    except BadRequest as e:
        logger.debug("Ignored BadRequest while answering callback: %s", e)
    except Exception:
        logger.exception("Unexpected error while answering callback")

    data = query.data or ""

    # update last actor info from callback user for accurate admin reporting
    cb_user = query.from_user
    if cb_user:
        context.user_data["last_actor_id"] = cb_user.id
        context.user_data["last_actor_username"] = cb_user.username
        context.user_data["last_actor_name"] = cb_user.full_name
        # phone won't be present here unless a contact was shared; leave previous phone if any

    if data == "start_search":
        context.user_data["expecting_username"] = True
        try:
            await query.message.reply_text(t["search_prompt"], reply_markup=get_main_menu(language))
        except Exception:
            pass
        return
    if data == "start_help":
        await help_cmd(update, context)
        return
    if data == "start_report":
        try:
            await query.message.reply_text(t["report_prompt"], reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
        return

    if data.startswith("lang:"):
        return await select_language(update, context)

    user = context.user_data.get("current_user")
    if not user and not data.startswith("start_"):
        try:
            await query.message.reply_text(t["no_user_selected"], reply_markup=get_main_menu(language))
        except Exception:
            pass
        return

    insta = context.application.bot_data['insta']

    if data == "view_posts":
        actor = {
            "id": context.user_data.get("last_actor_id"),
            "username": context.user_data.get("last_actor_username"),
            "name": context.user_data.get("last_actor_name"),
            "phone": context.user_data.get("last_actor_phone"),
            "language": language,
        }
        await aboutadmin.buffer_admin_action(context, actor, "requested_posts", getattr(user, "username", None))
        await aboutadmin._immediate_admin_alert(context, actor, "requested_posts", getattr(user, "username", None))
        await query.message.reply_text(t["fetching_posts"])
        try:
            medias = await insta.get_user_medias(user.pk, amount=80)
        except Exception:
            medias = []
        if not medias:
            await query.message.reply_text(t["no_posts"], reply_markup=get_main_menu(language))
            return
        context.user_data["last_medias_raw"] = [model_to_dict(m) for m in medias]
        media_items = []
        for m in medias:
            subs = extract_media_items(m)
            for si in subs:
                if si.get("url"):
                    media_items.append(si)
        context.user_data["media_items"] = media_items
        await _send_posts_page_for_query(query, context, 0)
        return

    if data.startswith("posts_page:"):
        try:
            page = int(data.split(":", 1)[1])
        except Exception:
            page = 0
        await _send_posts_page_for_query(query, context, page)
        return

    if data == "view_stories":
        actor = {
            "id": context.user_data.get("last_actor_id"),
            "username": context.user_data.get("last_actor_username"),
            "name": context.user_data.get("last_actor_name"),
            "phone": context.user_data.get("last_actor_phone"),
            "language": language,
        }
        await aboutadmin.buffer_admin_action(context, actor, "requested_stories", getattr(user, "username", None))
        await aboutadmin._immediate_admin_alert(context, actor, "requested_stories", getattr(user, "username", None))
        await query.message.reply_text(t["fetching_stories"])
        stories = await insta.get_user_stories(user.pk)
        if not stories:
            await query.message.reply_text(t["no_stories"], reply_markup=profile_actions_keyboard(language=language))
            return
        for s in stories:
            subs = extract_media_items(s)
            for si in subs:
                url = si.get("url")
                if not url:
                    continue
                try:
                    url = str(url)
                except Exception:
                    pass
                cap = (si.get("caption") or "")[:1024]
                try:
                    if si.get("kind") == "video" or re.search(r"\.mp4(\?|$)|\.m3u8", url or "", re.I):
                        await context.bot.send_video(chat_id=query.message.chat.id, video=url, caption=(cap or None))
                    else:
                        await context.bot.send_photo(chat_id=query.message.chat.id, photo=url, caption=(cap or None))
                except Exception:
                    logger.exception("Failed to send story item")
        await query.message.reply_text(t["stories_shown"], reply_markup=profile_actions_keyboard(language=language))
        return

    if data == "view_highlights":
        actor = {
            "id": context.user_data.get("last_actor_id"),
            "username": context.user_data.get("last_actor_username"),
            "name": context.user_data.get("last_actor_name"),
            "phone": context.user_data.get("last_actor_phone"),
            "language": language,
        }
        await aboutadmin.buffer_admin_action(context, actor, "requested_highlights", getattr(user, "username", None))
        await aboutadmin._immediate_admin_alert(context, actor, "requested_highlights", getattr(user, "username", None))
        await query.message.reply_text(t["fetching_highlights"])
        highlights = await insta.get_user_highlights(user.pk)
        if not highlights:
            await query.message.reply_text(t["no_highlights"], reply_markup=profile_actions_keyboard(language=language))
            return
        for h in highlights:
            title = getattr(h, "title", None) or str(getattr(h, "pk", "Highlight"))
            try:
                pk = int(getattr(h, "pk", h))
            except Exception:
                pk = getattr(h, "pk", None)
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"⭐ {title}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t["button_open"], callback_data=f"highlight:{pk}")]])
            )
        await query.message.reply_text(t["select_highlight"], reply_markup=profile_actions_keyboard(language=language))
        return

    if data.startswith("highlight:"):
        raw = data.split(":", 1)[1]
        try:
            hk = int(raw)
        except Exception:
            await query.message.reply_text(t["invalid_highlight"], reply_markup=profile_actions_keyboard(language=language))
            return
        actor = {
            "id": context.user_data.get("last_actor_id"),
            "username": context.user_data.get("last_actor_username"),
            "name": context.user_data.get("last_actor_name"),
            "phone": context.user_data.get("last_actor_phone"),
            "language": language,
        }
        await aboutadmin.buffer_admin_action(context, actor, "opened_highlight", getattr(user, "username", None), f"highlight_pk={hk}")
        await aboutadmin._immediate_admin_alert(context, actor, "opened_highlight", getattr(user, "username", None), f"highlight_pk={hk}")
        await query.message.reply_text(t["fetching_highlight"])
        hinfo = await insta.get_highlight_info(hk)
        if not hinfo:
            await query.message.reply_text(t["no_highlight_info"], reply_markup=profile_actions_keyboard(language=language))
            return
        items = getattr(hinfo, "items", None) or model_to_dict(hinfo).get("items", [])
        if not items:
            await query.message.reply_text(t["no_highlight_items"], reply_markup=profile_actions_keyboard(language=language))
            return
        for it in items:
            si_list = extract_media_items(it)
            for si in si_list:
                url = si.get("url")
                if not url:
                    continue
                try:
                    url = str(url)
                except Exception:
                    pass
                cap = (si.get("caption") or "")[:1024]
                try:
                    if si.get("kind") == "video":
                        await context.bot.send_video(chat_id=query.message.chat.id, video=url, caption=(cap or None))
                    else:
                        await context.bot.send_photo(chat_id=query.message.chat.id, photo=url, caption=(cap or None))
                except Exception:
                    logger.exception("Failed to send highlight media")
        await query.message.reply_text(t["highlights_shown"], reply_markup=profile_actions_keyboard(language=language))
        return

    if data == "view_tracking":
        # Placeholder for tracking feature
        await query.message.reply_text(t["tracking_message"], reply_markup=profile_actions_keyboard(language=language))
        return

    if data == "close_profile":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(t["profile_closed"], reply_markup=get_main_menu(language))
        return

    if data == "profile_menu":
        try:
            await query.message.reply_text(t["profile_menu"], reply_markup=profile_actions_keyboard(language=language))
        except Exception:
            pass
        return

    if data == "noop":
        return

    await query.message.reply_text(t["unknown_action"], reply_markup=profile_actions_keyboard(language=language))
    return

# ---------------- admin debug: dump raw media shape ----------------
async def dump_media_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = context.user_data.get("language", "en")
    t = TRANSLATIONS[language]
    admin_chat_id = context.application.bot_data.get('admin_chat_id')
    chat_id = update.effective_chat.id
    if not admin_chat_id or str(chat_id) != str(admin_chat_id):
        await update.message.reply_text(t["not_authorized"])
        return
    args = context.args or []
    idx = 0
    if args:
        try:
            idx = int(args[0])
        except Exception:
            await update.message.reply_text(t["dump_media_usage"])
            return
    raw_list = context.user_data.get("last_medias_raw")
    if not raw_list:
        await update.message.reply_text(t["no_media_cached"])
        return
    if idx < 0 or idx >= len(raw_list):
        await update.message.reply_text(t["index_out_of_range"].format(len(raw_list)-1))
        return
    try:
        dumped = json.dumps(raw_list[idx], default=str, indent=2)[:3900]
        await update.message.reply_text(f"Media[{idx}] model_dump (truncated):\n```\n{dumped}\n```", parse_mode="Markdown")
    except Exception as e:
        logger.exception(t["dump_media_failed"])
        await update.message.reply_text(t["dump_media_failed"])

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        SELECTING_LANGUAGE: [
            CallbackQueryHandler(select_language, pattern="^lang:"),
        ],
        CHOOSING: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice),
            CallbackQueryHandler(handle_callback_query),
        ],
        REPORTING: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_report_message),
            CallbackQueryHandler(handle_callback_query),
        ],
    },
    fallbacks=[CommandHandler("start", start)],
    allow_reentry=True,
    per_message=True,  # Enable per-message tracking for callbacks
)

help_cmd_handler = CommandHandler("help", help_cmd)

dump_media_cmd_handler = CommandHandler("dump_media", dump_media_cmd)
