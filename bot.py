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

# أقصى حجم للملفات (50 ميجابايت)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 ميجابايت

# تحميل الكوكيز من متغيرات البيئة
yt_cookies_content = os.getenv("YT_COOKIES", "")
if yt_cookies_content:
    with open("cookies_yt.txt", "w", encoding="utf-8") as f:
        f.write(yt_cookies_content)

ig_cookies_content = os.getenv("IG_COOKIES", "")
if ig_cookies_content:
    with open("cookies_ig.txt", "w", encoding="utf-8") as f:
        f.write(ig_cookies_content)

tt_cookies_content = os.getenv("TT_COOKIES", "")
if tt_cookies_content:
    with open("cookies_tt.txt", "w", encoding="utf-8") as f:
        f.write(tt_cookies_content)

def get_cookie_file_for_url(url: str) -> str:
    if "instagram.com" in url or "instagr.am" in url:
        return "cookies_ig.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies_yt.txt"
    elif "tiktok.com" in url:
        return "cookies_tt.txt"
    return "cookies.txt"  # fallback

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

📥 فقط أرسل رابط الفيديو وسيظهر لك خيارات التحميل.
🎧 استخدم /mp3 <رابط> لتحويل الفيديو إلى MP3 مباشرة.

⚠️ تأكد من حقوق المحتوى قبل الاستخدام.
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    url = update.message.text.strip()
    if not (any(site in url for site in ["http://", "https://"]) and "." in url):
        await update.message.reply_text("❌ الرجاء إرسال رابط صحيح لفيديو.")
        return

    context.user_data["last_url"] = url

    cookie_file = get_cookie_file_for_url(url)
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'cookiefile': cookie_file,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ عند جلب جودات الفيديو:\n{e}")
        return

    # جلب جودات فيديو تحتوي صوت وفيديو (مدمجة)
    video_formats = []
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
            height = f.get('height')
            if height:
                video_formats.append((int(height), f['format_id']))

    if not video_formats:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎧 تحميل صوت MP3", callback_data="audio")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")]
        ])
        await update.message.reply_text("لم نتمكن من جلب جودات الفيديو، اختر:", reply_markup=keyboard)
        return

    video_formats.sort(key=lambda x: x[0])  # تصاعدي حسب الجودة (الارتفاع)

    context.user_data["video_formats"] = video_formats  # تخزين الجودات لاستخدامها لاحقًا

    buttons = [
        [InlineKeyboardButton("▶️ تحميل فيديو", callback_data="download_video_menu")],
        [InlineKeyboardButton("🎧 تحميل صوت MP3", callback_data="audio")],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")]
    ]

    await update.message.reply_text(
        "اختر طريقة التحميل:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    url = context.user_data.get("last_url")
    video_formats = context.user_data.get("video_formats", [])

    if data == "cancel":
        await query.edit_message_text("تم إلغاء العملية.")
        return

    if data == "audio":
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط محفوظ. أرسل الرابط مرة أخرى.")
            return
        await query.edit_message_text("⏳ جاري تحميل وتحويل الصوت...")
        await download_mp3(query.message, url)
        return

    if data == "download_video_menu":
        if not video_formats:
            await query.edit_message_text("❌ لا توجد معلومات جودة لتحميل الفيديو.")
            return

        video_formats.sort(key=lambda x: x[0])  # تصاعدي حسب الجودة

        highest_quality = video_formats[-1][1]  # أعلى جودة
        lowest_quality = video_formats[0][1]    # أقل جودة

        buttons = [
            [InlineKeyboardButton("📺 جودة عالية", callback_data=f"quality_{highest_quality}")],
            [InlineKeyboardButton("📺 جودة منخفضة", callback_data=f"quality_{lowest_quality}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main_menu")]
        ]
        await query.edit_message_text(
            "اختر جودة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data == "back_to_main_menu":
        buttons = [
            [InlineKeyboardButton("▶️ تحميل فيديو", callback_data="download_video_menu")],
            [InlineKeyboardButton("🎧 تحميل صوت MP3", callback_data="audio")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="cancel")]
        ]
        await query.edit_message_text(
            "اختر طريقة التحميل:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("quality_"):
        if not url:
            await query.message.reply_text("❌ لم يتم العثور على رابط محفوظ. أرسل الرابط مرة أخرى.")
            return
        format_id = data[len("quality_"):]
        await query.edit_message_text(f"⏳ جاري تحميل الفيديو بالجودة {format_id}...")
        await download_video_by_format(query.message, url, format_id)
        return

async def download_video_by_format(message, url: str, format_id: str):
    try:
        filename = f"{uuid.uuid4()}.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'format': format_id,
            'outtmpl': output_path,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': cookie_file,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        file_size = os.path.getsize(output_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(output_path)
            await message.reply_text(f"❌ حجم الفيديو كبير جداً ({file_size / (1024*1024):.2f} ميجابايت) ولا يمكن تحميله.")
            return

        await message.reply_video(video=open(output_path, 'rb'))

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع لاختيار جودة أخرى", callback_data="download_video_menu")]
        ])
        await message.reply_text("يمكنك اختيار تحميل آخر:", reply_markup=keyboard)

        os.remove(output_path)

    except Exception as e:
        await message.reply_text(f"❌ حدث خطأ أثناء تحميل الفيديو:\n{e}")

async def download_mp3(message, url: str):
    try:
        filename = f"{uuid.uuid4()}"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'outtmpl': output_path,
            'quiet': True,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0'
            },
            'nocheckcertificate': True,
            'cookiefile': cookie_file
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3_path = output_path + ".mp3"
        if not os.path.exists(mp3_path):
            await message.reply_text("❌ لم يتم العثور على ملف الصوت بعد التحويل.")
            return

        file_size = os.path.getsize(mp3_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(mp3_path)
            await message.reply_text(f"❌ حجم ملف الصوت كبير جداً ({file_size / (1024*1024):.2f} ميجابايت) ولا يمكن تحميله.")
            return

        await message.reply_document(document=open(mp3_path, 'rb'), filename="audio.mp3")
        os.remove(mp3_path)

    except Exception as e:
        await message.reply_text(f"❌ فشل تحميل الصوت:\n{e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    details = "\n".join([f"• `{uid}`" for uid in list(user_ids)]) or "لا يوجد مستخدمين بعد."
    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n👤 عدد المستخدمين: {len(user_ids)}\n📥 عدد الطلبات: {request_count}\n\n🧾 المستخدمون:\n{details}",
        parse_mode="Markdown"
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
