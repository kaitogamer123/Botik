"""
Push Goal Service (ядро системы выбора цели сезона)
"""
import logging
from datetime import datetime, timedelta
import aiosqlite

# Логгер для этого модуля
logger = logging.getLogger(__name__)

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from config import (
    CLAN_CHATS,
    ADMIN_NEWS_TARGETS,
    PUSH_CHANGE_DEADLINE_DAYS,
    CLAN_DISPLAY
)
from utils.formatting import PUSH_GOAL_TEXT
from utils.keyboards import push_goal_keyboard
# ИСПРАВЛЕНО: Импортируем функцию проверки 48 часов из нашего модуля лимитера
from utils.push_limiter import is_locked

# ─────────────────────────────────────────────────────────────
# 1. РАССЫЛКА ГОЛОСОВАНИЯ
# ─────────────────────────────────────────────────────────────
async def launch_push_vote(bot: Bot) -> None:
    """
    Массовая рассылка опроса по целям сезона.
    Перед запуском полностью сбрасывает старые результаты!
    ИСПРАВЛЕНО: Рассылает опрос СТРОГО участникам основного состава (squad).
    """
    from database import clear_old_push_data
    await clear_old_push_data()
    logger.info("Старые цели пуша успешно сброшены.")

    all_members = await db.get_all_members()

    for member in all_members:
        user_id = member["user_id"]

        # ЖЕСТКИЙ ФИЛЬТР: Если человек не из основы — бот его вообще не трогает при пуше!
        if member.get("clan") != "squad":
            continue

        # Если не зарегистрирован (нет игрового ника) — заносим в очередь ожидания
        if member.get("registered") != 1:
            await db.add_push_pending(user_id)
            continue

        # Зарегистрированным игрокам основы шлем опрос в ЛС
        try:
            await bot.send_message(
                chat_id=user_id,
                text=PUSH_GOAL_TEXT,
                parse_mode="HTML",
                reply_markup=push_goal_keyboard()
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить пуш-опрос пользователю {user_id}: {e}")


# ─────────────────────────────────────────────────────────────
# 2. СОХРАНЕНИЕ ВЫБОРА
# ─────────────────────────────────────────────────────────────

async def save_push_goal(user_id: int, goal: str) -> bool:
    """
    Сохраняет цель пользователя.
    Возвращает True если сохранено, False если заблокировано.
    """
    # ИСПРАВЛЕНО: Вызываем функцию получения цели через модуль db.
    existing = await db.get_push_goal(user_id)

    if existing and is_locked(existing["chosen_at"]):
        return False

    # ИСПРАВЛЕНО: Вызываем функцию сохранения через модуль db.
    await db.set_push_goal(user_id, goal)
    return True


# ─────────────────────────────────────────────────────────────
# 3. ПОЛУЧЕНИЕ НЕОПРЕДЕЛИВШИХСЯ (Исправлено: ТОЛЬКО ДЛЯ ОСНОВЫ)
# ─────────────────────────────────────────────────────────────

async def get_undecided_members() -> list[dict]:
    """
    Возвращает всех зарегистрированных пользователей БЕЗ выбора цели.
    ИСПРАВЛЕНО: Фильтрует участников и оставляет строго основной состав (squad).
    """
    members = await db.get_all_members()
    result = []

    for m in members:
        # Проверяем, что человек полностью зарегистрирован
        if not m.get("registered"):
            continue

        # ЖЕСТКИЙ ФИЛЬТР: Если человек из академки или ивентов — полностью игнорируем его в пуше
        if m.get("clan") != "squad":
            continue

        # Проверяем, выбрал ли он цель на сезон
        goal = await db.get_push_goal(m["user_id"])
        if not goal:
            result.append(m)

    return result


# ─────────────────────────────────────────────────────────────
# 4. РАССЫЛКА НАПОМИНАНИЙ
# ─────────────────────────────────────────────────────────────

async def notify_undecided_users(bot: Bot) -> None:
    """
    Личное уведомление всем, кто не выбрал цель.
    """
    undecided = await get_undecided_members()

    for u in undecided:
        try:
            await bot.send_message(
                u["user_id"],
                "⏰ Напоминание: выбери цель сезона в боте!",
            )
        except Exception as e:
            logger.warning(f"Failed reminder to {u['user_id']}: {e}")
# ─────────────────────────────────────────────────────────────
# 5. РАССЫЛКА В НОВОСТИ КЛАНОВ (Исправлено под ТЗ)
# ─────────────────────────────────────────────────────────────

async def notify_clan_news(bot: Bot) -> None:
    """
    Отправляет уведомление в news-топики кланов.
    Группирует участников строго по их кланам, чтобы не пинговать лишних.
    """
    undecided = await get_undecided_members()
    if not undecided:
        return

    # Группируем «молчунов» по ключам кланов
    clan_groups = {"academy": [], "squad": [], "events": []}
    for u in undecided:
        clan = u.get("clan")
        if clan in clan_groups:
            clan_groups[clan].append(u)

    # Рассылаем уведомления в топики новостей каждого клана
    for clan_key, data in ADMIN_NEWS_TARGETS.items():
        clan_members = clan_groups.get(clan_key, [])
        if not clan_members:
            continue  # Если в этом клане все определились, ничего не шлем

        # Собираем теги для текущего клана
        mentions = []
        for m in clan_members:
            if m.get("username"):
                mentions.append(f"@{m['username']}")
            else:
                # Если юзернейма нет, делаем кликабельное текстовое упоминание
                name = m.get("game_nick") or "Игрок"
                mentions.append(f"<a href='tg://user?id={m['user_id']}'>{name}</a>")

        # Форматируем текст строго по ТЗ
        text_lines = []
        for mention in mentions:
            text_lines.append(mention)

        text_lines.append(
            "\nОпределитесь с тем что вы будете пушить в этом сезоне. "
            "Сделайте это в течении двух дней. Это можно сделать в лс с ботом"
        )

        text = "\n".join(text_lines)

        try:
            await bot.send_message(
                chat_id=data["chat_id"],
                message_thread_id=data["thread_id"],
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"News notify failed for {clan_key}: {e}")


# ─────────────────────────────────────────────────────────────
# 6. УТИЛИТЫ (для handlers)
# ─────────────────────────────────────────────────────────────

async def user_can_change_goal(user_id: int) -> bool:
    """
    Проверка: может ли пользователь менять выбор.
    """
    # ИСПРАВЛЕНО: Добавлен префикс db. к вызову get_push_goal
    goal = await db.get_push_goal(user_id)

    if not goal:
        return True

    return not is_locked(goal["chosen_at"])
