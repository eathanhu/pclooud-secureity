import os
import re
import time
import asyncio
import base64
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================================================
# CONFIG
# =====================================================

BOT_TOKEN = "1819045933:AAFuBQpfqmxAMyjYqF3j6JdNOUjBOAltcuo"

PCLOUD_EMAIL = "jejit57404@itquoted.com"
PCLOUD_PASSWORD = "Th@#Guy401"

FOLDER_NAME = "yasir"

# =====================================================
# PCLOUD API
# pCloud has 2 data centers: US (api) and EU (eapi)
# Auth via userinfo?getauth=1 (NOT a /getauth endpoint)
# =====================================================

PCLOUD_API = "https://api.pcloud.com"
auth_token = None


def get_auth():
    """Authenticate with pCloud.
    Tries both US and EU data centers."""
    global auth_token, PCLOUD_API

    for host in ["https://api.pcloud.com", "https://eapi.pcloud.com"]:
        try:
            r = requests.get(
                f"{host}/userinfo",
                params={
                    "getauth": 1,
                    "username": PCLOUD_EMAIL,
                    "password": PCLOUD_PASSWORD,
                },
            )
            data = r.json()
            print(f"pCloud userinfo response ({host}): {data}")

            if data.get("result") == 0 and data.get("auth"):
                auth_token = data["auth"]
                PCLOUD_API = host
                print(f"pCloud auth OK ({host})")
                return auth_token

            print(f"pCloud auth failed ({host}): {data}")

        except Exception as e:
            print(f"pCloud auth error ({host}): {e}")

    return None


get_auth()

# =====================================================
# WEBDAV HELPERS
# =====================================================


def webdav_auth_header():
    creds = base64.b64encode(
        f"{PCLOUD_EMAIL}:{PCLOUD_PASSWORD}".encode()
    ).decode()
    return {"Authorization": f"Basic {creds}"}


def create_pcloud_folder(path):
    url = f"https://webdav.pcloud.com{path}"
    r = requests.request("MKCOL", url, headers=webdav_auth_header())
    return r.status_code in [200, 201, 405]


create_pcloud_folder(f"/{FOLDER_NAME}")

# =====================================================
# HELPERS
# =====================================================


def humanbytes(size):
    if not size:
        return "0 B"
    power = 1024
    n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    while size > power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {units[n]}"


def progress_bar(percent):
    filled = int(percent / 100 * 12)
    return "⬢" * filled + "⬡" * (12 - filled)


def is_url(text):
    return bool(re.match(r"https?://", text))


# =====================================================
# DDL GENERATOR (getfilepublink + auth token)
# =====================================================


def get_ddl(filepath):
    global auth_token, PCLOUD_API

    if not auth_token:
        get_auth()
    if not auth_token:
        return "Auth failed"

    for attempt in range(2):
        try:
            r = requests.get(
                f"{PCLOUD_API}/getfilepublink",
                params={"auth": auth_token, "path": filepath},
            )
            data = r.json()

            if data.get("result") == 0:
                host = data["hosts"][0]
                path = data["path"]
                return f"https://{host}{path}"

            if data.get("result") in [1000, 2000, 2009] and attempt == 0:
                get_auth()
                continue

            return f"DDL Error: {data.get('error', data)}"

        except Exception as e:
            return str(e)

    return "DDL generation failed"


# =====================================================
# URL TO PCLOUD (savefileto)
# =====================================================


def save_url(url):
    global auth_token

    if not auth_token:
        get_auth()
    if not auth_token:
        return {"result": -1, "error": "Auth failed"}

    try:
        r = requests.get(
            f"{PCLOUD_API}/savefileto",
            params={
                "auth": auth_token,
                "url": url,
                "path": f"/{FOLDER_NAME}",
            },
        )
        return r.json()
    except Exception as e:
        return {"result": -1, "error": str(e)}


# =====================================================
# UPLOAD WITH REAL PROGRESS
# =====================================================


class UploadState:
    def __init__(self):
        self.uploaded = 0
        self.total = 0
        self.done = False


async def progress_watcher(state, msg, filename, username):
    while not state.done:
        if state.total > 0 and state.uploaded > 0:
            pct = state.uploaded * 100 / state.total
            elapsed = getattr(state, "_start", 0)
            speed = state.uploaded / (time.time() - elapsed) if elapsed else 0
            try:
                await msg.edit_text(
                    f"📄 {filename}\n"
                    f"Task By: {username}\n\n"
                    f"⬆️ Uploading to pCloud...\n"
                    f"{progress_bar(pct)} {pct:.1f}%\n"
                    f"Processed → {humanbytes(state.uploaded)} of {humanbytes(state.total)}\n"
                    f"Speed → {humanbytes(speed)}/s"
                )
            except:
                pass
        await asyncio.sleep(3)


