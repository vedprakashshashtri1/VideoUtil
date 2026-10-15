# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.response import *
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
from bot.premium import *
from bot.localisation import Localisation
from pyrogram import Client, filters
from pyrogram.types import Message, ForceReply
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode
from bot.helper_funcs.media_caption import enhance_media_caption
from contextlib import nullcontext
from bot.task_manager import (
    task_manager,
    PHASE_QUEUED,
    PHASE_DOWNLOADING,
    PHASE_PROCESSING,
    PHASE_UPLOADING,
    build_dedupe_key,
)
from bot.group_status import announce_task, make_manager_progress, UploadSink
import asyncio
import os
import time
import subprocess

cut_queue = []

async def safe_telegram_call(func, *args, **kwargs):
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            print(f"⏳ FloodWait: Sleeping for {e.value} seconds...")
            await asyncio.sleep(e.value)
        except Exception:
            raise

@app.on_message(filters.reply & filters.command(["cut", f"cut@{BOT_USERNAME}"]))
async def cut_command(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id
    is_premium = await is_premium_user(user_id)

    # Force Subscription
    if not await is_subscribed(app, user_id):
        return await not_joined(app, message)

    verify_status = await db.get_verify_status(user_id)
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
            await db.update_verify_status(user_id, is_verified=False)
            verify_status = await db.get_verify_status(user_id)

        if not is_premium and not verify_status['is_verified']:
            return await short_url(app, message)

    if not message.reply_to_message:
        return await message.reply("⚠️ Please reply to a video you want to cut.")

    replied = message.reply_to_message
    media = replied.video or replied.document
    if not media or not media.file_id:
        return await message.reply("⚠️ Invalid or missing video file.")

    # ✅ Force user to reply using ForceReply
    ask_msg = await message.reply(
        "📝 Send the start and end time like:\n\n`00:01:30 - 00:02:45`",
        reply_markup=ForceReply(selective=True)
    )

    try:
        response_msg = await client.listen(
            chat_id=message.chat.id,
            filters=filters.reply & filters.user(user_id),
            timeout=60
        )
    except asyncio.TimeoutError:
        return await message.reply("⏱️ Timeout! Please try again.")
    except Exception as e:
        return await message.reply(f"❌ Error:\n`{e}`")

    if not response_msg.text or "-" not in response_msg.text:
        return await message.reply("⚠️ Invalid input. Format: `HH:MM:SS - HH:MM:SS`")

    try:
        start_time, end_time = map(str.strip, response_msg.text.split("-"))
    except Exception:
        return await message.reply("⚠️ Could not parse time. Use format like `00:00:10 - 00:00:40`")

    media = replied.video or replied.document
    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "cut", title,
        build_dedupe_key(user_id, file_uid, "cut", f"{start_time}-{end_time}"),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    await announce_task(message)

    cut_queue.append((client, message, replied, start_time, end_time, task_id))
    if len(cut_queue) == 1:
        await process_cut_task(*cut_queue[0])


async def process_cut_task(client, message, replied, start_time: str, end_time: str, task_id: str = None):
    user_id = message.from_user.id
    CUT_DIR = "app/cut"
    os.makedirs(CUT_DIR, exist_ok=True)

    input_path = f"{CUT_DIR}/{user_id}_{task_id or message.id}_input.mp4"
    output_path = f"{CUT_DIR}/{user_id}_{task_id or message.id}_cut.mp4"
    progress_path = f"{CUT_DIR}/{user_id}_{task_id or message.id}_progress.txt"

    sent_msg = None
    try:
        if task_id and task_manager.is_cancelled(task_id):
            return

        if not task_id:
            sent_msg = await safe_telegram_call(
                message.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ..."
            )

        # Download file
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                await safe_telegram_call(
                    replied.download,
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", sent_msg, time.time())
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            return

        if not task_id and sent_msg:
            await safe_telegram_call(sent_msg.edit, "✂️ Tʀɪᴍᴍɪɴɢ ᴠɪᴅᴇᴏ...")
        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        total_duration = get_video_duration(input_path)
        start_ts = time.time()

        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", start_time, "-to", end_time,
            "-i", input_path,
            "-c:v", "copy", "-c:a", "copy",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        if task_id:
            task_manager.register_process(task_id, process)

        async def simulate_progress():
            bar_length = 12
            last_percent = -1
            est_duration = get_video_duration(output_path) or (get_video_duration(input_path) or 60)
            while process.returncode is None:
                await asyncio.sleep(2)
                try:
                    elapsed = time.time() - start_ts
                    percent = min(100, (elapsed / est_duration) * 100)
                    filled = int(bar_length * percent / 100)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    eta = (elapsed * (100 - percent)) / max(percent, 1e-3)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴠɪᴅᴇᴏ ᴛʀɪᴍᴍɪɴɢ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )
                    if percent != last_percent:
                        if task_id:
                            await task_manager.update_progress(task_id, percent, eta=eta_str)
                        elif sent_msg:
                            await safe_telegram_call(sent_msg.edit_text, progress_text)
                        last_percent = percent

                    if percent >= 100:
                        break
                except Exception as e:
                    LOGGER.warning(f"Simulated progress error: {e}")
                    continue

        await asyncio.gather(simulate_progress(), process.wait())

        if process.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            stderr_output = (await process.stderr.read()).decode(errors="ignore")
            LOGGER.error(f"FFmpeg failed: {stderr_output}")
            return await safe_telegram_call(sent_msg.edit if sent_msg else message.reply, "❌ Tʀɪᴍᴍɪɴɢ ғᴀɪʟᴇᴅ.")

        if task_id and task_manager.is_cancelled(task_id):
            return

        file_size = os.path.getsize(output_path)
        downloaded_time = TimeFormatter((time.time() - os.path.getctime(input_path)) * 1000)
        subbed_time = TimeFormatter((time.time() - os.path.getctime(output_path)) * 1000)

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                if sent_msg:
                    await flood_retry(sent_msg.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(CUT_DIR, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        # Caption
        caption = (
            f"<blockquote>{os.path.basename(output_path)}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nTrimmed: {subbed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(output_path, caption, media_preference)

        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=output_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=output_path)

        duration = get_video_duration(output_path) if media_preference == "video" else None

        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            await smart_split_and_upload(
                client=client,
                message=message,
                file_path=output_path,
                status_msg=(UploadSink(task_id) if task_id else sent_msg),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=message.id,
                task_id=task_id,
            )
        if sent_msg:
            try:
                await sent_msg.delete()
            except Exception:
                pass

    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        return await process_cut_task(client, message, replied, start_time, end_time, task_id)

    except Exception as e:
        LOGGER.error(f"Cut error: {e}")
        await safe_telegram_call(
            message.reply,
            f"❌ Error:\n<code>{e}</code>",
            parse_mode=ParseMode.HTML
        )

    finally:
        for f in (input_path, output_path, progress_path):
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        if task_id:
            await task_manager.complete(task_id)

        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(cut_queue, task_id)
        while cut_queue:
            next_task = cut_queue[0]
            tid = next_task[-1] if isinstance(next_task, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                cut_queue.pop(0)
                continue
            await process_cut_task(*next_task)
            break
