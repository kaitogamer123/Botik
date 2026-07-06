import logging
from aiogram import Router, F, Bot
from aiogram.types import ChatMemberUpdated, Message

from config import CLAN_CHATS, CLAN_DISPLAY
from database import get_member, upsert_member, remove_member, add_push_pending
from utils.roster_sync import sync_roster_msg

logger = logging.getLogger(__name__)
router = Router()


def detect_clan_by_chat(chat_id: int):
    for clan, data in CLAN_CHATS.items():
        if data["chat_id"] == chat_id:
            return clan
    return None


def build_user_link(user_data: dict) -> str:
    """ Генерирует кликабельную ссылку на игрока. Защищено от смены юзернейма. """
    uid = user_data.get("user_id")
    uname = user_data.get("username")
    nick = user_data.get("game_nick") or uname or "Игрок"

    # Если ID известен, делаем вечную скрытую ссылку по ID
    if uid and int(uid) > 0:
        return f'<a href="tg://user?id={uid}">{nick}</a>'

    # Если ID еще нет, но есть тег, упоминаем по тегу
    if uname:
        return f"@{uname}"

    return nick


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, bot: Bot):
    chat_id = event.chat.id
    clan = detect_clan_by_chat(chat_id)

    if not clan:
        return

    user = event.new_chat_member.user
    user_id = user.id

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # ─── ВХОД В КЛАН ─────────────────────────────
    if new_status in ("member", "administrator") and old_status in ("left", "kicked", "left_chat_member"):

        member = await get_member(user_id)

        if not member:
            await upsert_member(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                clan=clan,
                registered=0,
            )
        else:
            await upsert_member(
                user_id=user_id,
                clan=clan,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )

        # ─── сообщение в чат клана ───────────────
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"👋 Добро пожаловать в <b>{CLAN_DISPLAY.get(clan, clan)}</b>, {build_user_link(user)}!\n"
                     f"Пройди регистрацию в боте, чтобы попасть в список участников.",  # ИСПРАВЛЕНО: "in" на "в"
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"welcome msg failed: {e}")

        # ─── ЛС пользователю ─────────────────────
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"👋 Ты вступил в клан <b>{CLAN_DISPLAY.get(clan, clan)}</b>.\n\n"
                     f"Обязательно пройди регистрацию в боте через /start.",
                parse_mode="HTML"
            )
        except Exception:
            pass  # у пользователя может быть закрыт ЛС

        # ─── если не зарегистрирован → очередь пуша ─────
        if not member or member.get("registered") != 1:  # ИСПРАВЛЕНО: более строгая проверка флага
            await add_push_pending(user_id)

        await sync_roster_msg(bot, clan)

    # ─── ВЫХОД ИЗ КЛАНА ─────────────────────────
    elif new_status in ("left", "kicked"):

        member = await get_member(user_id)
        if member:
            await remove_member(user_id)

        await sync_roster_msg(bot, clan)


# ─── ПЕРЕХВАТ СООБЩЕНИЙ ДЛЯ СБОРА СТАРЫХ УЧАСТНИКОВ ───────────────────────────

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_message_collect_user(message: Message):
    """
    Ловит любое сообщение в клановых чатах.
    Если у автора сообщения ещё НЕТ игрового никнейма в базе данных,
    бот принудительно обновляет его клан и держит в списке 'Участники без ников'.
    """
    chat_id = message.chat.id
    clan = detect_clan_by_chat(chat_id)

    if not clan:
        return  # Если пишут в левом чате, игнорируем

    user_id = message.from_user.id

    # Игнорируем сообщения от других ботов и системные уведомления
    if message.from_user.is_bot:
        return

    member = await get_member(user_id)

    # ЖЕСТКОЕ ПРАВИЛО ПО ТЗ: Если игрок УЖЕ успешно зарегистрировался в ЛС (registered == 1),
    # мы ПОЛНОСТЬЮ игнорируем его сообщения во всех остальных чатах!
    if member and member.get("registered") == 1:
        return

    # Если игрока вообще нет в базе ИЛИ он есть, но ещё не ввёл игровой никнейм (game_nick)
    if not member or not member.get("game_nick"):
        await upsert_member(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            clan=clan,
            registered=0  # Оставляем статус незарегистрированного
        )
        # На всякий случай дублируем в очередь пуша
        await add_push_pending(user_id)
        logger.info(f"Игрок {user_id} актуализирован по сообщению в чате {clan} и удержан в списке без ников.")