def upload_to_pcloud(local_path, remote_path, state):
    url = f"https://webdav.pcloud.com{remote_path}"
    headers = webdav_auth_header()

    chunk_size = 1024 * 1024

    def file_generator():
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                state.uploaded += len(chunk)
                yield chunk

    r = requests.put(url, headers=headers, data=file_generator())
    state.done = True
    return r.status_code in [200, 201, 204]


# =====================================================
# HANDLE TEXT / URL
# =====================================================


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not is_url(text):
        return

    msg = await update.message.reply_text("🌐 Sending URL to pCloud...")

    result = await asyncio.to_thread(save_url, text)

    if result.get("result") == 0:
        metadata = result.get("metadata", [])
        if metadata and isinstance(metadata, list):
            file_data = metadata[0]
            filepath = file_data.get("path", "")
            filename = file_data.get("name", "file")
            size = file_data.get("size", 0)

            ddl = await asyncio.to_thread(get_ddl, filepath)

            await msg.edit_text(
                f"✅ URL Uploaded to pCloud\n\n"
                f"📄 {filename}\n"
                f"📦 {humanbytes(size)}\n\n"
                f"📥 Source:\n{text}\n\n"
                f"🌍 DDL Link:\n{ddl}"
            )
        else:
            await msg.edit_text(f"✅ URL sent to pCloud\n\nResult: {result}")
    else:
        await msg.edit_text(
            f"❌ Failed\n\nError: {result.get('error', result)}"
        )


# =====================================================
# HANDLE MEDIA
# =====================================================


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    telegram_file = None
    filename = "file"
    filesize = 0

    if message.document:
        telegram_file = await message.document.get_file()
        filename = message.document.file_name or message.document.file_unique_id
        filesize = message.document.file_size

    elif message.video:
        telegram_file = await message.video.get_file()
        filename = f"{message.video.file_unique_id}.mp4"
        filesize = message.video.file_size

    elif message.audio:
        telegram_file = await message.audio.get_file()
        filename = message.audio.file_name or f"{message.audio.file_unique_id}.mp3"
        filesize = message.audio.file_size

    elif message.photo:
        telegram_file = await message.photo[-1].get_file()
        filename = f"{message.photo[-1].file_unique_id}.jpg"
        filesize = message.photo[-1].file_size

    else:
        return

    username = message.from_user.first_name
    local_path = f"./{filename}"

    progress_message = await message.reply_text("🚀 Starting download...")

    # ─── DOWNLOAD FROM TELEGRAM ─────────────────────

    start = time.time()
    await telegram_file.download_to_drive(local_path)
    elapsed = time.time() - start
    speed = filesize / elapsed if elapsed > 0 else 0

    await progress_message.edit_text(
        f"📄 {filename}\n"
        f"Task By: {username}\n\n"
        f"✅ Download Complete\n"
        f"📦 {humanbytes(filesize)} → {humanbytes(speed)}/s"
    )

    # ─── UPLOAD TO PCLOUD ───────────────────────────

    state = UploadState()
    state.total = filesize
    state._start = time.time()

    watcher = asyncio.create_task(
        progress_watcher(state, progress_message, filename, username)
    )

    ok = await asyncio.to_thread(
        upload_to_pcloud, local_path, f"/{FOLDER_NAME}/{filename}", state
    )

    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass

    os.remove(local_path)

    if not ok:
        await progress_message.edit_text("❌ Upload to pCloud failed")
        return

    # ─── GENERATE DDL ───────────────────────────────

    filepath = f"/{FOLDER_NAME}/{filename}"
    ddl = await asyncio.to_thread(get_ddl, filepath)

    safe_name = filename.replace(" ", "%20")
    stream = f"https://webdav.pcloud.com/{FOLDER_NAME}/{safe_name}"

    # ─── FINAL MESSAGE ──────────────────────────────

    upload_time = time.time() - state._start
    upload_speed = filesize / upload_time if upload_time > 0 else 0

    await progress_message.edit_text(
        f"✅ Upload Complete\n\n"
        f"📄 {filename}\n"
        f"📦 {humanbytes(filesize)}\n"
        f"🚀 {humanbytes(upload_speed)}/s\n\n"
        f"🌍 DDL Link:\n{ddl}\n\n"
        f"⚡ Stream Link:\n{stream}"
    )


# =====================================================
# START BOT
# =====================================================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO,
        handle_media,
    )
)

app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
)

print("✅ Bot Started...")

app.run_polling()
