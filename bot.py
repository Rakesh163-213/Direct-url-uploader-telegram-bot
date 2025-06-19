from flask import Flask
from threading import Thread  # ✅ Add this line

# == Flask App ==
app = Flask(__name__)

@app.route('/')
def home():
    return '✅ Flask is running! Bot should be running too.'

def run_flask():
    app.run(host='0.0.0.0', port=8000)

# Start Flask in a separate thread
flask_thread = Thread(target=run_flask)
flask_thread.start()
import asyncio
#from config import API_ID,API_HASH,BOT_TOKEN
import os
import time
import requests
import humanize
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from http.client import IncompleteRead
async def delete_after_delay(msg, delay):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass
# Bot credentials
API_ID = int(os.getenv(API_ID)  # Replace with your actual API ID
API_HASH = os.getenv(API_HASH)
BOT_TOKEN = os.getenv(BOT_TOKEN)

app = Client("downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Session storage
user_data = {}

# Helpers
def readable_size(size):
    return humanize.naturalsize(size, binary=True)

def draw_progress_bar(percentage):
    full = int(percentage // 5)
    empty = 20 - full
    return "▓" * full + "░" * empty

def get_file_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, stream=True, headers=headers, timeout=15)
        size = int(r.headers.get("Content-Length", 0))
        cd = r.headers.get("Content-Disposition", "")
        name = cd.split("filename=")[-1].replace('"', '').strip() if "filename=" in cd else url.split("/")[-1].split("?")[0]
        if not "." in name:
            name += ".mp4"
        r.close()
        return name, size
    except Exception:
        return None, None

async def download_with_resume(url, filename, headers, status_msg, total_size):
    downloaded = 0
    start_time = time.time()
    last_update = start_time

    with open(filename, "wb") as f:
        try:
            r = requests.get(url, stream=True, headers=headers, timeout=30)
            for chunk in r.iter_content(chunk_size=1024 * 1024 * 2):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    elapsed = max(now - last_update, 0.001)
                    speed = len(chunk) / elapsed
                    percent = downloaded * 100 / total_size if total_size else 0
                    eta = (total_size - downloaded) / speed if speed > 0 else 0
                    bar = draw_progress_bar(percent)

                    try:
                        await status_msg.edit_text(
                            f"📅 **Downloading Progress**\n\n"
                            f"{bar}\n"
                            f"**Percentage:** `{percent:.2f}%`\n"
                            f"**Completed:** `{humanize.naturalsize(downloaded)}` / `{humanize.naturalsize(total_size)}`\n"
                            f"**Speed:** `{humanize.naturalsize(speed)}/s`\n"
                            f"**ETA:** `{humanize.naturaldelta(eta)}`"
                        )
                    except MessageNotModified:
                        pass

                    last_update = now
            r.close()
        except IncompleteRead:
            raise Exception("Download was interrupted. Try again.")

@app.on_message(filters.private & filters.text & filters.incoming)
async def handle_all_messages(client, message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id in user_data and user_data[user_id].get("rename"):
        new_name = text
        old_name = user_data[user_id]["file_name"]
        ext = os.path.splitext(old_name)[1] or ".mp4"
        user_data[user_id]["file_name"] = f"{new_name}{ext}"
        user_data[user_id]["rename"] = False
        confirmation_msg = await message.reply("✅ Renamed successfully. Uploading...")
        await asyncio.sleep(2)  # short delay so user sees it
        await confirmation_msg.delete()
        return await upload_file(client, message, user_id, rename=True)

    if not text.startswith("http"):
        return await message.reply("❌ Please send a valid direct URL.")

    file_name, file_size = get_file_info(text)
    if not file_name or file_size == 0:
        return await message.reply("❌ Failed to fetch file info. The link may not be direct or the server blocked it.")

    user_data[user_id] = {
        "url": text,
        "file_name": file_name,
        "file_size": file_size,
        "rename": False,
        "status_msg": None  # will be updated later
    }

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Rename", callback_data="rename"),
            InlineKeyboardButton("📁 Default", callback_data="default")
        ]
    ])

    msg = await message.reply(
        f"📄 **File Name:** `{file_name}`\n📦 **Size:** {readable_size(file_size)}",
        reply_markup=buttons
    )
    asyncio.create_task(delete_after_delay(msg, 19))  # ⏱️ Clean-up in 19 sec

@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if user_id not in user_data:
        return await callback_query.message.edit_text("❌ Session expired. Please send the link again.")

    await callback_query.message.edit_reply_markup(reply_markup=None)

    if data == "rename":
        user_data[user_id]["rename"] = True
        msg = await callback_query.message.reply("✍️ Send the new file name (without extension):")
        asyncio.create_task(delete_after_delay(msg, 10))
        return
    if data == "default":
        await callback_query.message.edit_text("⬇️ Uploading file...")
        return await upload_file(client, callback_query.message, user_id, rename=False)

async def upload_file(client, message, user_id, rename):
    try:
        info = user_data.get(user_id)
        url = info["url"]
        filename = info["file_name"]
        path = f"./{filename}"
        headers = {"User-Agent": "Mozilla/5.0"}

        total_size = int(user_data[user_id].get("file_size", 0))
        if total_size == 0:
            raise Exception("File size is zero or unknown (from earlier fetch).")
        status_msg = user_data[user_id].get("status_msg")

        if not status_msg:
            status_msg = await message.reply("📥 Starting download...")
            user_data[user_id]["status_msg"] = status_msg
        else:
            await status_msg.edit_text("📥 Starting download...")

        await download_with_resume(url, path, headers, status_msg, total_size)

        await status_msg.edit_text("📤 Starting upload...")
        upload_start_time = time.time()
        
        async def progress(current, total):
            now = time.time()
            elapsed = max(now - upload_start_time, 0.001)
            speed = current / elapsed
            percent = current * 100 / total if total else 0
            eta = (total - current) / speed if speed > 0 else 0
            bar = draw_progress_bar(percent)

            try:
                await status_msg.edit_text(
                    f"📤 **Uploading Progress**\n\n"
                    f"{bar}\n"
                    f"**Percentage:** `{percent:.2f}%`\n"
                    f"**Uploaded:** `{humanize.naturalsize(current)}` / `{humanize.naturalsize(total)}`\n"
                    f"**Speed:** `{humanize.naturalsize(speed)}/s`\n"
                    f"**ETA:** `{humanize.naturaldelta(eta)}`"
                )
            except MessageNotModified:
                pass

        await client.send_document(
            chat_id=message.chat.id,
            document=path,
            caption=f"✅ Uploaded as `{filename}`",
            progress=progress
        )

        os.remove(path)

    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    finally:
        try:
            status_msg = user_data.get(user_id, {}).get("status_msg")
            if status_msg:
                await status_msg.delete()
        except:
            pass
        user_data.pop(user_id, None)
print("starting")
app.run()
