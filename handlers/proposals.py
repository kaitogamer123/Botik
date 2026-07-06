"""
Предложения участников → президентам.
"""

import logging
import json
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импортируем состояния из нашего нового базового модуля админки
from handlers.admin_features.base import AdminStates

from database import (
    get_member, add_proposal, get_proposals, get_proposal,
    update_proposal_status, get_all_members,
)
from utils.permissions import can_read_proposals, can_edit_list
from utils.keyboards import (
    proposals_list_keyboard, proposal_actions_keyboard, back_keyboard, main_menu, admin_panel_keyboard
)
from config import INITIAL_ADMINS

logger = logging.getLogger(__name__)
router = Router()


class ProposalStates(StatesGroup):
    collecting = State()


# ─── Отправить предложение ────────────────────────────────────────────────────

@router.message(F.text == "💡 Отправить предложение")
async def start_proposal(message: Message, state: FSMContext):
    member = await get_member(message.from_user.id)
    if not member or not member.get("registered"):
        await message.answer("Сначала пройди регистрацию. /start")
        return

    await state.set_state(ProposalStates.collecting)
    await state.update_data(texts=[], photos=[])
    await message.answer(
        "✍️ Напиши своё предложение (можно прикрепить фото).\n\n"
        "Когда закончишь — отправь /done\n"
        "Для отмены — /cancel"
    )


@router.message(ProposalStates.collecting, F.photo)
async def collect_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    texts  = data.get("texts", [])

    # Берём наибольшее фото
    photos.append(message.photo[-1].file_id)
    caption = message.caption or ""
    if caption:
        texts.append(caption)

    await state.update_data(photos=photos, texts=texts)
    await message.answer("📎 Фото добавлено. Продолжай или отправь /done")


@router.message(ProposalStates.collecting, F.text)
async def collect_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if text == "/cancel":
        await state.clear()
        member = await get_member(message.from_user.id)
        await message.answer("❌ Отменено.", reply_markup=main_menu(member))
        return
    if text == "/done":
        await finalize_proposal(message, state, bot)
        return

    data = await state.get_data()
    texts = data.get("texts", [])
    texts.append(text)
    await state.update_data(texts=texts)
    await message.answer("📝 Добавлено. Ещё? Или /done для отправки.")


