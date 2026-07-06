import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import get_member, upsert_member, get_all_members
from utils.permissions import can_appoint_admins
from utils.keyboards import appoint_role_keyboard, admin_panel_keyboard
from config import ROLE_LABELS
from .base import AdminStates  # Импортируем общие стейты

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "⚙️ Назначить модерацию")
async def appoint_start(message: Message, state: FSMContext):
    member = await get_member(message.from_user.id)
    if not member or not can_appoint_admins(member):
        await message.answer("⛔ У тебя нет прав для назначения модерации.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="edit_list:cancel")]
    ])

    await message.answer(
        "Напиши <b>user_id</b> или <b>@username</b> участника, "
        "которому хочешь назначить роль:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(AdminStates.waiting_appoint_user)

@router.message(AdminStates.waiting_appoint_user)
async def appoint_receive_user(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()

    if text in ("/cancel", "/back"):
        await state.clear()
        member = await get_member(message.from_user.id)
        await message.answer(
            "❌ Назначение модерации отменено.",
            reply_markup=admin_panel_keyboard(member.get("role", "member"))
        )
        return

    target = None
    if text.lstrip("-").isdigit():
        target = await get_member(int(text))
    elif text.startswith("@"):
        uname = text[1:]
        all_members = await get_all_members()
        target = next((m for m in all_members if m.get("username") == uname), None)

    if not target:
        await message.answer("❌ Участник не найден в базе. Попробуй ещё раз:")
        return

    await state.update_data(target_id=target["user_id"])
    nick = target.get("game_nick") or target.get("username") or str(target["user_id"])
    await message.answer(
        f"Выбери роль для участника <b>{nick}</b>:",
        parse_mode="HTML",
        reply_markup=appoint_role_keyboard(target["user_id"]),
    )
    await state.clear()


@router.callback_query(lambda c: c.data and c.data.startswith("appoint:") and c.data != "appoint:cancel")
async def appoint_role_cb(call: CallbackQuery, bot: Bot):
    parts = call.data.split(":")
    if len(parts) < 3:
        return
    _, target_id_str, role = parts[0], parts[1], parts[2]

    admin = await get_member(call.from_user.id)
    if not admin or not can_appoint_admins(admin):
        await call.answer("⛔ Нет прав.", show_alert=True)
        return

    try:
        target_id = int(target_id_str)
    except ValueError:
        return

    target = await get_member(target_id)
    if not target:
        await call.answer("❌ Игрок не найден в БД чата.", show_alert=True)
        return

    # 1. Обновляем роль в оперативной базе данных бота
    await upsert_member(user_id=target_id, role=role)

    # 2. ФИЗИЧЕСКАЯ ЗАПИСЬ В ФАЙЛ admins.txt
    import config
    uname = target.get("username") or "unknown"
    clan = target.get("clan") or "none"

    # Сначала удалим старую запись этого юзера из файла (если она была), чтобы избежать дубликатов
    lines = []
    if os.path.exists(config.ADMINS_FILE_PATH):
        with open(config.ADMINS_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip().startswith(f"{target_id}:"):
                    lines.append(line)

    # Добавляем новую строчку в структуру файла
    lines.append(f"{target_id}:{uname}:{role}:{clan}\n")

    # Перезаписываем файл целиком со свежими данными
    with open(config.ADMINS_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # 3. ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ КОНФИГА В ПАМЯТИ НА ЛЕТУ
    from utils.admin_logger import reload_bot_config, log_admin_action
    reload_bot_config()

    role_label = config.ROLE_LABELS.get(role, role)
    nick = target.get("game_nick") or target.get("username") or str(target_id)

    await call.message.edit_text(
        f"✅ Роль <b>{role_label}</b> успешно назначена участнику <b>{nick}</b> и сохранена в admins.txt!",
        parse_mode="HTML",
    )
    await call.answer()

    # Отправляем отчет в топик общих логов админки
    await log_admin_action(
        bot=bot,
        admin_id=call.from_user.id,
        admin_name=call.from_user.username or call.from_user.first_name,
        action_text=f"Выдал роль <b>{role_label}</b> пользователю {nick} (ID: <code>{target_id}</code>). Данные внесены в admins.txt."
    )

    try:
        await bot.send_message(
            target_id,
            f"🎉 Тебе назначена новая роль администрации ViGarik Squad: <b>{role_label}</b>\nПерезапусти бота через /start",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "appoint:cancel")
async def appoint_cancel(call: CallbackQuery):
    await call.message.delete()
    await call.answer()
