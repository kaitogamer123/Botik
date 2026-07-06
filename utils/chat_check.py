"""
Утилиты для проверки членства пользователя в чатах кланов и администрации.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from config import CLAN_CHATS, ADMIN_CHAT_ID, INITIAL_ADMINS


async def get_user_clans(bot: Bot, user_id: int) -> list[str]:
    """
    Проверяет, в каких клановых чатах состоит пользователь.
    Возвращает список ключей кланов (например: ['squad', 'academy']).
    """
    # Сначала проверяем жестко заданных в конфиге создателей
    if user_id in INITIAL_ADMINS:
        allocated_clan = INITIAL_ADMINS[user_id].get("clan")
        # ИСПРАВЛЕНО: Если у лидера в конфиге уже прописан его клан, сразу возвращаем его без лишних выборов меню
        if allocated_clan and allocated_clan in CLAN_CHATS:
            return [allocated_clan]
        return list(CLAN_CHATS.keys())

    user_clans = []

    for clan_key, chat_info in CLAN_CHATS.items():
        try:
            member = await bot.get_chat_member(chat_id=chat_info["chat_id"], user_id=user_id)
            # ИСПРАВЛЕНО: Заменен устаревший статус "creator" на актуальный "owner"
            if member.status in ["owner", "administrator", "member"]:
                user_clans.append(clan_key)
        except TelegramBadRequest:
            # Вызывается, если бот не админ в чате или чат недоступен
            continue
        except Exception:
            continue

    return user_clans


async def is_chat_admin(bot: Bot, user_id: int) -> bool:
    """
    Определяет администратора по принципу его нахождения в ADMIN_CHAT_ID.
    """
    if user_id in INITIAL_ADMINS:
        return True

    if not ADMIN_CHAT_ID:
        return False

    try:
        member = await bot.get_chat_member(chat_id=ADMIN_CHAT_ID, user_id=user_id)
        # ИСПРАВЛЕНО: Убран статус "member", чтобы обычные участники админ-чата не получали права модераторов!
        # Также заменен "creator" на "owner"
        return member.status in ["owner", "administrator"]
    except Exception:
        return False
