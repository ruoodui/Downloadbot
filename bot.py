import os
import uuid
import asyncio
import nest_asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import yt_dlp

nest_asyncio.apply()  # لتجنب مشاكل حلقة الأحداث في بعض البيئات (Railway, Jupyter...)

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@mitech808")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "mitech808")
ADMIN_ID = int(os.getenv("ADMIN_ID", "193646746"))

# إنشاء ملف الكوكيز من متغير البيئة
cookies_content = os.getenv("YOUTUBE_COOKIES", "")
if cookies_content:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(cookies_content)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

user_ids = set()
request_count = 0

async def is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def send_subscription_prompt(update: Update):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
        [InlineKeyboardButton("📷 تابعنا على Instagram", url=f"https://instagram.com/{INSTAGRAM_USERNAME}")]
    ])
    await update.message.reply_text("⚠️ لا يمكنك استخدام البوت قبل الاشتراك في القناة:", reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    welcome_text = f"""
👋 أهلاً {user.first_name}!

🔹 يدعم تحميل الفيديو والصوت من YouTube، TikTok، Instagram، وغيرها.

📥 فقط أرسل رابط الفيديو وسيظهر لك خيار التحميل.
🎧 استخدم /mp3 <رابط> لتحويل الفيديو إلى MP3.

⚠️ تأكد من حقوق المحتوى قبل الاستخدام.
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count
    user = update.effective_user

    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    user_ids.add(user.id)
    request_count += 1

    url = update.message.text.strip()

    if any(site in url for site in ["http://", "https://"]) and "." in url:
        context.user_data["last_url"] = url
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 تحميل فيديو", callback_data="video")],
            [InlineKeyboardButton("🎧 تحويل إلى MP3", callback_data="audio")]
        ])
        await update.message.reply_text("اختر نوع التحميل:", reply_markup=keyboard)
    else:
        await update.message.reply_text("❌ الرجاء إرسال رابط صحيح لفيديو.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    url = context.user_data.get("last_url")

    if not url:
        await query.message.reply_text("❌ لم يتم العثور على رابط محفوظ. أرسل الرابط مرة أخرى.")
        return

    await query.edit_message_text("⏳ جاري التحميل...")

    if action == "video":
        await download_best_video(query.message, url)
    elif action == "audio":
        await download_mp3(query.message, url)

async def download_best_video(message, url: str):
    try:
        filename = f"{uuid.uuid4()}.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)

        ydl_opts = {
            'format': 'best',
            'outtmpl': output_path,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': 'cookies.txt',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await message.reply_video(video=open(output_path, 'rb'))
        os.remove(output_path)

    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء تحميل الفيديو: {e}")

async def download_mp3(message, url: str):
    try:
        filename = f"{uuid.uuid4()}"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)

        ydl_opts = {
            'outtmpl': output_path,
            'quiet': True,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'cookiefile': 'cookies.txt',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            },
            'nocheckcertificate': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3_path = output_path + ".mp3"

        if os.path.exists(mp3_path):
            await message.reply_document(document=open(mp3_path, 'rb'), filename="audio.mp3")
            os.remove(mp3_path)
        else:
            await message.reply_text("❌ لم يتم العثور على ملف الصوت بعد التحويل.")

    except Exception as e:
        await message.reply_text(f"❌ فشل التحميل: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n👤 عدد المستخدمين: {len(user_ids)}\n📥 عدد الطلبات: {request_count}"
    )

async def download_mp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗️ استخدم الأمر:\n/mp3 <رابط>")
        return
    url = context.args[0]
    await download_mp3(update.message, url)

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("mp3", download_mp3_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
