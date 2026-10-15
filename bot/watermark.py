# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from datetime import datetime as dt
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys, shlex, json
from pathlib import Path
from pyrogram import Client, filters #InputFile
from pyrogram.types import Message, InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from bot.helper_funcs.media_caption import enhance_media_caption
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from mimetypes import guess_type
from bot.config import Config
from PIL import Image
import aiofiles, tempfile
import mimetypes

from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.helper_funcs.display_progress import *
from bot.helper_funcs.split_uploader import smart_split_and_upload
from bot.plugins.incoming_message_fn import (
    incoming_start_message_f,
    incoming_compress_message_f,
    incoming_cancel_message_f
)
from bot.plugins.status_message_fn import (
    eval_message_f,
    exec_message_f,
    upload_log_file
)
from bot.fsub import *
from bot.localisation import Localisation
from bot.premium import *
from bot.plugins.call_back_button_handler import button
from contextlib import nullcontext
from bot.task_manager import (
    task_manager,
    build_dedupe_key,
    PHASE_QUEUED,
    PHASE_DOWNLOADING,
    PHASE_PROCESSING,
    PHASE_UPLOADING,
)
from bot.group_status import announce_task, make_manager_progress, UploadSink


watermark_queue = []


# /setwatermark command
@app.on_message(filters.command(["setwatermark", f"setwatermark@{BOT_USERNAME}"]))
async def set_watermark_handler(client: Client, message: Message):
    reply = message.reply_to_message
    user_id = message.from_user.id

    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
   
    is_premium = await is_premium_user(user_id)
    #  Check Force Subscription
    if not await is_subscribed(app, message.from_user.id):
        #await temp.delete()
        return await not_joined(app, message)

    verify_status = await db.get_verify_status(message.from_user.id)
    VERIFY_EXPIRE = await db.get_verified_time()

    SHORT_URL_1 = await db.get_shortener_url1()
    SHORT_API_1 = await db.get_shortener_api1()
    SHORT_URL_2 = await db.get_shortener_url2()
    SHORT_API_2 = await db.get_shortener_api2()

    if (SHORT_API_1 and SHORT_URL_1) or (SHORT_API_2 and SHORT_URL_2):

        if (
            verify_status['is_verified'] and
            VERIFY_EXPIRE is not None and
            VERIFY_EXPIRE < (time.time() - verify_status['verified_time'])
        ):
            await db.update_verify_status(message.from_user.id, is_verified=False)
            verify_status = await db.get_verify_status(message.from_user.id)

        if not is_premium and not verify_status['is_verified']:
            return await short_url(app, message)

    if not reply:
        return await message.reply(
            "⚠️ Reply with an **image** (photo/document) or a valid **image URL** to set watermark."
        )

    # --- Case 1: Image sent as document ---
    if reply.document and reply.document.mime_type and reply.document.mime_type.startswith("image/"):
        await db.set_watermark(user_id, reply.document.file_id)
        return await message.reply("✅ Watermark saved successfully.")

    # --- Case 2: Image sent as photo (compressed) ---
    elif reply.photo:
        tmp_path = f"/tmp/watermark_{user_id}.jpg"
        await client.download_media(reply.photo.file_id, file_name=tmp_path)

        sent = await message.reply_document(tmp_path, caption="Watermark Uploaded ✅")
        file_id = sent.document.file_id

        await db.set_watermark(user_id, file_id)
        os.remove(tmp_path)
        return await message.reply("✅ Watermark saved successfully.")

    # --- Case 3: Image URL ---
    elif reply.text and reply.text.lower().startswith(("http://", "https://")):
        url = reply.text.strip()
        ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        tmp_path = f"/tmp/url_watermark_{user_id}{ext}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await message.reply("❌ Failed to download image from URL.")
                    with open(tmp_path, "wb") as f:
                        f.write(await resp.read())

            sent = await message.reply_document(tmp_path, caption="Watermark Uploaded ✅")
            file_id = sent.document.file_id

            await db.set_watermark(user_id, file_id)
            os.remove(tmp_path)
            return await message.reply("✅ Watermark saved successfully.")

        except Exception as e:
            return await message.reply(f"❌ Error downloading image:\n<code>{e}</code>")

    # --- No valid input ---
    return await message.reply(
        "⚠️ Reply with an **image** (photo/document) or a valid **image URL** to set watermark."
    )

