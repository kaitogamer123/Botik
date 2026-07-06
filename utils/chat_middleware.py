from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from utils.admin_logger import log_user_chat


class ChatLoggingMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        # 1. Перехват входящего сообщения от ИГРОКА в ЛС
        if event.text and event.chat.type == "private":
            user = event.from_user

            # Игнорируем вызовы служебных команд, чтобы не спамить
            if not event.text.startswith(("/SetupBot", "/reload", "/refresh")):
                await log_user_chat(
                    bot=event.bot,
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    message_text=event.text,
                    is_bot_reply=False
                )

        # Передаем управление хэндлеру бота и ловим результат
        result = await handler(event, data)

        # 2. АВТО-ПЕРЕХВАТ ОТВЕТА БОТА (Ловит message.answer и message.reply на лету)
        if isinstance(result, Message) and result.chat.type == "private":
            # Проверяем, что сообщение отправил сам бот
            if result.from_user and result.from_user.is_bot:
                user = event.from_user  # Получаем данные игрока, кому ответил бот
                await log_user_chat(
                    bot=event.bot,
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    message_text=result.text or "[Медиа/Клавиатура]",
                    is_bot_reply=True
                )

        return result
