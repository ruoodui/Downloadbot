import os
import uuid
import asyncio
import time
import nest_asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import yt_dlp

nest_asyncio.apply()
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@mitech808")

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

async def is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def send_subscription_prompt(update: Update):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")]
    ])
    await update.message.reply_text("⚠️ لا يمكنك استخدام البوت قبل الاشتراك في القناة:", reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    welcome = f"""
👋 أهلاً {user.first_name}!

🔹 أرسل رابط فيديو من YouTube لتحميله.

⚠️ تأكد من حقوق المحتوى قبل الاستخدام.
"""
    await update.message.reply_text(welcome.strip())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    url = update.message.text.strip()
    if url.startswith("http") and "." in url:
        loading_msg = await update.message.reply_text("⏳ جاري التحميل...")
        await download_video(loading_msg, url, "best")
    else:
        await update.message.reply_text("❌ الرجاء إرسال رابط صحيح.")

async def download_video(message, url, quality):
    filename = f"{uuid.uuid4()}.mp4"
    output = os.path.join(DOWNLOAD_FOLDER, filename)

    last_update = 0

    async def progress_hook(d):
        nonlocal last_update
        now = time.time()
        if now - last_update < 1:
            return
        last_update = now

        if d.get("status") == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded_bytes = d.get("downloaded_bytes", 0)
            eta = d.get("eta")

            if total_bytes:
                percent = downloaded_bytes / total_bytes * 100
                mb_downloaded = downloaded_bytes / (1024 * 1024)
                mb_total = total_bytes / (1024 * 1024)
                eta_text = f"{int(eta)} ثانية" if eta else "غير معروف"

                print(f"تحميل: {percent:.1f}% - {mb_downloaded:.1f}MB / {mb_total:.1f}MB - الوقت المتبقي: {eta_text}")
                text = (
                    f"⏳ جاري التحميل...\n"
                    f"{percent:.1f}% - {mb_downloaded:.1f}MB / {mb_total:.1f}MB\n"
                    f"🕒 الوقت المتبقي: {eta_text}"
                )
                try:
                    await message.edit_text(text)
                except Exception as e:
                    print(f"خطأ تحديث رسالة التحميل: {e}")

    try:
        print("بدأ التحميل")
        ydl_opts = {
            "format": quality,
            "outtmpl": output,
            "quiet": True,
            "nocheckcertificate": True,
            "progress_hooks": [lambda d: asyncio.create_task(progress_hook(d))],
            "http_headers": {"User-Agent": "Mozilla/5.0"},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        print("انتهى التحميل، جاري الإرسال")
        with open(output, "rb") as video_file:
            await message.reply_video(video=video_file)

        await asyncio.sleep(5)
        await message.delete()
        os.remove(output)
        print("تم الإرسال وحذف الملف المؤقت")

    except Exception as e:
        print(f"خطأ أثناء التحميل أو الإرسال: {e}")
        await message.reply_text(f"❌ خطأ أثناء التحميل: {e}")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
