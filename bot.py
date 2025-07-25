import os
import uuid
import asyncio
import nest_asyncio
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import yt_dlp
import csv

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
save_cookie_file("cookies_fb.txt", "FB_COOKIES")

def get_cookie_file_for_url(url: str) -> str:
    if "facebook.com" in url or "fb.watch" in url:
        return "cookies_fb.txt"
    elif "instagram.com" in url:
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

🔹 يدعم تحميل الفيديو والصوت من YouTube وInstagram وTikTok وFacebook.

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
        filename = str(uuid.uuid4())
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        def get_ydl_opts(q):
            return {
                'format': q,
                'outtmpl': output_path + ".%(ext)s",
                'quiet': True,
                'nocheckcertificate': True,
                'cookiefile': cookie_file,
                'http_headers': {'User-Agent': 'Mozilla/5.0'}
            }

        with yt_dlp.YoutubeDL(get_ydl_opts(quality)) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                await message.reply_text("❌ لم يتم تحميل معلومات الفيديو.")
                return

            downloaded_file = ydl.prepare_filename(info)

        if not downloaded_file or not os.path.isfile(downloaded_file):
            await message.reply_text("❌ لم يتم العثور على ملف الفيديو بعد التحميل.")
            return

        if os.path.getsize(downloaded_file) > 50 * 1024 * 1024 and quality != "worst":
            os.remove(downloaded_file)
            await message.reply_text("⚠️ الحجم كبير، سيتم التحميل بجودة أقل...")
            await download_video(message, url, "worst", context)
            return

        if os.path.getsize(downloaded_file) > 50 * 1024 * 1024:
            await message.reply_text("❌ حتى بعد تقليل الجودة، الملف أكبر من 50MB.")
            os.remove(downloaded_file)
            return

        with open(downloaded_file, 'rb') as video_file:
            await message.reply_video(video=video_file)

        await asyncio.sleep(5)
        await message.delete()
        os.remove(downloaded_file)

    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء تحميل الفيديو:\n{e}")

async def download_mp3(message, url, quality, context):
    try:
        filename = str(uuid.uuid4())
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        def get_ydl_opts(q):
            return {
                'format': 'bestaudio/best',
                'outtmpl': output_path + ".%(ext)s",
                'quiet': True,
                'nocheckcertificate': True,
                'cookiefile': cookie_file,
                'http_headers': {'User-Agent': 'Mozilla/5.0'},
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': q
                }]
            }

        with yt_dlp.YoutubeDL(get_ydl_opts(quality)) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                await message.reply_text("❌ لم يتم تحميل معلومات الصوت.")
                return

            mp3_file = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')

        if not os.path.exists(mp3_file):
            await message.reply_text("❌ لم يتم العثور على ملف الصوت بعد التحويل.")
            return

        if os.path.getsize(mp3_file) > 50 * 1024 * 1024 and quality != "64":
            os.remove(mp3_file)
            await message.reply_text("⚠️ الملف كبير، سيتم التحويل إلى جودة أقل...")
            await download_mp3(message, url, "64", context)
            return

        if os.path.getsize(mp3_file) > 50 * 1024 * 1024:
            await message.reply_text("❌ حتى بعد تقليل الجودة، الملف الصوتي أكبر من 50MB.")
            os.remove(mp3_file)
            return

        await message.reply_document(document=open(mp3_file, 'rb'), filename="audio.mp3")
        await asyncio.sleep(5)
        await message.delete()
        os.remove(mp3_file)

    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء تحميل الصوت:\n{e}")

# ✅ /stats: فقط عدد المستخدمين + زر تصدير CSV
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 تحميل المستخدمين CSV", callback_data="export_users_csv")]
    ])

    await update.message.reply_text(
        f"📊 الإحصائيات:\n\n👤 عدد المستخدمين: {len(user_ids)}",
        reply_markup=keyboard
    )

# ✅ تصدير ملف CSV عند الضغط
async def export_users_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    filename = os.path.join(DOWNLOAD_FOLDER, "users.csv")
    with open(filename, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["User ID"])
        for uid in user_ids:
            writer.writerow([uid])

    await query.message.reply_document(document=InputFile(filename), filename="users.csv")
    os.remove(filename)

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
    app.add_handler(CallbackQueryHandler(export_users_csv, pattern="^export_users_csv$"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
