import logging
import os
from enum import Enum

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaVideo,
    Update,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class AccessState(Enum):
    NO_ACCESS = "no_access"
    HAS_ACCESS = "has_access"


class MaterialState(Enum):
    LOCKED = "locked"
    OPENED = "opened"
    EXPIRED = "expired"


CB_ENTER = "enter_group"
CB_LEAVE = "leave_group"
CB_OPEN = "open_material"
CB_WATCH = "watch_lesson"
CB_HIDE = "hide_lesson"
CB_RENEW = "renew_access"
CB_UPLOAD = "upload_help"


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()

PLACEHOLDER_VIDEO_ID = os.getenv("PLACEHOLDER_VIDEO_ID", "").strip()
LESSON_VIDEO_ID = os.getenv("LESSON_VIDEO_ID", "").strip()
MAX_LESSON_TTL_SECONDS = 47 * 60 * 60 + 59 * 60  # 172740 seconds


def get_lesson_ttl_seconds() -> int:
    raw_value = os.getenv("LESSON_TTL_SECONDS", "30").strip()

    try:
        ttl = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("LESSON_TTL_SECONDS must be an integer") from exc

    if ttl <= 0:
        raise RuntimeError("LESSON_TTL_SECONDS must be greater than 0")

    if ttl > MAX_LESSON_TTL_SECONDS:
        raise RuntimeError(
            f"LESSON_TTL_SECONDS must not exceed {MAX_LESSON_TTL_SECONDS} seconds "
            "(47 hours and 59 minutes)"
        )

    return ttl


LESSON_TTL_SECONDS = get_lesson_ttl_seconds()


# Demo storage without DB.
access_users: set[int] = set()
latest_material_message: dict[tuple[int, int], int] = {}
material_states: dict[tuple[int, int], MaterialState] = {}


def get_admin_user_id() -> int | None:
    if not ADMIN_USER_ID:
        return None

    try:
        return int(ADMIN_USER_ID)
    except ValueError:
        logger.warning("ADMIN_USER_ID is not a valid integer")
        return None


def is_admin(user_id: int) -> bool:
    admin_id = get_admin_user_id()
    return admin_id is not None and user_id == admin_id


def media_is_configured() -> bool:
    return bool(PLACEHOLDER_VIDEO_ID and LESSON_VIDEO_ID)


def get_access_state(user_id: int) -> AccessState:
    return AccessState.HAS_ACCESS if user_id in access_users else AccessState.NO_ACCESS


def access_label(user_id: int) -> str:
    if get_access_state(user_id) == AccessState.HAS_ACCESS:
        return "✅ Доступ активен"
    return "⛔️ Доступ не активен"


def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Войти в группу", callback_data=CB_ENTER),
            InlineKeyboardButton("🚪 Выйти из группы", callback_data=CB_LEAVE),
        ],
        [InlineKeyboardButton("🎬 Открыть материал", callback_data=CB_OPEN)],
    ]

    if is_admin(user_id):
        rows.append([InlineKeyboardButton("🆔 Загрузить видео / получить file_id", callback_data=CB_UPLOAD)])

    return InlineKeyboardMarkup(rows)


def locked_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Посмотреть урок", callback_data=CB_WATCH)],
            [InlineKeyboardButton("💳 Продлить доступ", callback_data=CB_RENEW)],
        ]
    )


def opened_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🙈 Скрыть урок", callback_data=CB_HIDE)],
            [InlineKeyboardButton("🚪 Выйти из группы", callback_data=CB_LEAVE)],
        ]
    )


def expired_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Посмотреть урок ещё раз", callback_data=CB_WATCH)],
            [InlineKeyboardButton("💳 Продлить доступ", callback_data=CB_RENEW)],
        ]
    )


def renew_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Войти в группу для демо", callback_data=CB_ENTER)],
            [InlineKeyboardButton("▶️ Попробовать снова", callback_data=CB_WATCH)],
        ]
    )


def locked_caption(user_id: int) -> str:
    return (
        "🔒 Урок закрыт.\n\n"
        "Это управляемый контейнер материала: сейчас внутри него видео-заглушка.\n\n"
        f"Ваш статус: {access_label(user_id)}"
    )


def opened_caption() -> str:
    return (
        "✅ Урок открыт.\n\n"
        f"Через {LESSON_TTL_SECONDS} секунд бот автоматически вернёт сюда заглушку."
    )


def expired_caption(user_id: int) -> str:
    return (
        "⏳ Сессия просмотра завершена.\n\n"
        "Бот вернул материал в состояние заглушки без удаления сообщения.\n\n"
        f"Ваш статус: {access_label(user_id)}"
    )


