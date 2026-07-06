import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup

from database import get_member
from utils.permissions import is_any_admin
from utils.keyboards import main_menu, admin_panel_keyboard
from config import ROLE_LABELS

logger = logging.getLogger(__name__)
router = Router()

class AdminStates(StatesGroup):
    waiting_appoint_user = State()        # Ожидание юзера для роли
    choosing_clan_to_edit = State()       # Выбор клана
    waiting_edit_member_id = State()      # Ввод ID игрока в клане
    waiting_new_nick_for_member = State() # Ввод нового никнейма
    waiting_mass_import = State()         # Массовый импорт строк
    waiting_announcement_text = State()   # Рассылка новостей
    waiting_proposal_answer = State()     # Ответ на заявку
    waiting_twink_user = State()        # Ожидание ID или тега основы
    waiting_twink_clan = State()        # Ожидание выбора клана для твинка
    waiting_twink_nick = State()        # Ожидание игрового ника твинка

@router.message(F.text == "👔 Для админов")
@router.message(F.text == "👔 Для аgминов")
@router.message(F.text.contains("Для админ"))
@router.message(F.text.contains("Для admin"))
async def cmd_open_admin_panel(message: Message):
    member = await get_member(message.from_user.id)
    if not member or not is_any_admin(member):
        await message.answer("⛔ Доступ заблокирован. Меню только для администрации.")
        return

    role = member.get("role", "member")
    await message.answer(
        f"👔 <b>Панель управления ViGarik Squad</b>\n"
        f"Ваша текущая роль: {ROLE_LABELS.get(role, role)}\n\n"
        f"Выбери необходимое действие на клавиатуре ниже:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(role)
    )

@router.message(F.text == "◀️ Выйти из админки")
@router.message(F.text.contains("Выйти из админ"))
async def cmd_close_admin_panel(message: Message):
    member = await get_member(message.from_user.id)
    await message.answer(
        "🔄 Возвращаюсь в главное меню игрока.",
        reply_markup=main_menu(member)
    )


@router.message(F.text == "/SetupBotVigarikThreads")
async def cmd_auto_setup_vigarik_threads(message: Message, bot: Bot):
    """
    Секретная команда автоматического развертывания топиков логов.
    Доступна строго владельцу @Ka1D3en (ID: 7899153362).
    """
    # Жесткая проверка на твой ID
    if message.from_user.id != 7899153362:
        return

    import config
    from database import set_setting

    # Берем ID чата администрации из твоего конфига
    chat_id = config.LOGS_CHAT_ID or config.ADMIN_CHAT_ID

    if not chat_id:
        await message.answer(
            "❌ <b>Ошибка настройки:</b>\n"
            "Сначала пропиши ID чата в <code>LOGS_CHAT_ID</code> внутри файла <b>config.py</b>!",
            parse_mode="HTML"
        )
        return

    await message.answer("⏳ <b>Запуск развертывания системы...</b>\nСоздаю топики логов в административном чате...",
                         parse_mode="HTML")

    # Конфигурация топиков: ключ -> (Название, Цвет значка в HEX)
    topics_config = {
        "main_admin": ("👔 Общие логи админки", 0x6FB9F0),  # Синий
        "squad": ("👑 Логи Основы (Squad)", 0xFFD700),  # Золотой
        "academy": ("🎓 Логи Академии", 0x1CB0F6),  # Голубой
        "events": ("🎉 Логи Ивентов", 0xFF8500)  # Оранжевый
    }

    results = []

    for key, (name, color) in topics_config.items():
        try:
            # Отправляем запрос в Telegram API на создание темы на форуме
            topic = await bot.create_forum_topic(
                chat_id=chat_id,
                name=name,
                icon_color=color
            )

            # Сохраняем полученный thread_id прямо в базу данных на лету!
            await set_setting(f"topic_id_{key}", str(topic.message_thread_id))

            # Отправляем стартовый закреп в созданную тему
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic.message_thread_id,
                text=f"📌 Топик успешно инициализирован. Сюда будут поступать логи категории: <b>{name}</b>.",
                parse_mode="HTML"
            )
            results.append(f"✅ {name} — ID темы: <code>{topic.message_thread_id}</code>")

        except Exception as e:
            await message.answer(
                f"❌ Ошибка при создании топика <b>{name}</b>: {e}\nУбедись, что бот добавлен в чат и выдан статус Администратора с правом управления темами!",
                parse_mode="HTML")
            return

    report = (
            "🚀 <b>Система логирования успешно настроена!</b>\n\n"
            "Все топики созданы и привязаны к базе данных:\n" + "\n".join(results) +
            "\n\n<i>Перезапуск бота не требуется. Логгер уже начал перехват действий!</i>"
    )
    await message.answer(report, parse_mode="HTML")
@router.message(F.text == "/get_id")
async def cmd_get_chat_id_live(message: Message):
    """Временная команда для моментального получения ID группы."""
    await message.answer(
        f"🆔 <b>ID этого чата:</b> <code>{message.chat.id}</code>\n"
        f"📌 Скопируй его и вставь в config.py в поле LOGS_CHAT_ID"
    )
