"""
Система списков кланов:
- генерация
- обновление
- ручной вызов админом через команду
"""

import logging

from aiogram import Router, Bot, F
from aiogram.types import Message, LinkPreviewOptions

from config import ROSTER_TOPICS
from database import (
    get_member,
    get_clan_members,
    get_roster_message_id,
    save_roster_message_id,
)
from utils.formatting import format_roster
from utils.permissions import can_edit_list

logger = logging.getLogger(__name__)
router = Router()


# ─── Обновление одного клана ──────────────────────────────────────────────────

async def update_clan_list(bot: Bot, clan: str):
    """
    Создаёт или обновляет сообщение списка клана в топике.
    """

    topic = ROSTER_TOPICS.get(clan)
    if not topic or not topic.get("thread_id"):
        logger.warning(f"Clan {clan} has no roster topic configured")
        return

    chat_id = topic["chat_id"]
    thread_id = topic["thread_id"]

    members = await get_clan_members(clan)
    text = format_roster(clan, members)

    msg_id = await get_roster_message_id(clan)

    # Заменяем устаревший disable_web_page_preview на актуальный LinkPreviewOptions для aiogram 3.x
    preview_options = LinkPreviewOptions(is_disabled=True)

    try:
        if msg_id:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                message_thread_id=thread_id,
                text=text,
                parse_mode="HTML",
                link_preview_options=preview_options,
            )
        else:
            raise Exception("no message id")

    except Exception:
        msg = await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=text,
            parse_mode="HTML",
            link_preview_options=preview_options,
        )
        await save_roster_message_id(clan, msg.message_id)


# ─── Обновление всех кланов ──────────────────────────────────────────────────

async def update_all_clans(bot: Bot):
    for clan in ROSTER_TOPICS.keys():
        await update_clan_list(bot, clan)


# ─── Ручной вызов админом ────────────────────────────────────────────────────

# ИСПРАВЛЕНО: Изменили текст на команду, чтобы не ломать кнопку инлайн-меню из админки
@router.message(F.text == "/refresh_roster")
async def manual_update(message: Message, bot: Bot):
    """
    Принудительный refresh списка клана через команду в чате.
    """

    # Безопасное получение данных админа напрямую из БД
    member = message.middleware_data.get("member") or await get_member(message.from_user.id)

    if not member or not can_edit_list(member):
        await message.answer("⛔ Нет прав.")
        return

    clan = member.get("clan")
    if not clan:
        await message.answer("❌ Клан не найден.")
        return

    await update_clan_list(bot, clan)
    await message.answer("✅ Список клана принудительно обновлён в топике.")