def no_access_caption() -> str:
    return (
        "⛔️ Доступ не активен.\n\n"
        "В реальном проекте здесь была бы проверка оплаты, тарифа или участия в группе.\n"
        "В демо можно нажать «Войти в группу для демо»."
    )


def job_name(chat_id: int, message_id: int) -> str:
    return f"expire_lesson:{chat_id}:{message_id}"


def remove_existing_expire_job(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> bool:
    current_jobs = context.job_queue.get_jobs_by_name(job_name(chat_id, message_id))
    if not current_jobs:
        return False

    for job in current_jobs:
        job.schedule_removal()

    return True


async def safe_edit_media(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    video_id: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    try:
        await context.bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=InputMediaVideo(media=video_id, caption=caption),
            reply_markup=reply_markup,
        )
    except BadRequest as exc:
        message = str(exc).lower()

        if "message is not modified" in message:
            logger.info("Message %s:%s already has requested media", chat_id, message_id)
            return

        logger.warning("BadRequest while editing media: %s", exc)
        raise
    except TelegramError as exc:
        logger.exception("Telegram error while editing media: %s", exc)
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    text = (
        "Привет! Это демо-бот ограниченного доступа к Telegram-контенту.\n\n"
        "Механика:\n"
        "1. Материал сначала показывается как видео-заглушка.\n"
        "2. Пользователь нажимает «Посмотреть урок».\n"
        "3. Бот проверяет доступ.\n"
        "4. Если доступ есть — заменяет заглушку на урок.\n"
        "5. По таймеру возвращает заглушку обратно.\n\n"
        f"Ваш статус: {access_label(user_id)}"
    )

    if not media_is_configured():
        text += (
            "\n\n⚙️ Видео пока не настроены. "
            "Админу нужно загрузить видео и добавить file_id в переменные окружения."
        )

    await update.effective_message.reply_text(text, reply_markup=main_keyboard(user_id))


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    await update.effective_message.reply_text(
        "Ваши идентификаторы:\n\n"
        f"user_id: `{user.id}`\n"
        f"chat_id: `{chat.id}`\n\n"
        "Для защиты админ-команд добавьте в Dockhost переменную:\n"
        f"`ADMIN_USER_ID={user.id}`",
        parse_mode="Markdown",
    )


async def upload_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.effective_message.reply_text("⛔️ Эта команда доступна только админу.")
        return

    await update.effective_message.reply_text(
        "🆔 Загрузка видео для демо\n\n"
        "1. Отправь мне видео-заглушку.\n"
        "2. Я верну `file_id`.\n"
        "3. Вставь его в Dockhost как `PLACEHOLDER_VIDEO_ID`.\n\n"
        "Потом отправь видео-урок и вставь его как `LESSON_VIDEO_ID`.\n\n"
        "После изменения переменных окружения перезапусти контейнер.",
        parse_mode="Markdown",
    )


async def receive_admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.effective_message.reply_text("⛔️ Видео получил, но file_id показываю только админу.")
        return

    message = update.effective_message

    if not message.video:
        return

    file_id = message.video.file_id

    await message.reply_text(
        "Видео получено ✅\n\n"
        "Скопируй нужную строку в переменные окружения Dockhost:\n\n"
        f"`PLACEHOLDER_VIDEO_ID={file_id}`\n\n"
        "или\n\n"
        f"`LESSON_VIDEO_ID={file_id}`\n\n"
        "После добавления переменных перезапусти контейнер.",
        parse_mode="Markdown",
    )


async def open_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if not media_is_configured():
        await query.message.reply_text(
            "⚙️ Видео пока не настроены.\n\n"
            "Админу нужно:\n"
            "1. Выполнить `/whoami` и добавить `ADMIN_USER_ID`.\n"
            "2. Выполнить `/upload`.\n"
            "3. Отправить боту видео-заглушку и видео-урок.\n"
            "4. Добавить `PLACEHOLDER_VIDEO_ID` и `LESSON_VIDEO_ID` в Dockhost.\n"
            "5. Перезапустить контейнер.",
            parse_mode="Markdown",
        )
        return

    sent_message = await context.bot.send_video(
        chat_id=chat_id,
        video=PLACEHOLDER_VIDEO_ID,
        caption=locked_caption(user_id),
        reply_markup=locked_keyboard(),
        protect_content=True,
    )

    latest_material_message[(chat_id, user_id)] = sent_message.message_id
    material_states[(chat_id, sent_message.message_id)] = MaterialState.LOCKED


async def enter_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Демо-доступ включён ✅")

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    access_users.add(user_id)

    if not query.message.video:
        await query.message.reply_text(
            "✅ Вы вошли в группу доступа.\n\n"
            "Теперь можно открыть материал и нажать «Посмотреть урок».",
            reply_markup=main_keyboard(user_id),
        )
        return

    if media_is_configured():
        await safe_edit_media(
            context=context,
            chat_id=chat_id,
            message_id=query.message.message_id,
            video_id=PLACEHOLDER_VIDEO_ID,
            caption=locked_caption(user_id),
            reply_markup=locked_keyboard(),
        )


async def leave_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Демо-доступ отключён 🚪")

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    access_users.discard(user_id)

    if query.message.video and media_is_configured():
        remove_existing_expire_job(context, chat_id, query.message.message_id)

        await safe_edit_media(
            context=context,
            chat_id=chat_id,
            message_id=query.message.message_id,
            video_id=PLACEHOLDER_VIDEO_ID,
            caption=locked_caption(user_id),
            reply_markup=locked_keyboard(),
        )

        material_states[(chat_id, query.message.message_id)] = MaterialState.LOCKED
        return

    latest_message_id = latest_material_message.get((chat_id, user_id))
    if latest_message_id and media_is_configured():
        remove_existing_expire_job(context, chat_id, latest_message_id)

        await safe_edit_media(
            context=context,
            chat_id=chat_id,
            message_id=latest_message_id,
            video_id=PLACEHOLDER_VIDEO_ID,
            caption=locked_caption(user_id),
            reply_markup=locked_keyboard(),
        )

        material_states[(chat_id, latest_message_id)] = MaterialState.LOCKED

    await query.message.reply_text(
        "🚪 Вы вышли из группы доступа.\n\n"
        "Если урок был открыт, бот вернул его в заглушку.",
        reply_markup=main_keyboard(user_id),
    )


async def watch_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if not media_is_configured():
        await query.message.reply_text("Сначала нужно настроить file_id заглушки и урока.")
        return

    if get_access_state(user_id) == AccessState.NO_ACCESS:
        await safe_edit_media(
            context=context,
            chat_id=chat_id,
            message_id=message_id,
            video_id=PLACEHOLDER_VIDEO_ID,
            caption=no_access_caption(),
            reply_markup=renew_keyboard(),
        )
        material_states[(chat_id, message_id)] = MaterialState.EXPIRED
        return

    await safe_edit_media(
        context=context,
        chat_id=chat_id,
        message_id=message_id,
        video_id=LESSON_VIDEO_ID,
        caption=opened_caption(),
        reply_markup=opened_keyboard(),
    )

    material_states[(chat_id, message_id)] = MaterialState.OPENED

    remove_existing_expire_job(context, chat_id, message_id)
    context.job_queue.run_once(
        expire_lesson,
        when=LESSON_TTL_SECONDS,
        chat_id=chat_id,
        user_id=user_id,
        name=job_name(chat_id, message_id),
        data={
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
        },
    )


async def hide_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Урок скрыт")

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if not media_is_configured():
        return

    remove_existing_expire_job(context, chat_id, message_id)

    await safe_edit_media(
        context=context,
        chat_id=chat_id,
        message_id=message_id,
        video_id=PLACEHOLDER_VIDEO_ID,
        caption=locked_caption(user_id),
        reply_markup=locked_keyboard(),
    )

    material_states[(chat_id, message_id)] = MaterialState.LOCKED


async def renew_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("В демо продление заменено кнопкой входа в группу")

    user_id = query.from_user.id

    await query.message.reply_text(
        "💳 Здесь могла бы быть оплата или ссылка на продление доступа.\n\n"
        "В демо нажми «Войти в группу», чтобы имитировать активный доступ.",
        reply_markup=main_keyboard(user_id),
    )


async def expire_lesson(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job

    chat_id = job.data["chat_id"]
    message_id = job.data["message_id"]
    user_id = job.data["user_id"]

    if not media_is_configured():
        return

    await safe_edit_media(
        context=context,
        chat_id=chat_id,
        message_id=message_id,
        video_id=PLACEHOLDER_VIDEO_ID,
        caption=expired_caption(user_id),
        reply_markup=expired_keyboard(),
    )

    material_states[(chat_id, message_id)] = MaterialState.EXPIRED
    logger.info("Lesson expired and returned to placeholder: %s:%s", chat_id, message_id)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = update.callback_query.data

    if data == CB_ENTER:
        await enter_group(update, context)
    elif data == CB_LEAVE:
        await leave_group(update, context)
    elif data == CB_OPEN:
        await open_material(update, context)
    elif data == CB_WATCH:
        await watch_lesson(update, context)
    elif data == CB_HIDE:
        await hide_lesson(update, context)
    elif data == CB_RENEW:
        await renew_access(update, context)
    elif data == CB_UPLOAD:
        await update.callback_query.answer()
        await upload_help(update, context)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("whoami", whoami))
    application.add_handler(CommandHandler("upload", upload_help))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.VIDEO, receive_admin_video))

    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()