async def finalize_proposal(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    texts  = data.get("texts", [])
    photos = data.get("photos", [])
    full_text = "\n".join(texts)

    if not full_text and not photos:
        await message.answer("❌ Нельзя отправить пустое предложение.")
        return

    from_id = message.from_user.id
    proposal_id = await add_proposal(from_id, full_text, photos)
    member = await get_member(from_id)

    await state.clear()
    await message.answer(
        "✅ Предложение отправлено президентам!",
        reply_markup=main_menu(member),
    )

    # Уведомляем президентов
    presidents_ids = [
        uid for uid, info in INITIAL_ADMINS.items() if info["role"] == "president"
    ]

    # Также ищем в БД
    all_m = await get_all_members()
    for m in all_m:
        if m.get("role") == "president":
            presidents_ids.append(m["user_id"])

    for pid in set(presidents_ids):
        try:
            uname = member.get("username") or member.get("first_name") or str(from_id)
            await bot.send_message(
                pid,
                f"📬 <b>Новое предложение</b> от <b>{uname}</b>!\n"
                f"Нажми «📬 Прочитать предложки» чтобы просмотреть.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Читать предложки (президент) ─────────────────────────────────────────────

@router.message(F.text == "📬 Прочитать предложки")
async def read_proposals(message: Message):
    member = await get_member(message.from_user.id)
    if not member or not can_read_proposals(member):
        await message.answer("⛔ Нет прав.")
        return

    proposals = await get_proposals("pending")
    if not proposals:
        await message.answer(
            "📭 Предложка пуста.",
            reply_markup=back_keyboard("proposal:back"),
        )
        return

    # Обогащаем именами
    all_m = {m["user_id"]: m for m in await get_all_members()}
    for p in proposals:
        sender = all_m.get(p["from_id"])
        p["from_name"] = (
            sender.get("username") or sender.get("first_name") or str(p["from_id"])
        ) if sender else str(p["from_id"])

    await message.answer(
        "📬 <b>Предложения участников:</b>",
        parse_mode="HTML",
        reply_markup=proposals_list_keyboard(proposals),
    )


@router.callback_query(F.data == "proposal:list")
async def cb_proposal_list(call: CallbackQuery):
    member = await get_member(call.from_user.id)
    if not member or not can_read_proposals(member):
        await call.answer("⛔", show_alert=True)
        return

    proposals = await get_proposals("pending")
    if not proposals:
        await call.message.edit_text(
            "📭 Предложка пуста.",
            reply_markup=back_keyboard("proposal:back"),
        )
        return

    all_m = {m["user_id"]: m for m in await get_all_members()}
    for p in proposals:
        sender = all_m.get(p["from_id"])
        p["from_name"] = (
            sender.get("username") or sender.get("first_name") or str(p["from_id"])
        ) if sender else str(p["from_id"])

    await call.message.edit_text(
        "📬 <b>Предложения участников:</b>",
        parse_mode="HTML",
        reply_markup=proposals_list_keyboard(proposals),
    )
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("proposal:view:"))
async def cb_view_proposal(call: CallbackQuery, bot: Bot):
    proposal_id = int(call.data.split(":")[2])
    proposal = await get_proposal(proposal_id)
    if not proposal:
        await call.answer("Предложение не найдено.", show_alert=True)
        return

    all_m = {m["user_id"]: m for m in await get_all_members()}
    sender = all_m.get(proposal["from_id"])
    from_name = (
        sender.get("username") or sender.get("first_name") or str(proposal["from_id"])
    ) if sender else str(proposal["from_id"])

    text = (
        f"📩 <b>От: {from_name}</b>\n"
        f"📅 {proposal['sent_at'][:16]}\n\n"
        f"{proposal['text'] or '(без текста)'}"
    )

    photos = proposal.get("media_json", [])
    if photos:
        # Если photos это строка (например JSON строка из базы), раскомментируй строку ниже:
        # if isinstance(photos, str): photos = json.loads(photos)
        media = [InputMediaPhoto(media=fid) for fid in photos]
        await call.message.answer_media_group(media=media)

    await call.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=proposal_actions_keyboard(proposal_id, proposal["from_id"]),
    )
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("proposal:reject:"))
async def cb_reject_proposal(call: CallbackQuery, bot: Bot):
    proposal_id = int(call.data.split(":")[2])
    proposal = await get_proposal(proposal_id)
    if not proposal:
        await call.answer("Не найдено.", show_alert=True)
        return

    await update_proposal_status(proposal_id, "rejected")
    await call.message.edit_text("❌ Предложение отклонено.")
    await call.answer()

    try:
        await bot.send_message(
            proposal["from_id"],
            "😔 Твоё предложение было рассмотрено и отклонено.\n"
            "Ты можешь отправить новое предложение в любой момент.",
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("proposal:reply:"))
async def cb_reply_proposal_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    proposal_id = int(parts[2])
    target_user_id = int(parts[3])

    await state.set_state(AdminStates.waiting_proposal_answer)
    await state.update_data(reply_to_user_id=target_user_id, reply_proposal_id=proposal_id)

    await call.message.answer(
        "✍️ <b>Введите текст ответа для игрока:</b>\n"
        "Бот автоматически отправит его пользователю в личные сообщения.\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(AdminStates.waiting_proposal_answer, F.text)
async def cb_reply_proposal_send(message: Message, state: FSMContext, bot: Bot):
    if message.text.strip() == "/cancel":
        await state.clear()
        member = await get_member(message.from_user.id)
        await message.answer("❌ Отправка ответа отменена.", reply_markup=main_menu(member))
        return

    data = await state.get_data()
    target_user_id = data.get("reply_to_user_id")
    proposal_id = data.get("reply_proposal_id")

    if not target_user_id:
        await state.clear()
        return

    reply_text = message.text.strip()

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=f"✉️ <b>Ответ от Администрации по вашему предложению №{proposal_id}:</b>\n\n"
                 f"{reply_text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Ответ успешно доставлен игроку в ЛС!")
        await update_proposal_status(proposal_id, "answered")
    except Exception:
        await message.answer(f"❌ Не удалось отправить. Игрок заблокировал бота или сменил настройки приватности.")

    # ИСПРАВЛЕНО: Этот блок теперь сдвинут влево и сработает при любом исходе отправки!
    member = await get_member(message.from_user.id)
    await state.clear()

    await message.answer(
        "Возврат в панель управления.",
        reply_markup=admin_panel_keyboard(member.get("role", "member"))
    )


# ИСПРАВЛЕНО: Хэндлер полностью изолирован и находится на уровне модуля
@router.callback_query(F.data == "proposal:back")
async def cb_proposal_back(call: CallbackQuery):
    await call.message.delete()
    await call.answer()
