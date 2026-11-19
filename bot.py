"""Main Telegram bot entry point with handlers."""
import asyncio
import html
import logging
import sys
from pathlib import Path

import yt_dlp
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile

from config import config
from downloader import VideoDownloader, download_video, DownloadResult
from utils import (
    detect_platform,
    extract_urls,
    RateLimiter,
    DownloadSemaphore,
    UserError,
    DownloadError,
    RateLimitError,
    format_file_size,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Global instances
downloader = VideoDownloader(
    max_file_mb=config.max_file_mb,
    proxy_url=config.proxy_url,
    instagram_cookies=config.instagram_cookies,
    instagram_cookies_browser=config.instagram_cookies_browser,
)
rate_limiter = RateLimiter(max_requests=config.rate_limit_per_min)
download_semaphore = DownloadSemaphore(max_concurrent=3)

# Router for handlers
router = Router()


# --- Command Handlers ---

@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    """Handle /start command."""
    welcome_text = (
        "سلام! 👋\n\n"
        "من ربات دانلود ویدیو از تیک‌تاک و اینستاگرام هستم.\n\n"
        "📥 فقط لینک ویدیو را بفرستید:\n"
        "• تیک‌تاک: tiktok.com، vm.tiktok.com، vt.tiktok.com\n"
        "• اینستاگرام: Reel، Post، TV\n\n"
        "⚠️ محدودیت‌ها:\n"
        f"• حداکثر حجم فایل: {config.max_file_mb} مگابایت\n"
        f"• حداکثر {config.rate_limit_per_min} درخواست در دقیقه\n"
        "• فقط ویدیو (نه عکس/کاروسل)\n\n"
        "برای راهنما /help را بزنید."
    )
    await message.answer(welcome_text)


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Handle /help command."""
    help_text = (
        "📖 راهنمای استفاده:\n\n"
        "۱. لینک ویدیو تیک‌تاک یا اینستاگرام را کپی کنید\n"
        "۲. اینجا بفرستید (فقط لینک، متن اضافه نکنید)\n"
        "۳. صبر کنید تا دانلود و ارسال شود\n\n"
        "✅ لینک‌های پشتیبانی شده:\n"
        "• https://www.tiktok.com/@user/video/123456\n"
        "• https://vm.tiktok.com/xxx\n"
        "• https://vt.tiktok.com/xxx\n"
        "• https://www.instagram.com/reel/xxx\n"
        "• https://www.instagram.com/p/xxx\n"
        "• https://www.instagram.com/tv/xxx\n\n"
        "❌ پشتیبانی نمی‌شود:\n"
        "• استوری (Story)\n"
        "• پست‌های فقط عکس/کاروسل\n"
        "• ویدیوهای خصوصی/حذف‌شده\n"
        "• لینک‌های یوتیوب، آپارات، و غیره\n\n"
        f"⚙️ تنظیمات:\n"
        f"• حداکثر حجم: {config.max_file_mb} MB\n"
        f"• محدودیت نرخ: {config.rate_limit_per_min} درخواست/دقیقه\n"
        f"• دانلود همزمان: ۳\n\n"
        "❓ سوال دارید؟ کد منبع را بررسی کنید."
    )
    await message.answer(help_text)


# --- Link Detection & Download Handler ---

@router.message(F.text)
async def handle_message(message: types.Message) -> None:
    """Handle incoming messages, detect links, and process downloads."""
    text = message.text or ""
    urls = extract_urls(text)

    if not urls:
        # Not a link, ignore or show help
        return

    # Process first valid URL
    for url in urls:
        platform = detect_platform(url)
        if platform:
            await process_download(message, url, platform)
            return

    # No supported platform found
    await message.reply(
        "❌ لینک ارسالی پشتیبانی نمی‌شود.\n\n"
        "فقط لینک‌های زیر قابل دانلود هستند:\n"
        "• تیک‌تاک (tiktok.com, vm.tiktok.com, vt.tiktok.com)\n"
        "• اینستاگرام Reel / Post / TV (instagram.com/reel/, /p/, /tv/)"
    )


async def process_download(message: types.Message, url: str, platform: str) -> None:
    """Process video download with rate limiting and error handling."""
    user_id = message.from_user.id

    # Rate limit check - reply, don't raise (a raise never reaches the user)
    if not await rate_limiter.is_allowed(user_id):
        retry_after = await rate_limiter.get_retry_after(user_id)
        logger.info(f"Rate limit hit by {user_id}, retry after {retry_after}s")
        await message.reply(
            f"⏳ خیلی سریع درخواست دادید! لطفاً {retry_after} ثانیه صبر کنید."
        )
        return

    # Send "downloading..." status
    status_msg = await message.reply("⏬ در حال دانلود...")
    result: DownloadResult | None = None

    try:
        # Limit concurrent downloads
        async with download_semaphore:
            result: DownloadResult = await download_video(url, downloader)

        # Update status
        await status_msg.edit_text("📤 در حال ارسال ویدیو...")

        # Send video
        video_file = BufferedInputFile(
            result.file_path.read_bytes(),
            filename=result.file_path.name
        )

        caption = (
            f"✅ {html.escape(result.title)}\n"
            f"📦 {format_file_size(result.filesize)}"
        )
        if result.duration:
            mins, secs = divmod(result.duration, 60)
            caption += f" | ⏱ {mins}:{secs:02d}"
        if result.width and result.height:
            caption += f" | 📐 {result.width}x{result.height}"

        await message.answer_video(
            video=video_file,
            caption=caption,
            supports_streaming=True,
        )

        # Delete status message
        await status_msg.delete()

    except UserError as e:
        # User-facing errors (already have Persian message)
        await status_msg.edit_text(e.message_fa)
        logger.info(f"User error for {user_id}: {e.message_en}")

    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "⏱ زمان دانلود به پایان رسید. لطفاً دوباره تلاش کنید یا لینک کوتاه‌تر بفرستید."
        )
        logger.warning(f"Download timeout for {user_id}: {url}")

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        if "rate-limit" in error_msg or "429" in error_msg or "too many requests" in error_msg:
            await status_msg.edit_text(
                "⏳ اینستاگرام موقتاً درخواست‌های زیاد را مسدود کرده است.\n"
                "چند دقیقه دیگر دوباره تلاش کنید.\n"
                "برای کاهش این خطا، فایل cookies.txt را در تنظیمات قرار دهید."
            )
        elif "login required" in error_msg or "not available" in error_msg or "private" in error_msg:
            await status_msg.edit_text(
                "🔒 این ویدیو خصوصی است یا اینستاگرام نیاز به لاگین دارد.\n"
                "راه حل: فایل cookies.txt را در پوشه پروژه بگذارید و در .env مقدار "
                "INSTAGRAM_COOKIES=cookies.txt را تنظیم کنید."
            )
        elif "removed" in error_msg or "deleted" in error_msg or "unavailable" in error_msg:
            await status_msg.edit_text("🗑 این ویدیو حذف شده یا در دسترس نیست.")
        elif "geo" in error_msg or "country" in error_msg:
            await status_msg.edit_text("🌍 این ویدیو در کشور شما در دسترس نیست.")
        else:
            await status_msg.edit_text("❌ خطا در دانلود. لینک را چک کنید یا بعداً تلاش کنید.")
        logger.error(f"yt-dlp error for {user_id}: {e}")

    except Exception as e:
        # Unexpected errors - log full traceback, show generic message
        logger.exception(f"Unexpected error for user {user_id}, url {url}")
        await status_msg.edit_text(
            "⚠️ خطای غیرمنتظره رخ داد. لطفاً بعداً تلاش کنید."
        )

    finally:
        # Only this download's own temp dir - never other users' in-flight files
        if result is not None:
            downloader.cleanup_result(result)


# --- Error Handler ---

@router.error()
async def error_handler(event: types.ErrorEvent) -> None:
    """Global error handler for unhandled exceptions."""
    logger.exception(f"Unhandled error: {event.exception}")


# --- Main Entry Point ---

async def main() -> None:
    """Start the bot."""
    logger.info("Starting Telegram video downloader bot...")

    # Validate token
    if not config.bot_token or config.bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not set in .env file!")
        print("❌ توکن ربات در فایل .env تنظیم نشده است!")
        print("فایل .env را باز کنید و BOT_TOKEN را وارد کنید.")
        return

    # Configure bot with proxy if needed
    bot_kwargs = {"token": config.bot_token}
    if config.proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy=config.proxy_url)
        bot_kwargs["session"] = session
        logger.info(f"Using proxy: {config.proxy_url}")

    bot = Bot(
        **bot_kwargs,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Start polling
    logger.info("Bot started. Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        downloader.cleanup()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)