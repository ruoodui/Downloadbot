import os
import uuid
import asyncio
import subprocess
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

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def write_cookie_file(filename: str, content: str):
    if content:
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"Failed to write {filename}: {e}")

write_cookie_file("cookies_yt.txt", os.getenv("YT_COOKIES", ""))
write_cookie_file("cookies_ig.txt", os.getenv("IG_COOKIES", ""))
write_cookie_file("cookies_tt.txt", os.getenv("TT_COOKIES", ""))

def get_cookie_file_for_url(url: str) -> str:
    if "instagram.com" in url or "instagr.am" in url:
        return "cookies_ig.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies_yt.txt"
    elif "tiktok.com" in url:
        return "cookies_tt.txt"
    return "cookies.txt"

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
        [InlineKeyboardButton("\ud83d\udd14 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
        [InlineKeyboardButton("\ud83d\udcf7 تابعنا على Instagram", url=f"https://instagram.com/{INSTAGRAM_USERNAME}")]
    ])
    await update.message.reply_text("\u26a0\ufe0f لا يمكنك استخدام البوت قبل الاشتراك في القناة:", reply_markup=keyboard)

async def delete_after_delay(context, message, delay=10):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_user_subscribed(user.id, context):
        await send_subscription_prompt(update)
        return

    welcome_text = f"""
\ud83d\udc4b أهلاً {user.first_name}!

\ud83d\udd39 يدعم تحميل الفيديو والصوت من YouTube، TikTok، Instagram، وغيرها.

\ud83d\udcc5 فقط أرسل رابط الفيديو وسيظهر لك خيار التحميل.
\ud83c\udfb7 استخدم /mp3 <رابط> لتحويل الفيديو إلى MP3.

\u26a0\ufe0f تأكد من حقوق المحتوى قبل الاستخدام.
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
    if url.startswith("http") and "." in url:
        context.user_data["last_url"] = url
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\ud83d\udcc5 تحميل فيديو", callback_data="video_menu")],
            [InlineKeyboardButton("\ud83c\udfb7 تحويل إلى MP3", callback_data="audio_menu")]
        ])
        msg = await update.message.reply_text("اختر نوع التحميل:", reply_markup=keyboard)
        await delete_after_delay(context, msg, delay=30)
    else:
        await update.message.reply_text("\u274c الرجاء إرسال رابط صحيح لفيديو.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    url = context.user_data.get("last_url")

    try:
        await query.message.delete()
    except:
        pass

    if action in ["video_menu", "audio_menu"]:
        context.user_data["last_action"] = action
        if action == "video_menu":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\ud83d\udfe2 جودة عالية", callback_data="video_high")],
                [InlineKeyboardButton("\ud83d\udd3b جودة منخفضة", callback_data="video_low")],
                [InlineKeyboardButton("\ud83d\udd19 رجوع", callback_data="back_main")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("\ud83d\udfe2 جودة عالية", callback_data="audio_high")],
                [InlineKeyboardButton("\ud83d\udd3b جودة منخفضة", callback_data="audio_low")],
                [InlineKeyboardButton("\ud83d\udd19 رجوع", callback_data="back_main")]
            ])
        msg = await query.message.reply_text("اختر الجودة:", reply_markup=keyboard)
        await delete_after_delay(context, msg, delay=30)
        return

    if action == "back_main":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("\ud83d\udcc5 تحميل فيديو", callback_data="video_menu")],
            [InlineKeyboardButton("\ud83c\udfb7 تحويل إلى MP3", callback_data="audio_menu")]
        ])
        msg = await query.message.reply_text("اختر نوع التحميل:", reply_markup=keyboard)
        await delete_after_delay(context, msg, delay=30)
        return

    if not url:
        await query.message.reply_text("\u274c لم يتم العثور على رابط محفوظ. أرسل الرابط مرة أخرى.")
        return

    loading_msg = await query.message.reply_text("\u23f3 جاري التحميل...")

    if action == "video_high":
        await download_best_video(loading_msg, url, context)
    elif action == "video_low":
        await download_low_quality_video(loading_msg, url, context)
    elif action == "audio_high":
        await download_mp3(loading_msg, url, context)
    elif action == "audio_low":
        await download_low_quality_audio(loading_msg, url, context)

async def download_best_video(message, url: str, context):
    try:
        filename = f"{uuid.uuid4()}.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'format': 'best',
            'outtmpl': output_path,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': cookie_file,
            'http_headers': {'User-Agent': 'Mozilla/5.0'}
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await message.reply_video(video=open(output_path, 'rb'))
        await delete_after_delay(context, message, delay=5)
        os.remove(output_path)

    except Exception as e:
        await message.reply_text(f"\u274c حدث خطأ أثناء تحميل الفيديو:\n{str(e)}")

async def download_low_quality_video(message, url: str, context):
    try:
        filename = f"{uuid.uuid4()}.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        cookie_file = get_cookie_file_for_url(url)

        ydl_opts = {
            'format': 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst',
            'outtmpl': output_path,
            'quiet': True,
            'nocheckcertificate': True,
            'cookiefile': cookie_file,
            'http_headers': {'User-Agent': 'Mozilla/5.0'}
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await message.reply_video(video=open(output_path, 'rb'))
        await delete_after_delay(context, message, delay=5)
        os.remove(output_path)

    except Exception as e:
        await message.reply_text(f"\u274c فشل تحميل النسخة منخفضة الجودة:\n{str(e)}")

async def download_mp3(message, url: str, context):
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
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
            'nocheckcertificate': True,
            'cookiefile': cookie_file
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3_path = output_path + ".mp3"
        await message.reply_document(document=open(mp3_path, 'rb'), filename="audio.mp3")
        await delete_after_delay(context, message, delay=5)
        os.remove(mp3_path)

    except Exception as e:
        await message.reply_text(f"\u274c فشل تحميل MP3:\n{str(e)}")

async def download_low_quality_audio(message, url: str, context):
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
                'preferredquality': '64',
            }],
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
            'nocheckcertificate': True,
            'cookiefile': cookie_file
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        mp3_path = output_path + ".mp3"
        await message.reply_document(document=open(mp3_path, 'rb'), filename="audio_low.mp3")
        await delete_after_delay(context, message, delay=5)
        os.remove(mp3_path)

    except Exception as e:
        await message.reply_text(f"\u274c فشل تحميل MP3 منخفض الجودة:\n{str(e)}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("\u274c هذا الأمر مخصص للمشرف فقط.")
        return

    details = "\n".join([f"• `{uid}`" for uid in list(user_ids)]) or "لا يوجد مستخدمين بعد."
    await update.message.reply_text(
        f"\ud83d\udcca إحصائيات البوت:\n\n\ud83d\udc64 عدد المستخدمين: {len(user_ids)}\n\ud83d\udcc5 عدد الطلبات: {request_count}\n\n\ud83d\udcdf المستخدمون:\n{details}",
        parse_mode="Markdown"
    )

async def download_mp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗️ استخدم الأمر:\n/mp3 <رابط>")
        return
    url = context.args[0]
    await download_mp3(update.message, url, context)

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
