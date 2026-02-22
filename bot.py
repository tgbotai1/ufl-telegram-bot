import asyncio
import logging
import re

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, TelegramObject

import config
import database
import agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        is_group = event.chat.type in ("group", "supergroup")
        is_allowed = not config.ALLOWED_TG_IDS or user.id in config.ALLOWED_TG_IDS

        if is_group and not is_allowed:
            # Silently collect message, no response
            if event.text:
                await database.save_group_message(
                    event.chat.id, event.chat.title,
                    user.id, user.username, user.first_name,
                    event.text,
                )
            return

        if not is_group and not is_allowed:
            await event.answer("Доступ ограничен.")
            return

        return await handler(event, data)

dp.message.middleware(AccessMiddleware())


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await database.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    name = msg.from_user.first_name or "там"
    await msg.answer(
        f"Привет, {name}! Я UFL PM-ассистент.\n\n"
        "Задавай вопросы по проекту — я отвечу на основе базы знаний UFL.\n\n"
        "Команды:\n"
        "/history — история диалога\n"
        "/clear — очистить историю\n"
        "/stats — статистика (для администраторов)"
    )


@dp.message(Command("history"))
async def cmd_history(msg: Message):
    await database.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)
    rows = await database.get_history(msg.from_user.id, limit=10)
    if not rows:
        await msg.answer("История пустая.")
        return

    lines = []
    for r in rows:
        role_label = "Ты" if r["role"] == "user" else "Бот"
        ts = r["created_at"].strftime("%d.%m %H:%M")
        text = r["content"][:200] + ("…" if len(r["content"]) > 200 else "")
        lines.append(f"[{ts}] {role_label}: {text}")

    await msg.answer("\n\n".join(lines))


@dp.message(Command("clear"))
async def cmd_clear(msg: Message):
    await database.clear_history(msg.from_user.id)
    await msg.answer("История диалога очищена.")


@dp.message(Command("search"))
async def cmd_search(msg: Message):
    # Usage: /search @username [keyword]
    parts = (msg.text or "").split(None, 2)  # ['/search', '@username', 'keyword?']
    if len(parts) < 2:
        await msg.answer("Использование: /search @username [ключевое слово]\nПример: /search @ivanov дедлайн")
        return

    raw = parts[1].lstrip("@")
    keyword = parts[2] if len(parts) > 2 else None

    rows = await database.search_group_messages(username=raw, keyword=keyword, limit=50)
    if not rows:
        kw_hint = f" по теме «{keyword}»" if keyword else ""
        await msg.answer(f"Сообщений от @{raw}{kw_hint} не найдено.")
        return

    lines = []
    for r in rows:
        ts = r["created_at"].strftime("%d.%m %H:%M")
        chat = r["chat_title"] or "?"
        text = r["content"][:300] + ("…" if len(r["content"]) > 300 else "")
        lines.append(f"[{ts}] [{chat}] {text}")

    header = f"Найдено {len(rows)} сообщений от @{raw}"
    if keyword:
        header += f" (тема: {keyword})"
    await msg.answer(header + ":\n\n" + "\n\n".join(lines))


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id not in config.ADMIN_TG_IDS:
        await msg.answer("Нет доступа.")
        return
    stats = await database.get_stats()
    await msg.answer(
        f"Статистика:\n"
        f"Пользователей: {stats['users']}\n"
        f"Сообщений всего: {stats['messages']}\n"
        f"Токенов использовано: {stats['tokens']}\n"
        f"Активных за 24ч: {stats['active_today']}"
    )


@dp.message(F.text)
async def handle_message(msg: Message):
    await database.upsert_user(msg.from_user.id, msg.from_user.username, msg.from_user.first_name)

    # Save user message
    await database.save_message(msg.from_user.id, "user", msg.text)

    # Build context from history
    history = await database.get_history(msg.from_user.id, limit=config.HISTORY_CONTEXT_SIZE)
    messages = [{"role": r["role"], "content": r["content"]} for r in history]

    # If message mentions @usernames — inject their group messages as context
    mentions = list(dict.fromkeys(re.findall(r"@(\w+)", msg.text)))
    if mentions:
        context_parts = []
        for username in mentions:
            rows = await database.search_group_messages(username=username, limit=100)
            if rows:
                lines = [
                    f"[{r['created_at'].strftime('%d.%m %H:%M')}] [{r['chat_title'] or '?'}] {r['content']}"
                    for r in rows
                ]
                context_parts.append(f"Сообщения @{username} в группах:\n" + "\n".join(lines))
        if context_parts:
            messages = [{"role": "system", "content": "\n\n".join(context_parts)}] + messages

    # Show typing indicator
    await bot.send_chat_action(msg.chat.id, "typing")

    try:
        reply, tokens = await agent.ask_agent(messages)
    except Exception as e:
        log.error("Agent error: %s", e)
        await msg.answer("Ошибка при обращении к агенту. Попробуй ещё раз.")
        return

    # Save assistant reply
    await database.save_message(msg.from_user.id, "assistant", reply, tokens_used=tokens)

    await msg.answer(reply)


async def main():
    await database.init_db()
    log.info("Bot starting...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
