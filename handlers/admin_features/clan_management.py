import re
import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import get_member, upsert_member, get_all_members, get_unregistered_members, get_clan_members, remove_member
from utils.permissions import can_edit_list, is_any_admin
from utils.keyboards import main_menu
from utils.roster_sync import sync_roster_msg
from config import CLAN_DISPLAY
from .base import AdminStates

router = Router()

@router.message(F.text == "📋 Редактировать список клана")
async def edit_list_select_clan(message: Message, state: FSMContext):
    member = await get_member(message.from_user.id)
    if not member or not can_edit_list(member):
        await message.answer("⛔ Недостаточно прав. Требуется Вице Президент и выше.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏰 Основа (Squad)", callback_data="edit_clan_sel:squad")],
        [InlineKeyboardButton(text="🎓 Академия (Academy)", callback_data="edit_clan_sel:academy")],
        [InlineKeyboardButton(text="⚔️ Ивенты (Events)", callback_data="edit_clan_sel:events")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_list:cancel")]
    ])

    await message.answer("Выбери клан, список которого ты хочешь изменить или пополнить:", reply_markup=kb)
    await state.set_state(AdminStates.choosing_clan_to_edit)

@router.callback_query(F.data.startswith("edit_clan_sel:"), AdminStates.choosing_clan_to_edit)
async def edit_list_show_members(callback: CallbackQuery, state: FSMContext):
    clan = callback.data.split(":")[1]
    await state.update_data(selected_clan=clan)

    members = await get_clan_members(clan)
    all_db = await get_all_members()
    unregistered_in_clan = [m for m in all_db if m.get("clan") == clan and not m.get("game_nick")]

    seen_ids = set()
    combined_members = []
    for m in members + unregistered_in_clan:
        if m["user_id"] not in seen_ids:
            seen_ids.add(m["user_id"])
            combined_members.append(m)

    lines = [f"<b>Редактирование списка: {CLAN_DISPLAY.get(clan)}</b>\n"]

    if not combined_members:
        lines.append("<i>Список сейчас пуст.</i>")
    else:
        for m in combined_members:
            uid = m["user_id"]
            nick = m.get("game_nick") or "<i>(Нет игрового ника ❌)</i>"
            uname = f"@{m['username']}" if m.get("username") else f"ID: {uid}"
            reg_marker = "✅" if m.get("registered") == 1 else "💤"
            lines.append(f"• <code>{uid}</code> | {reg_marker} {uname} | {nick}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Массовое добавление участников", callback_data=f"mass_import:{clan}")],
        [InlineKeyboardButton(text="◀️ Назад к выбору клана", callback_data="edit_clan_back_to_sel")],
        [InlineKeyboardButton(text="❌ Выйти из меню", callback_data="edit_list:cancel")]
    ])

    await callback.message.edit_text(
        "\n".join(lines) + "\n\nЧтобы изменить ник или удалить человека, <b>введи его user_id</b> сообщением ниже:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(AdminStates.waiting_edit_member_id)
    await callback.answer()

@router.callback_query(F.data == "edit_clan_back_to_sel", AdminStates.waiting_edit_member_id)
async def edit_clan_back_to_sel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await edit_list_select_clan(callback.message, state)
    await callback.message.delete()
    await callback.answer()

@router.message(AdminStates.waiting_edit_member_id)
async def edit_list_receive_id(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    clan = data.get("selected_clan")

    if not text.lstrip("-").isdigit():
        await message.answer("Введи корректный числовой user_id участника:")
        return

    target_id = int(text)
    target = await get_member(target_id)

    if not target:
        await message.answer("❌ Участник с таким ID не найден в базе.")
        return

    await state.update_data(edit_target_id=target_id)
    current_nick = target.get("game_nick") or "Отсутствует"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_list:cancel")]
    ])

    await message.answer(
        f"Участник: @{target.get('username') or 'нет'} (ID: <code>{target_id}</code>)\n"
        f"Текущий игровой ник: <b>{current_nick}</b>\n\n"
        f"✍️ Напиши новый игровой ник для него.\n"
        f"<i>(Или отправь команду <code>/delete</code> чтобы убрать его из этого клана)</i>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(AdminStates.waiting_new_nick_for_member)

@router.message(AdminStates.waiting_new_nick_for_member)
@router.message(AdminStates.waiting_new_nick_for_member)
async def edit_list_set_nick(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_id = data.get("edit_target_id")
    clan = data.get("selected_clan")
    editor = await get_member(message.from_user.id)

    if message.text.strip() == "/delete":
        await remove_member(target_id)

        # ЛОГИРОВАНИЕ УДАЛЕНИЯ
        from utils.admin_logger import log_admin_action
        await log_admin_action(
            bot=bot,
            admin_id=message.from_user.id,
            admin_name=message.from_user.username or message.from_user.first_name,
            action_text=f"🗑 Полностью удалил из базы участника ID <code>{target_id}</code>.",
            clan_key=clan
        )

        await state.clear()
        await message.answer("🗑 Участник полностью удалён из базы.", reply_markup=main_menu(editor))
        await sync_roster_msg(bot, clan)
        return

    new_nick = message.text.strip()
    if not new_nick or len(new_nick) > 30:
        await message.answer("Ник не может быть пустым или длиннее 30 символов. Введи заново:")
        return

    await upsert_member(user_id=target_id, game_nick=new_nick, registered=1, clan=clan)

    # ЛОГИРОВАНИЕ СМЕНЫ НИКА АДМИНОМ
    from utils.admin_logger import log_admin_action
    await log_admin_action(
        bot=bot,
        admin_id=message.from_user.id,
        admin_name=message.from_user.username or message.from_user.first_name,
        action_text=f"✏️ Изменил ник участнику ID <code>{target_id}</code> на <b>{new_nick}</b>.",
        clan_key=clan
    )

    await state.clear()
    await message.answer(f"✅ Ник участника успешно изменен на <b>{new_nick}</b>!", parse_mode="HTML",
                         reply_markup=main_menu(editor))
    await sync_roster_msg(bot, clan)

@router.callback_query(F.data.startswith("mass_import:"), AdminStates.waiting_edit_member_id)
async def mass_import_start(callback: CallbackQuery, state: FSMContext):
    clan = callback.data.split(":")[1]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_list:cancel")]
    ])

    await callback.message.edit_text(
        f"📋 <b>Массовое добавление в клан {CLAN_DISPLAY.get(clan)}</b>\n\n"
        f"Отправь список участников единым сообщением. Каждая пара (тег и ник) должна быть на новой строчке.\n"
        f"Разделитель — тире или дефис.\n\n"
        f"<b>Пример формата (до 20 строк):</b>\n"
        f"<code>@username1 — НикВИгре1</code>\n"
        f"<code>@username2 — НикВИгре2</code>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(AdminStates.waiting_mass_import)
    await callback.answer()

@router.message(AdminStates.waiting_mass_import)
async def mass_import_process(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    clan = data.get("selected_clan")
    editor = await get_member(message.from_user.id)

    lines = [line.strip() for line in message.text.split("\n") if line.strip()]

    if len(lines) > 30:
        await message.answer("❌ Слишком большой список! Лимит за один раз — 30 строк. Сократи список и отправь заново:")
        return

    success_count = 0
    errors = []
    all_db_members = await get_all_members()

    for idx, line in enumerate(lines, 1):
        parts = re.split(r'\s*[\-—–]\s*', line, maxsplit=1)
        if len(parts) < 2:
            errors.append(f"Строка {idx}: не найден разделитель (тире)")
            continue

        raw_tag, game_nick = parts[0].strip(), parts[1].strip()
        username = raw_tag.replace("@", "").strip()

        if not username or not game_nick:
            errors.append(f"Строка {idx}: пустой тег или игровой ник")
            continue

        existing_user = next(
            (m for m in all_db_members if m.get("username") and str(m.get("username")).lower() == username.lower()),
            None)

        # ИСПРАВЛЕНО: Безопасный апсерт без фейковых ID и неинициализированных локальных переменных
        if existing_user:
            real_uid = existing_user.get("user_id")
            await upsert_member(user_id=real_uid, username=username, game_nick=game_nick, clan=clan, registered=1)
        else:
            await upsert_member(user_id=None, username=username, game_nick=game_nick, clan=clan, registered=1)

        success_count += 1

    report = f"📊 <b>Результат импорта в клан {CLAN_DISPLAY.get(clan)}:</b>\n"
    report += f"✅ Успешно добавлено/обновлено: <b>{success_count}</b> участников.\n"

    if errors:
        report += "\n⚠️ <b>Ошибки в строках:</b>\n" + "\n".join(errors[:10])

    await message.answer(report, parse_mode="HTML", reply_markup=main_menu(editor))
    await state.clear()
    await sync_roster_msg(bot, clan)

@router.callback_query(F.data == "edit_list:cancel")
async def process_edit_list_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("Редактирование отменено")

@router.message(F.text == "👤 Участники без ников")
async def unregistered_list(message: Message):
    member = await get_member(message.from_user.id)
    if not member or not is_any_admin(member):
        await message.answer("⛔ Нет прав.")
        return

    role = member.get("role", "member")

    if role in ("president", "grand_vice_president", "grand_vice"):
        clan_to_search = None
    else:
        clan_to_search = member.get("clan")

    members = await get_unregistered_members(clan_to_search)

    if not members:
        await message.answer("✅ Все участники успешно внесли свои игровые никнеймы!")
        return

    clan_title = CLAN_DISPLAY.get(clan_to_search, "Все кланы")
    lines = [f"<b>Участники без игрового ника ({clan_title}):</b>\n"]

    for m in members:
        uname = m.get("username")
        tg_name = f"@{uname}" if uname else m.get("first_name") or "Игрок"
        captured_clan = CLAN_DISPLAY.get(m.get('clan'), 'Не определен')
        # ИСПРАВЛЕНО: Эти две строчки теперь строго внутри цикла for!
        lines.append(f"• {tg_name} — <code>{m['user_id']}</code> <i>(Клан: {captured_clan})</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── ДОБАВЛЕНИЕ ТВИНКА (Вице-президент и выше) ───────────────────────────────

@router.message(F.text == "➕ Добавить твинк")
async def add_twink_start(message: Message, state: FSMContext):
    """Проверяет права и запрашивает юзера для привязки твинка."""
    member = await get_member(message.from_user.id)
    if not member or not can_edit_list(member):  # Проверка: Вице и выше
        await message.answer("⛔ Недостаточно прав.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_list:cancel")]
    ])

    await message.answer(
        "➕ <b>Режим добавления твинка</b>\n\n"
        "Пришли <b>user_id</b> или <b>@username</b> игрока, "
        "которому нужно добавить второй (твинк) аккаунт:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(AdminStates.waiting_twink_user)


@router.message(AdminStates.waiting_twink_user)
async def add_twink_receive_user(message: Message, state: FSMContext):
    """Находит данные основного игрока, чтобы скопировать их для твинка."""
    text = message.text.strip()
    target = None

    if text.lstrip("-").isdigit():
        target = await get_member(int(text))
    elif text.startswith("@"):
        uname = text[1:].lower().strip()
        all_members = await get_all_members()
        target = next((m for m in all_members if m.get("username") and m["username"].lower() == uname), None)

    if not target:
        await message.answer(
            "❌ Игрок не найден в базе. Твинк можно добавить только существующему игроку! Попробуй еще раз:")
        return

    # Сохраняем Telegram данные основы, чтобы привязать к ним твинк
    await state.update_data(
        t_id=target.get("user_id"),
        t_uname=target.get("username"),
        t_fname=target.get("first_name"),
        t_lname=target.get("last_name")
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏰 Основа (Squad)", callback_data="twink_clan:squad")],
        [InlineKeyboardButton(text="🎓 Академия (Academy)", callback_data="twink_clan:academy")],
        [InlineKeyboardButton(text="⚔️ Ивенты (Events)", callback_data="twink_clan:events")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_list:cancel")]
    ])

    await message.answer(f"Игрок найден. Выбери <b>клан</b>, в который нужно занести его твинк:", parse_mode="HTML",
                         reply_markup=kb)
    await state.set_state(AdminStates.waiting_twink_clan)


@router.callback_query(AdminStates.waiting_twink_clan, F.data.startswith("twink_clan:"))
async def add_twink_receive_clan(callback: CallbackQuery, state: FSMContext):
    """Фиксирует клан для твинка."""
    clan = callback.data.split(":")[1]
    await state.update_data(t_clan=clan)

    await callback.message.edit_text("✍️ Теперь введи <b>игровой никнейм твинка</b>:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_twink_nick)
    await callback.answer()


@router.message(AdminStates.waiting_twink_nick)
@router.message(AdminStates.waiting_twink_nick)
async def add_twink_finalize(message: Message, state: FSMContext, bot: Bot):
    """Создает запись твинка в БД через специальный асинхронный INSERT."""
    twink_nick = message.text.strip()
    if len(twink_nick) > 30:
        await message.answer("Ник слишком длинный. Введи до 30 символов:")
        return

    data = await state.get_data()
    editor = await get_member(message.from_user.id)
    t_clan = data.get("t_clan")

    import aiosqlite
    from database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO members (user_id, username, first_name, last_name, game_nick, clan, role, registered)
            VALUES (?, ?, ?, ?, ?, ?, 'member', 1)
            """,
            (data.get("t_id"), data.get("t_uname"), data.get("t_fname"), data.get("t_lname"), twink_nick, t_clan)
        )
        await db.commit()

    # ЛОГИРОВАНИЕ ДОБАВЛЕНИЯ ТВИНКА
    from utils.admin_logger import log_admin_action
    await log_admin_action(
        bot=bot,
        admin_id=message.from_user.id,
        admin_name=message.from_user.username or message.from_user.first_name,
        action_text=f"➕ Добавил твинк с ником <b>{twink_nick}</b> игроку ID <code>{data.get('t_id')}</code>.",
        clan_key=t_clan
    )

    await state.clear()
    await message.answer(
        f"✅ Твинк с ником <b>{twink_nick}</b> успешно добавлен игроку!",
        parse_mode="HTML",
        reply_markup=main_menu(editor)
    )

    await sync_roster_msg(bot, t_clan)
