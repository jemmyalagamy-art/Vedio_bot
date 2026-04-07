import os
import tempfile
import logging

import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = (
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
)

MAX_FILE_SIZE_MB = 50


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hello! Send me a video link from TikTok, Instagram, Facebook, or Twitter/X "
        "and I'll download and send the video back to you.\n\n"
        "Supported platforms:\n"
        "• TikTok\n"
        "• Instagram\n"
        "• Facebook\n"
        "• Twitter / X"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Just send me a video URL from one of these platforms:\n"
        "• TikTok — https://www.tiktok.com/...\n"
        "• Instagram — https://www.instagram.com/...\n"
        "• Facebook — https://www.facebook.com/...\n"
        "• Twitter/X — https://twitter.com/... or https://x.com/..."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if not text.startswith("http"):
        await update.message.reply_text(
            "Please send a valid video URL (starting with http:// or https://)."
        )
        return

    if not is_supported_url(text):
        await update.message.reply_text(
            "Sorry, that URL isn't from a supported platform.\n"
            "Supported: TikTok, Instagram, Facebook, Twitter/X"
        )
        return

    status_msg = await update.message.reply_text("⏳ Downloading your video, please wait...")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(text, download=True)
                filename = ydl.prepare_filename(info)

                if not filename.endswith(".mp4"):
                    base = os.path.splitext(filename)[0]
                    filename = base + ".mp4"

            if not os.path.exists(filename):
                files = os.listdir(tmpdir)
                if files:
                    filename = os.path.join(tmpdir, files[0])
                else:
                    await status_msg.edit_text(
                        "❌ Download failed: could not find the downloaded file."
                    )
                    return

            file_size_mb = os.path.getsize(filename) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                await status_msg.edit_text(
                    f"❌ The video is too large ({file_size_mb:.1f} MB). "
                    f"Telegram only allows files up to {MAX_FILE_SIZE_MB} MB."
                )
                return

            title = info.get("title", "video")
            await status_msg.edit_text(f"✅ Downloaded! Sending \"{title}\"...")

            with open(filename, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=title,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )

            await status_msg.delete()

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error("DownloadError: %s", error_msg)

            if "private" in error_msg.lower():
                await status_msg.edit_text("❌ This video is private and cannot be downloaded.")
            elif "age" in error_msg.lower():
                await status_msg.edit_text("❌ This video is age-restricted and cannot be downloaded.")
            elif "unavailable" in error_msg.lower() or "not found" in error_msg.lower():
                await status_msg.edit_text("❌ This video is unavailable or has been removed.")
            else:
                await status_msg.edit_text(
                    "❌ Could not download the video. The link may be private, expired, or unsupported."
                )

        except Exception as e:
            logger.exception("Unexpected error while handling %s", text)
            await status_msg.edit_text(
                "❌ An unexpected error occurred. Please try again later."
            )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
