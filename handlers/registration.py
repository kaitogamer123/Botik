"""
Обработка процесса регистрации игрового никнейма и выбора клана.
"""

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext

import database as db
from handlers.start import RegistrationState
from utils.roster_sync import sync_roster_msg
from utils.keyboards import main_menu

router = Router()


# ─── Изменение никнейма из главного меню ──────────────────────────────────────

@router.message(F.text == "✏️ Изменить текущий ник")
async def change_current_nick_cmd(message: types.Message, state: FSMContext):
    """Ловит нажатие кнопки изменения ника из главного меню."""
    user_id = message.from_user.id
    member = await db.get_member(user_id)

    # Проверяем, зарегистрирован ли вообще человек
    if not member or member.get("registered") != 1:
        await message.answer("❌ Вы еще не зарегистрированы в боте. Напишите /start")
        return

    await message.answer(
        f"Ваш текущий ник в списке: <b>{member.get('game_nick', 'Не указан')}</b>\n\n"
        f"Введите ваш новый точный игровой никнейм:",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove() # Прячем старые кнопки на время ввода
    )
    # Сохраняем в память клан, чтобы после ввода ника обновить правильный топик
    await state.update_data(clan=member.get("clan"))
    await state.set_state(RegistrationState.entering_nick)


# ─── Регистрация/Выбор клана ──────────────────────────────────────────────────

# ИСПРАВЛЕНО: Префикс select_clan изменен на choose_clan в соответствии с файлом клавиатур
@router.callback_query(RegistrationState.choosing_clan, F.data.startswith("choose_clan:"))
async def process_clan_choice(callback: types.CallbackQuery, state: FSMContext):
    clan = callback.data.split(":")[1]
    data = await state.get_data()

    user_id = callback.from_user.id
    await db.upsert_member(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        clan=clan,
        role=data.get("role", "member"),
        registered=0
    )

    await callback.message.edit_text("Клан выбран успешно! Теперь введите ваш точный игровой никнейм:")
    await state.update_data(clan=clan)
    await state.set_state(RegistrationState.entering_nick)
    await callback.answer()


# ─── Ввод никнейма (для первичного старта и для изменения) ────────────────────
@router.message(RegistrationState.entering_nick)
async def process_nick_input(message: types.Message, state: FSMContext, bot: Bot):
    game_nick = message.text.strip()

    if len(game_nick) < 2 or len(game_nick) > 30:
        err_msg = "❌ Ник слишком короткий или длинный. Введите корректный игровой ник:"
        await message.answer(err_msg)

        # ДОБАВЛЕНО: Логируем ошибку бота
        from utils.admin_logger import log_user_chat
        await log_user_chat(bot=bot, user_id=message.from_user.id, username=message.from_user.username,
                            first_name=message.from_user.first_name, message_text=err_msg, is_bot_reply=True)
        return

    data = await state.get_data()
    clan = data.get("clan")
    user_id = message.from_user.id

    # ИСПРАВЛЕНО: Теперь передаем username, чтобы база данных железно сделала МЁРДЖ
    # и удалила игрока из списка участников без ников!
    await db.upsert_member(
        user_id=user_id,
        username=message.from_user.username, # <-- ДОБАВЬ ЭТУ СТРОЧКУ
        game_nick=game_nick,
        clan=clan,
        registered=1
    )

    # Получаем актуальные данные игрока из базы данных для генерации Reply-меню кнопок
    member = await db.get_member(user_id)

    # ИСПРАВЛЕНО: Объявляем переменную reply_msg, чтобы логгер не выдавал NameError!
    reply_msg = f"🎉 Никнейм успешно сохранен: <b>{game_nick}</b>"

    await message.answer(
        text=reply_msg,
        parse_mode="HTML",
        reply_markup=main_menu(member)  # Возвращаем игроку его клавиатуру управления
    )

    # ЛОГИРУЕМ ОТВЕТ БОТА ИГРОКУ
    from utils.admin_logger import log_user_chat
    await log_user_chat(
        bot=bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        message_text=reply_msg,
        is_bot_reply=True
    )

    await state.clear()

    # Триггерим автоматическое обновление списков в топиках
    if clan:
        await sync_roster_msg(bot, clan)
