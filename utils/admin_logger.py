import logging
from datetime import datetime
from aiogram import Bot
import config
from database import get_setting, set_setting

# Настраиваем локальный файловый логгер
logger = logging.getLogger("admin_actions")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler("admin_actions.log", encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


async def get_or_create_admin_topic(bot: Bot, chat_id: int, admin_id: int, admin_name: str) -> int:
    """
    Проверяет, есть ли у админа персональный топик.
    Если нет — автоматически создает его на лету и сохраняет в БД.
    """
    setting_key = f"admin_topic_{admin_id}"
    thread_id_str = await get_setting(setting_key)

    if thread_id_str:
        return int(thread_id_str)

    # Если топика нет, создаем его на лету
    topic_title = f"📁 Логи @{admin_name}" if admin_name else f"📁 Логи ID {admin_id}"
    try:
        topic = await bot.create_forum_topic(
            chat_id=chat_id,
            name=topic_title,
            icon_color=0x9B59B6  # Фиолетовый цвет для личных логов
        )

        # Запоминаем в базу данных, чтобы не плодить дубликаты
        await set_setting(setting_key, str(topic.message_thread_id))

        # Отправляем приветственное сообщение в новый топик админа
        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=topic.message_thread_id,
            text=f"📌 Топик инициализирован. Сюда будут дублироваться абсолютно все действия администратора: <b>@{admin_name}</b> (ID: <code>{admin_id}</code>).",
            parse_mode="HTML"
        )
        return topic.message_thread_id
    except Exception as e:
        logging.error(f"Не удалось создать персональный топик для админа {admin_id}: {e}")
        return 0


async def log_admin_action(bot: Bot, admin_id: int, admin_name: str, action_text: str, clan_key: str = "main_admin"):
    """
    Логирует действия: пишет в файл, отправляет в топик категории И в персональный топик админа.
    """
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{clan_key.upper()}] Админ ID {admin_id} (@{admin_name}): {action_text}"

    # 1. Запись в файл на сервере
    logger.info(log_msg)

    # 2. Проверяем базовый чат логов
    chat_id = config.LOGS_CHAT_ID or config.ADMIN_CHAT_ID
    if not chat_id:
        return

    html_text = (
        f"⚡ <b>ДЕЙСТВИЕ АДМИНИСТРАЦИИ</b>\n"
        f"📅 <b>Время:</b> <code>{time_str}</code>\n"
        f"👤 <b>Админ:</b> @{admin_name} (ID: <code>{admin_id}</code>)\n"
        f"📝 <b>Что сделано:</b> {action_text}"
    )

    # ────── ОТПРАВКА В ТОПИК КАТЕГОРИИ (КЛАНА) ──────
    setting_key = f"topic_id_{clan_key}"
    thread_id_str = await get_setting(setting_key)

    if not thread_id_str and clan_key != "main_admin":
        thread_id_str = await get_setting("topic_id_main_admin")

    if thread_id_str:
        try:
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=int(thread_id_str),
                text=html_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить лог в топик категории {clan_key}: {e}")

    # ────── ОТПРАВКА В ПЕРСОНАЛЬНЫЙ ТОПИК АДМИНА ──────
    # Бот проверит или автоматически создаст тему на лету
    admin_thread_id = await get_or_create_admin_topic(bot, chat_id, admin_id, admin_name)

    if admin_thread_id and admin_thread_id != int(thread_id_str or 0):
        try:
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=admin_thread_id,
                text=html_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить лог в персональный топик админа {admin_id}: {e}")


async def get_or_create_chat_log_topic(bot: Bot, chat_id: int) -> int:
    """
    Проверяет наличие топика для трансляции ЛС игроков.
    Если его нет — создаёт его автоматически.
    """
    setting_key = "topic_id_users_chat"
    thread_id_str = await get_setting(setting_key)

    if thread_id_str:
        return int(thread_id_str)

    try:
        topic = await bot.create_forum_topic(
            chat_id=chat_id,
            name="💬 Личные сообщения игроков",
            icon_color=0x2ECC71  # Зеленый цвет для чат-логов
        )
        await set_setting(setting_key, str(topic.message_thread_id))

        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=topic.message_thread_id,
            text="📌 В этот топик в реальном времени транслируются все диалоги обычных игроков с ботом в ЛС.",
            parse_mode="HTML"
        )
        return topic.message_thread_id
    except Exception as e:
        logging.error(f"Не удалось создать топик для логов ЛС игроков: {e}")
        return 0


async def log_user_chat(bot: Bot, user_id: int, username: str, first_name: str, message_text: str,
                        is_bot_reply: bool = False):
    """
    Транслирует сообщения пользователей и ответы бота в специальный топик.
    """
    # Записываем в стандартный текстовый файл на сервере (для истории)
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction = "БОТ -> ЮЗЕР" if is_bot_reply else "ЮЗЕР -> БОТ"
    logger.info(f"[{direction}] ID {user_id} (@{username}): {message_text}")

    chat_id = config.LOGS_CHAT_ID or config.ADMIN_CHAT_ID
    if not chat_id:
        return

    thread_id = await get_or_create_chat_log_topic(bot, chat_id)
    if not thread_id:
        return

    display_name = f"@{username}" if username else f"{first_name} (ID: {user_id})"

    if is_bot_reply:
        html_text = (
            f"🤖 <b>Ответ бота для</b> {display_name}:\n"
            f" └ <i>{message_text}</i>"
        )
    else:
        html_text = (
            f"👤 <b>Игрок</b> {display_name} <b>написал боту:</b>\n"
            f" └ <code>{message_text}</code>"
        )

    try:
        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=html_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка трансляции ЛС в топик: {e}")
