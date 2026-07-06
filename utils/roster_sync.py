"""
Утилита для синхронизации и обновления текстовых списков в топиках групп.
"""

import logging
from aiogram import Bot
from aiogram.types import LinkPreviewOptions
import database as db
from utils.list_format import format_clan_roster
from config import ROSTER_TOPICS

logger = logging.getLogger(__name__)


async def sync_roster_msg(bot: Bot, clan_key: str) -> None:
    """
    Генерирует актуальный список клана.
    Принудительно УДАЛЯЕТ старое сообщение со списком и отправляет новое бесшумно.
    """
    topic_info = ROSTER_TOPICS.get(clan_key)
    if not topic_info or not topic_info["chat_id"] or not topic_info["thread_id"]:
        return

    # 1. Получаем отсортированных участников из БД
    members = await db.get_clan_members(clan_key)

    # 2. Форматируем список в HTML
    text = format_clan_roster(clan_key, members)

    # 3. Получаем ID старого сообщения
    old_msg_id = await db.get_roster_message_id(clan_key)

    # 4. Принудительно удаляем старый топ, если он существовал
    if old_msg_id:
        try:
            await bot.delete_message(
                chat_id=topic_info["chat_id"],
                message_id=int(old_msg_id) # Застраховали от сбоев типов данных SQLite
            )
        except Exception:
            pass

    # 5. Отправляем новое сообщение со свежим топом СТРОГО БЕЗ ЗВУКА И УВЕДОМЛЕНИЙ
    try:
        new_msg = await bot.send_message(
            chat_id=topic_info["chat_id"],
            message_thread_id=topic_info["thread_id"],
            text=text,
            parse_mode="HTML",
            disable_notification=True, # ИСПРАВЛЕНО: Бесшумная отправка ростера игрокам
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

        # 6. Закрепляем новое сообщение БЕЗ ЗВУКА (Убирает системную плашку закрепа)
        try:
            await bot.pin_chat_message(
                chat_id=topic_info["chat_id"],
                message_id=new_msg.message_id,
                disable_notification=True # ИСПРАВЛЕНО: Бесшумный закреп
            )
        except Exception:
            pass

        # 7. Сохраняем ID нового сообщения в базу данных
        await db.save_roster_message_id(clan_key, new_msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки списка в чат {clan_key}: {e}")


async def sync_all_rosters(bot: Bot) -> None:
    """
    Вызывается при старте бота.
    Синхронизирует списки для всех кланов, описанных в конфигурации.
    """
    from config import CLAN_CHATS
    for clan_key in CLAN_CHATS.keys():
        await sync_roster_msg(bot, clan_key)