@app.on_message(filters.command(["getwatermark", f"getwatermark@{BOT_USERNAME}"]))
async def get_watermark_handler(client: Client, message: Message):
    user_id = message.from_user.id
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    watermark = await db.get_watermark(user_id)

    if not watermark:
        return await message.reply("⚠️ Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ sᴀᴠᴇᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ.")

    # Case 1: Telegram file_id (most common)
    try:
        return await message.reply_document(
            watermark,
            caption="🖼️ Tʜɪs ɪs ʏᴏᴜʀ sᴀᴠᴇᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ɪᴍᴀɢᴇ."
        )
    except Exception:
        pass  # not a file_id, maybe a local file or URL

    # Case 2: Local file exists
    if os.path.exists(watermark):
        return await message.reply_document(
            watermark,
            caption="🖼️ Tʜɪs ɪs ʏᴏᴜʀ sᴀᴠᴇᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ɪᴍᴀɢᴇ."
        )

    # Case 3: URL → download and send
    if watermark.startswith("http://") or watermark.startswith("https://"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(watermark) as resp:
                    if resp.status != 200:
                        return await message.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ғʀᴏᴍ ᴛʜᴇ ᴜʀʟ.")

                    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tmp_file.write(await resp.read())
                    tmp_file.close()

            await message.reply_document(
                tmp_file.name,
                caption="🖼️ Tʜɪs ɪs ʏᴏᴜʀ sᴀᴠᴇᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ (ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ ғʀᴏᴍ ᴜʀʟ)."
            )

            os.unlink(tmp_file.name)
            return
        except Exception as e:
            return await message.reply(f"❌ Eʀʀᴏʀ ᴡʜɪʟᴇ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ:\n<code>{str(e)}</code>")

    return await message.reply("⚠️ Sᴀᴠᴇᴅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ɪs ɴᴇɪᴛʜᴇʀ ᴀ ғɪʟᴇ, ғɪʟᴇ_ɪᴅ ɴᴏʀ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ.")

# /delwatermark command
@app.on_message(filters.command(["delwatermark", f"delwatermark@{BOT_USERNAME}"]))
async def del_watermark_handler(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    path = await db.get_watermark(message.from_user.id)
    if path and os.path.exists(path):
        os.remove(path)
    await db.del_watermark(message.from_user.id)
    await message.reply("🗑️ Wᴀᴛᴇʀᴍᴀʀᴋ ᴅᴇʟᴇᴛᴇᴅ.")

# /addwatermark command
@app.on_message(filters.command(["addwatermark", f"addwatermark@{BOT_USERNAME}"]))
async def add_watermark_cmd(client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)   
    user_id = message.from_user.id
    is_premium = await is_premium_user(user_id)
    #  Check Force Subscription
    if not await is_subscribed(app, message.from_user.id):
        #await temp.delete()
        return await not_joined(app, message)

    verify_status = await db.get_verify_status(message.from_user.id)
    VERIFY_EXPIRE = await db.get_verified_time()

    SHORT_URL_1 = await db.get_shortener_url1()
    SHORT_API_1 = await db.get_shortener_api1()
    SHORT_URL_2 = await db.get_shortener_url2()
    SHORT_API_2 = await db.get_shortener_api2()

    if (SHORT_API_1 and SHORT_URL_1) or (SHORT_API_2 and SHORT_URL_2):

        if (
            verify_status['is_verified'] and
            VERIFY_EXPIRE is not None and
            VERIFY_EXPIRE < (time.time() - verify_status['verified_time'])
        ):
            await db.update_verify_status(message.from_user.id, is_verified=False)
            verify_status = await db.get_verify_status(message.from_user.id)

        if not is_premium and not verify_status['is_verified']:
            return await short_url(app, message)

    if not message.reply_to_message:
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ғɪʟᴇ ᴛᴏ ᴡᴀᴛᴇʀᴍᴀʀᴋ.")

    replied = message.reply_to_message
    media = replied.video or replied.document
    if not media:
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ ғɪʟᴇ.")

    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "watermark", title,
        build_dedupe_key(user_id, file_uid, "watermark", ""),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    from bot.group_status import announce_task
    await announce_task(message)

    watermark_queue.append((client, message, task_id))
    _ensure_runner_watermark()


async def process_watermark_task(client, message, task_id=None):
    replied = message.reply_to_message
    media = replied.video or replied.document or replied.photo
    user_id = message.from_user.id

    # Directory setup
    base_dir = os.path.join(tempfile.gettempdir(), "video-util", "watermark")
    os.makedirs(base_dir, exist_ok=True)

    input_path = None
    output_path = None
    watermark_path = None

    d_start = time.time()
    processing = None if task_id else await message.reply("⚙️ Pʀᴇᴘᴀʀɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ...")
    heavy_acquired = False

    async def _fail(txt: str):
        if processing:
            return await flood_retry(processing.edit_text, txt)
        return await message.reply(txt)

    # 1. Get watermark from DB
    wm_file_id = await db.get_watermark(user_id)
    if wm_file_id:
        try:
            wm_path = os.path.join(base_dir, f"{user_id}_wm.jpg")
            await client.download_media(wm_file_id, file_name=wm_path)
            watermark_path = wm_path
        except Exception as e:
            return await _fail(f"❌ Failed to fetch watermark from DB:\n`{e}`")

    # 2. Image URL
    elif len(message.command) >= 2 and message.command[1].startswith("http"):
        try:
            url = message.command[1]
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await _fail("❌ Failed to download watermark from URL.")
                    wm_path = os.path.join(base_dir, f"{user_id}_wm.jpg")
                    with open(wm_path, "wb") as f:
                        f.write(await resp.read())
                    watermark_path = wm_path
        except Exception as e:
            return await _fail(f"❌ Error downloading watermark:\n`{e}`")

    # 3. Replied photo
    elif message.reply_to_message.photo:
        try:
            wm_path = os.path.join(base_dir, f"{user_id}_wm.jpg")
            await client.download_media(message.reply_to_message.photo.file_id, file_name=wm_path)
            watermark_path = wm_path
        except Exception as e:
            return await _fail(f"❌ Failed to get watermark from image:\n`{e}`")

    if not watermark_path:
        return await _fail("⚠️ No watermark found. Use `/setwatermark`, or provide image URL.")

    # Input / Output setup
    original_ext = os.path.splitext(media.file_name or "file.mp4")[1]
    input_path = os.path.join(base_dir, f"{replied.id}_input{original_ext}")
    output_path = os.path.join(base_dir, f"{replied.id}_watermarked{original_ext}")
    progress_path = os.path.join(base_dir, f"{replied.id}_progress.txt")

    try:
        # Download file (download slot: released the instant file hits disk)
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            await replied.download(
                file_name=input_path,
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", processing, d_start)
            )
    except (asyncio.CancelledError, Exception) as e:
        if task_id and task_manager.is_cancelled(task_id):
            return
        return await _fail(f"❌ Failed to download media:\n`{e}`")

    if task_id and task_manager.is_cancelled(task_id):
        if processing:
            try:
                await processing.delete()
            except Exception:
                pass
        return

    if not task_id and processing:
        await flood_retry(processing.edit_text, "💧 Aᴅᴅɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ...")
    if task_id:
        # Stay "Queued" until the heavy slot is actually ours.
        await task_manager.set_phase(task_id, PHASE_QUEUED)
        await task_manager.acquire_heavy()
        if task_manager.is_cancelled(task_id):
            task_manager.release_heavy()
            if processing:
                try:
                    await processing.delete()
                except Exception:
                    pass
            return
        heavy_acquired = True
        await task_manager.set_phase(task_id, PHASE_PROCESSING)
        await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)

    # Remove old progress file
    if os.path.exists(progress_path):
        os.remove(progress_path)

    # Build ffmpeg command (new version)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i", input_path,
        "-i", watermark_path,
        "-filter_complex", "[1:v][0:v]scale2ref=w=iw:h=ih[wm][base];[base][wm]overlay=0:0",
        "-map", "0:v:0",
        "-map", "0:a?",
        "-map", "0:s?",
        "-map_metadata", "0",
        "-c:v", str(codec[0]),
        "-crf", str(int(float(crf[0]))),
        "-preset", str(preset[0]),
        "-c:a", "aac",
        "-b:a", str(audio_b[0]),
        "-c:s", "copy",
        "-progress", progress_path,
        "-nostats",
        "-loglevel", "0",
        output_path
    ]

    WM_START_TIME = time.time()
    process = await asyncio.create_subprocess_exec(*cmd)
    if task_id:
        task_manager.register_process(task_id, process)

    async def parse_progress():
        last_percent = -1
        bar_length = 12
        total_duration = get_video_duration(input_path)

        while process.returncode is None:
            if task_id and task_manager.is_cancelled(task_id):
                break
            await asyncio.sleep(2)
            if not os.path.exists(progress_path):
                continue
            try:
                with open(progress_path, 'r') as f:
                    lines = f.readlines()

                progress_data = dict(line.strip().split('=', 1) for line in lines if '=' in line)
                out_time_us = int(progress_data.get("out_time_us", "0").replace("N/A", "0"))
                out_time = out_time_us / 1_000_000

                if total_duration == 0:
                    continue

                percent = min(100, (out_time / total_duration) * 100)
                percent_display = round(percent, 2)

                filled = int(bar_length * percent / 100)
                bar = '█' * filled + '░' * (bar_length - filled)

                elapsed = time.time() - WM_START_TIME
                eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                eta_str = TimeFormatter(eta * 1000)

                progress_text = (
                    f"<blockquote><b>ᴀᴅᴅɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ</b></blockquote>\n"
                    f"<code>[{bar}]</code>\n"
                    f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                    f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                )

                if percent_display != last_percent:
                    if not task_id and processing:
                        await flood_retry(processing.edit_text, progress_text)
                    if task_id:
                        await task_manager.update_progress(
                            task_id, percent_display, eta=eta_str
                        )
                    last_percent = percent_display

                if progress_data.get("progress") == "end":
                    break
            except Exception as e:
                LOGGER.warning(f"FFmpeg progress parse error: {e}")
                continue

    try:
        await asyncio.gather(parse_progress(), process.wait())
    finally:
        # Free the heavy slot the instant encode ends (pipeline: next heavy
        # job starts while THIS task uploads).
        if task_id and heavy_acquired:
            task_manager.release_heavy()
            heavy_acquired = False

    if task_id and task_manager.is_cancelled(task_id):
        if processing:
            try:
                await processing.delete()
            except Exception:
                pass
        return

    if not os.path.exists(output_path):
        return await _fail("❌ Watermarking failed — no output file.")

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        return await _fail("⚠️ Output file size is 0B ⚠️")

    # Upload
    try:
        file_name = media.file_name or "output.mp4"
        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)
        watermarked_time = TimeFormatter((time.time() - WM_START_TIME) * 1000)

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                if not task_id and processing:
                    await flood_retry(processing.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(base_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nWatermarked: {watermarked_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        duration = get_video_duration(output_path)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(output_path, caption, media_preference)

        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=output_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=output_path)

        # Upload slot: max 1 upload, full speed, millisecond handoff.
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            await smart_split_and_upload(
                client=client,
                message=message,
                file_path=output_path,
                status_msg=(UploadSink(task_id) if task_id else processing),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=message.id,
                task_id=task_id,
            )
        # Working message served its purpose (status message is the live view)
        if processing:
            try:
                await processing.delete()
            except Exception:
                pass

    except Exception as e:
        return await _fail(f"❌ Upload failed:\n`{e}`")

    finally:
        # Cleanup
        for f in [input_path, output_path, watermark_path, progress_path]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)


_wm_worker = None

def _pop_watermark():
    if watermark_queue:
        del watermark_queue[0]


async def _pump_watermark():
    global _wm_worker
    try:
        while watermark_queue:
            while watermark_queue and task_manager.is_cancelled(watermark_queue[0][2]):
                _, _, tid = watermark_queue.pop(0)
                await task_manager.complete(tid)
            if not watermark_queue:
                break
            c, m, t = watermark_queue[0]
            try:
                await process_watermark_task(c, m, t)
            except BaseException as e:
                LOGGER.warning(f"Watermark task {t} exited: {e}")
            finally:
                await task_manager.complete(t)
                if watermark_queue and watermark_queue[0][2] == t:
                    _pop_watermark()
    finally:
        _wm_worker = None


def _ensure_runner_watermark():
    global _wm_worker
    watermark_queue[:] = [x for x in watermark_queue if not task_manager.is_cancelled(x[2])]
    if _wm_worker is None or _wm_worker.done():
        _wm_worker = asyncio.create_task(_pump_watermark())


async def _run_watermark(client, message, task_id):
    _ensure_runner_watermark()

async def flood_retry(func, *args, retries=5, **kwargs):
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = min(getattr(e, "value", None) or getattr(e, "x", None) or 1, 60)
            LOGGER.warning(f"FloodWait: sleeping for {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            if attempt == retries - 1:
                raise e

