"""
Обработчик команды /start и первичная авторизация по кланам.
"""

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

import database as db
from utils.chat_check import get_user_clans, is_chat_admin
from config import CLAN_DISPLAY, INITIAL_ADMINS
from utils.keyboards import main_menu, choose_clan_keyboard

router = Router()


class RegistrationState(StatesGroup):
    choosing_clan = State()
    entering_nick = State()


# Фильтр F.chat.type == "private" заставляет бота реагировать на /start ТОЛЬКО в личных сообщениях
# ИСПРАВЛЕНО: Добавлен аргумент bot: Bot для корректного вызова внешних утилит проверки чатов
@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username

    # 1. Проверяем, админ ли он чата администрации (ИСПРАВЛЕНО: заменен message.bot на bot)
    is_admin = await is_chat_admin(bot, user_id)

    # Определяем базовую роль
    current_role = "member"
    if user_id in INITIAL_ADMINS:
        current_role = INITIAL_ADMINS[user_id]["role"]
    elif is_admin:
        current_role = "vice"  # Дефолтная роль для админ-чата, если не лидер

    # 2. Проверяем, в каких кланах сидит человек (ИСПРАВЛЕНО: заменен message.bot на bot)
    clans = await get_user_clans(bot, user_id)

    if not clans:
        await message.answer(
            "❌ Доступ заблокирован. Вас нет ни в одном чате наших кланов.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # Проверяем, есть ли он уже в БД
    member = await db.get_member(user_id)

    if member and member.get("registered") == 1:
        await message.answer(
            f"Привет, {message.from_user.first_name}! Это главное меню бота ViGarik Squad.\n"
            f"Вы зарегистрированы в клане: {CLAN_DISPLAY.get(member['clan'])}",
            reply_markup=main_menu(member)
        )
        return

    # 3. Если он в нескольких кланах — просим выбрать
    # 3. Если он в нескольких кланах — просим выбрать
    if len(clans) > 1:
        # ДОБАВЛЕНО: Очищаем Reply-меню перед отправкой Инлайн-клавиатуры
        await message.answer(
            f"Привет, @{username or message.from_user.first_name}! Я нашёл тебя в чатах нескольких наших кланов.\n\n"
            f"⚠️ <b>Если у тебя есть твинк-аккаунт:</b> нажми на тот клан, где находится твоя <u>ОСНОВА</u>.\n"
            f"Твой второй аккаунт администрация добавит в список позже.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )

        # Подключенная ранее функция choose_clan_keyboard с префиксом choose_clan
        await message.answer("Выбери клан для своего основного аккаунта:", reply_markup=choose_clan_keyboard(clans))

        await state.update_data(clans=clans, role=current_role)
        await state.set_state(RegistrationState.choosing_clan)

    else:
        clan = clans[0]
        await db.upsert_member(
            user_id=user_id,
            username=username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            clan=clan,
            role=current_role,
            registered=0
        )
        await message.answer(
            f"Привет, @{username or message.from_user.first_name}! Это приветственное сообщение бота Vigarik Squad.\n"
            f"Твой клан определен как: <b>{CLAN_DISPLAY[clan]}</b>.\n\n"
            f"Введите ваш точный игровой никнейм (Nick в игре):",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.update_data(clan=clan)
        await state.set_state(RegistrationState.entering_nick)
