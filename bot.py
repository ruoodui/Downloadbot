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

nest_asyncio.apply()
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@mitech808")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "mitech808")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def save_cookie_file(filename, env_key):
    content = os.getenv(env_key, "")
    if content:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

save_cookie_file("cookies_yt.txt", "YT_COOKIES")
save_cookie_file("cookies_ig.txt", "IG_COOKIES")
save_cookie_file("cookies_tt.txt", "TT_COOKIES")

def get_cookie_file_for_url(url: str) -> str:
    if "instagram.com" in url:
        return "cookies_ig.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies_yt.txt"
    elif "tiktok.com" in url:
        return "cookies_tt.txt"
    return ""

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

    welcome = f"""
👋 أهلاً {user.first_name}!

🔹 يدعم تحميل الفيديو والصوت من YouTube وInstagram وTikTok.

📥 فقط أرسل الرابط وسيظهر لك خيارات التحميل.
🎧 استخدم /mp3 <الرابط> لتحميل MP3.

⚠️ تأكد من حقوق المحتوى قبل الاستخدام.
"""
    await update.message.reply_text(welcome.strip(), parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    user_ids.add(user.id)
    request_count += 1

    url = update.message.text.strip()
    if url.startswith("http") and "." in url:
        context.user_data["last_url"] = url
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 تحميل فيديو", callback_data="video_menu")],
            [InlineKeyboardButton("🎧 تحويل إلى MP3", callback_data="audio_menu")]
        ])
        await update.message.reply_text("اختر نوع التحميل:", reply_markup=keyboard)
    else:
        await update.message.reply_text("❌ الرجاء إرسال رابط صحيح.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    url = context.user_data.get("last_url")

    if action in ["video_menu", "audio_menu"]:
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط محفوظ.")
            return

        context.user_data["last_action"] = action
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 جودة عالية", callback_data=f"{action}_high")],
            [InlineKeyboardButton("🔻 جودة منخفضة", callback_data=f"{action}_low")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
        ])
        await query.message.edit_text("اختر الجودة:", reply_markup=keyboard)
        return

    if action == "back":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 تحميل فيديو", callback_data="video_menu")],
            [InlineKeyboardButton("🎧 تحويل إلى MP3", callback_data="audio_menu")]
        ])
        await query.message.edit_text("اختر نوع التحميل:", reply_markup=keyboard)
        return

    if not url:
        await query.message.reply_text("❌ لم يتم العثور على رابط محفوظ.")
        return

    loading_msg = await query.message.reply_text("⏳ جاري التحميل...")

    if action == "video_menu_high":
        await download_video(loading_msg, url, "best", context)
    elif action == "video_menu_low":
        await download_video(loading_msg, url, "worst", context)
    elif action == "audio_menu_high":
        await download_mp3(loading_msg, url, "192", context)
    elif action == "audio_menu_low":
        await download_mp3(loading_msg, url, "64", context)

async def download_video(message, url, quality, context):
    try:
        filename = f"{uuid.uuid4()}.mp4"
        output = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'format': quality,
            'outtmpl': output,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': cookie_file,
            'http_headers': {'User-Agent': 'Mozilla/5.0'}
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await message.reply_video(video=open(output, 'rb'))
        await asyncio.sleep(5)
        await message.delete()
        os.remove(output)

    except Exception as e:
        await message.reply_text(f"❌ خطأ في تحميل الفيديو:\n{e}")

async def download_mp3(message, url, quality, context):
    try:
        filename = f"{uuid.uuid4()}"
        output = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': cookie_file,
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality
            }]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3_path = output + ".mp3"
        await message.reply_document(document=open(mp3_path, 'rb'), filename="audio.mp3")
        await asyncio.sleep(5)
        await message.delete()
        os.remove(mp3_path)

    except Exception as e:
        await message.reply_text(f"❌ خطأ في تحميل الصوت:\n{e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return
    users = "\n".join([f"• {u}" for u in user_ids]) or "لا يوجد."
    await update.message.reply_text(
        f"📊 إحصائيات:\n👤 المستخدمين: {len(user_ids)}\n📥 الطلبات: {request_count}\n\n{users}",
        parse_mode="Markdown"
    )

async def download_mp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗️ استخدم:\n/mp3 <الرابط>")
        return
    url = context.args[0]
    await download_mp3(update.message, url, "192", context)

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
