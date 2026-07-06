import logging
from aiogram import Bot
from database import get_all_members, upsert_member
from config import INITIAL_ADMINS

logger = logging.getLogger(__name__)


async def check_and_update_usernames(bot: Bot):
    """Фоновая задача: проверяет смену юзернеймов у игроков с известным ID."""
    logger.info("Запуск плановой проверки юзернеймов...")
    all_members = await get_all_members()

    # Собираем ID президентов для уведомлений
    presidents = [uid for uid, info in INITIAL_ADMINS.items() if info["role"] == "president"]

    for m in all_members:
        uid = m.get("user_id")
        old_username = m.get("username")

        # Проверяем только тех, у кого реальный ID уже есть в базе
        if not uid or int(uid) <= 0:
            continue

        try:
            # Запрашиваем актуальный профиль из Telegram API
            chat = await bot.get_chat(chat_id=uid)
            new_username = chat.username

            # Если юзернейм изменился (или удалился/появился)
            if old_username != new_username:
                # Обновляем в нашей БД
                await upsert_member(user_id=uid, username=new_username)

                # Формируем текст сообщения для лидеров
                old_display = f"@{old_username}" if old_username else "отсутствовал"
                new_display = f"@{new_username}" if new_username else "удален ❌"
                game_nick = m.get("game_nick") or "Без ника"

                msg_text = (
                    "🔔 <b>Уведомление о смене юзернейма!</b>\n\n"
                    f"Игрок: <b>{game_nick}</b> (ID: <code>{uid}</code>)\n"
                    f"Старый тег: {old_display}\n"
                    f"Новый тег: <b>{new_display}</b>"
                )

                # Рассылаем всем президентам
                for pres_id in set(presidents):
                    try:
                        await bot.send_message(chat_id=pres_id, text=msg_text, parse_mode="HTML")
                    except Exception:
                        pass

                logger.info(f"Юзернейм игрока {uid} изменен: {old_username} -> {new_username}")
        except Exception as e:
            # Игрок мог заблокировать бота, это нормально, пропускаем
            logger.debug(f"Не удалось проверить юзернейм для ID {uid}: {e}")
