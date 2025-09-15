import asyncio
import logging
import os
import tempfile
import shutil
from typing import Dict, Tuple, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from aiohttp import web

from video_unique import unique_video

# Настройки логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Ограничение параллелизма (число одновременных задач)
SEM = asyncio.Semaphore(int(os.getenv("WORKERS", "2")))
# Максимальное число копий за одну задачу
MAX_COPIES = int(os.getenv("MAX_COPIES", "10"))

# Память для выбора количества копий на пользователя
# user_id -> (temp_file_path, orig_filename)
pending_files: Dict[int, Tuple[str, str]] = {}


def build_copies_keyboard(max_copies: int = MAX_COPIES):
    kb = InlineKeyboardBuilder()
    for i in range(1, max_copies + 1):
        kb.button(text=f"{i}", callback_data=f"copies:{i}")
    # Раскладываем по рядам по 5 кнопок
    kb.adjust(5)
    return kb.as_markup()


async def download_telegram_file(bot: Bot, message: Message) -> Optional[Tuple[str, str]]:
    try:
        MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "50"))
        MAX_BYTES = MAX_FILE_MB * 1024 * 1024

        if message.video:
            file_id = message.video.file_id
            filename = message.video.file_name or "video.mp4"
            size = message.video.file_size or 0
        elif message.document and (message.document.mime_type or "").startswith("video/"):
            file_id = message.document.file_id
            filename = message.document.file_name or "video.mp4"
            size = message.document.file_size or 0
        else:
            return None

        # Проверка лимита размера файла
        if size and size > MAX_BYTES:
            await message.answer(
                f"Файл слишком большой: {(size/1024/1024):.1f} МБ. Допустимый максимум — {MAX_FILE_MB} МБ."
            )
            return None

        file = await bot.get_file(file_id)
        fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1] or ".mp4")
        os.close(fd)
        await bot.download_file(file.file_path, destination=tmp_path)
        return tmp_path, filename
    except Exception as e:
        logger.exception("Ошибка скачивания файла: %s", e)
        return None


async def process_and_send(bot: Bot, chat_id: int, input_path: str, copies: int):
    """Запускает уникализацию в отдельном потоке и отправляет результаты пользователю."""
    await bot.send_message(chat_id, f"Запускаю обработку… Количество копий: {copies}. Это может занять время.")

    # Выделяем рабочую папку на время задачи
    workdir = tempfile.mkdtemp(prefix="uniq_")
    try:
        async with SEM:
            # MoviePy/ffmpeg — блокирующие операции. Выполним в thread-пуле.
            outputs = await asyncio.to_thread(unique_video, input_path, copies, workdir)

        # Попытаемся отправить по одному файлу
        for p in outputs:
            try:
                await bot.send_chat_action(chat_id, "upload_video")
                await bot.send_video(chat_id, video=FSInputFile(p))
            except Exception as e:
                logger.exception("Ошибка отправки файла %s: %s", p, e)
                await bot.send_message(chat_id, f"Не удалось отправить файл: {os.path.basename(p)}")

        await bot.send_message(chat_id, "Готово! Если нужно, пришлите новое видео.")
    except Exception as e:
        logger.exception("Ошибка обработки: %s", e)
        await bot.send_message(chat_id, "Произошла ошибка при обработке видео. Попробуйте позже.")
    finally:
        # Удалим исходник и рабочие файлы
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


async def on_start(message: Message):
    text = (
        "Привет! Я уникализирую видео.\n\n"
        "Пришлите видео в чат (как видео или документ). После этого я попрошу выбрать количество копий.\n"
        f"Можно выбрать 1–{MAX_COPIES} копий."
    )
    await message.answer(text)


async def on_help(message: Message):
    text = (
        "Как пользоваться:\n"
        "1) Отправьте мне видео или документ с видео.\n"
        "2) Нажмите на кнопку с количеством копий.\n"
        "3) Дождитесь готовых файлов.\n\n"
        f"Ограничение: максимум {MAX_COPIES} копий за одну задачу.\n"
        "Команда /start — показать приветствие."
    )
    await message.answer(text)


async def on_video(message: Message, bot: Bot):
    res = await download_telegram_file(bot, message)
    if not res:
        await message.answer("Пришлите видеофайл (как видео или документ)")
        return
    tmp_path, filename = res
    pending_files[message.from_user.id] = (tmp_path, filename)
    await message.answer("Сколько копий создать?", reply_markup=build_copies_keyboard())


async def on_copies(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    data = callback.data or ""
    if not data.startswith("copies:"):
        return
    try:
        copies = int(data.split(":", 1)[1])
    except Exception:
        copies = 1

    # Применяем лимит
    if copies < 1:
        copies = 1
    if copies > MAX_COPIES:
        copies = MAX_COPIES

    info = pending_files.pop(callback.from_user.id, None)
    if not info:
        await callback.message.answer("Не найден загруженный файл. Пришлите видео ещё раз.")
        return

    tmp_path, _ = info
    await callback.message.answer(f"Принято, создаю {copies} копий…")
    # Запускаем задачу в фоне, чтобы не блокировать обработку бота
    asyncio.create_task(process_and_send(bot, callback.message.chat.id, tmp_path, copies))


async def main():
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения (.env)")

    bot = Bot(token=token)
    dp = Dispatcher()

    # Команды
    dp.message.register(on_start, CommandStart())
    dp.message.register(on_help, Command("help"))

    # Получение видео: как video или как документ (тип проверим внутри)
    dp.message.register(on_video, F.video)
    dp.message.register(on_video, F.document)

    # Обработка выбора количества копий
    dp.callback_query.register(on_copies, F.data.startswith("copies:"))

    # На всякий случай удалим webhook, чтобы точно использовать long polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook removed; using long polling")
    except Exception:
        logger.warning("Failed to delete webhook; will continue with polling")

    # Поднимаем простой HTTP-сервер для health-check (Koyeb routing)
    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")
    async def root(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", root)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logger.info("HTTP health server started on port %s", port)
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем HTTP-сервер аккуратно
        try:
            await runner.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
