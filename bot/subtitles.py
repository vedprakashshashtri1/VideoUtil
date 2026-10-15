# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from datetime import datetime as dt
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys, re, mimetypes, aiofiles, shlex, json
from pathlib import Path
from pyrogram import Client, filters #InputFile
from pyrogram.types import Message, InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from bot.helper_funcs.media_caption import build_media_caption, enhance_media_caption
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from mimetypes import guess_type
from bot.config import Config
from PIL import Image
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app, crf, resolution, audio_b, preset, codec, name, size, HSUB_LOCATION)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.helper_funcs.display_progress import *
from bot.helper_funcs.split_uploader import smart_split_and_upload, tg_safe_upload_name
from bot.helper_funcs.dump import dump_copy
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
from bot.merge_video import *
from bot.premium import *
from bot.plugins.call_back_button_handler import button
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


rsub_queue = []
rsub_requests = {}
subtitle_requests = {}
subtitle_queue = []
hardsub_requests = {}
hardsub_queue = []
extractsub_queue = []
extractsub_requests = {}
pending_subtype = {}  # Tracks which task user initiated: {"user_id": "soft"|"hard"}


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


@app.on_message(filters.command(["extract_sub", f"extract_sub@{BOT_USERNAME}"]))
async def handle_extract_sub(client, message: Message):
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

    if not message.reply_to_message or not (message.reply_to_message.video or message.reply_to_message.document):
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇxᴛʀᴀᴄᴛ sᴜʙᴛɪᴛʟᴇs.")

    user_id = message.from_user.id
    replied = message.reply_to_message
    media = replied.video or replied.document
    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "sub", title,
        build_dedupe_key(user_id, file_uid, "extract_sub", ""),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    await announce_task(message)

    extractsub_queue.append((message, task_id))
    if len(extractsub_queue) == 1:
        await process_extract_sub(client, message, task_id)



# /hsub command
@app.on_message(filters.command(["hsub", f"hsub@{BOT_USERNAME}"]))
async def hsub_command(client, message: Message):   
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

    reply = message.reply_to_message
    if not reply or not (reply.video or reply.document):
        return await message.reply("🔁 Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ғɪʟᴇ ғɪʀsᴛ.")

    hardsub_requests[message.from_user.id] = reply
    pending_subtype[message.from_user.id] = "hard"
    msg = await message.reply("🎯 Nᴏᴡ sᴇɴᴅ ᴍᴇ ᴛʜᴇ sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ (.sʀᴛ ᴏʀ .ᴀss) 𝙁𝙤𝙧 𝙃𝘼𝙍𝘿 𝙎𝙐𝘽")
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass

# /sub command
@app.on_message(filters.command(["sub", f"sub@{BOT_USERNAME}"]))
async def sub_handler(client, message: Message):
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

    reply = message.reply_to_message
    if not reply:
        return await message.reply("❗ Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ғɪʟᴇ.")

    media = reply.video or reply.document
    if not media:
        return await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ ғɪʟᴇ.")

    subtitle_requests[message.from_user.id] = reply
    pending_subtype[message.from_user.id] = "soft"
    msg = await message.reply("🤜 Nᴏᴡ sᴇɴᴅ ᴍᴇ ᴛʜᴇ sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ (.sʀᴛ ᴏʀ .ᴀss) 𝙛𝙤𝙧 𝙎𝙊𝙁𝙏 𝙎𝙐𝘽")
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass

# Shared handler for incoming subtitle files


@app.on_message(filters.command(["rsub", f"rsub@{BOT_USERNAME}"]))
async def handle_rsub(client, message: Message):   
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

    if not message.reply_to_message or not (message.reply_to_message.video or message.reply_to_message.document):
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ʀᴇᴍᴏᴠᴇ sᴜʙᴛɪᴛʟᴇs.")

    user_id = message.from_user.id
    replied = message.reply_to_message
    media = replied.video or replied.document
    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "sub", title,
        build_dedupe_key(user_id, file_uid, "rsub", ""),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    await announce_task(message)

    rsub_queue.append((message, task_id))
    if len(rsub_queue) == 1:
        await process_rsub_task(client, message, task_id)

@app.on_message(filters.document & ~filters.command(["leech", "l", f"leech@{BOT_USERNAME}", f"l@{BOT_USERNAME}"]))
async def handle_subtitle_file(client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    subtype = pending_subtype.get(user_id)

    if subtype == "soft":
        if user_id not in subtitle_requests:
            return

        if any(item[0] == message if isinstance(item, tuple) else item == message for item in subtitle_queue):
            return await message.reply("⚠️ Tʜɪs sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ǫᴜᴇᴜᴇ.")

        video_message = subtitle_requests.pop(user_id, None)
        if not video_message:
            return

        media = video_message.video or video_message.document
        file_uid = getattr(media, "file_unique_id", "") or str(video_message.id)
        title = (getattr(media, "file_name", None) or "video").strip() or "video"
        task_id, err = await task_manager.register(
            user_id, message.chat.id, "sub", title,
            build_dedupe_key(user_id, file_uid, "sub", ""),
            link=getattr(message, "link", "") or "",
        )
        if not task_id:
            return await message.reply(err)

        await announce_task(message)

        subtitle_queue.append((message, video_message, task_id))
        if len(subtitle_queue) == 1:
            sub_msg, vid_msg, tid = subtitle_queue[0]
            await process_subtitle_task(client, sub_msg, vid_msg, tid)

    elif subtype == "hard":
        if user_id not in hardsub_requests:
            return

        if any(item[0] == message if isinstance(item, tuple) else item == message for item in hardsub_queue):
            return await message.reply("⚠️ Tʜɪs sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ǫᴜᴇᴜᴇ.")

        video_message = hardsub_requests.pop(user_id, None)
        if not video_message:
            return

        media = video_message.video or video_message.document
        file_uid = getattr(media, "file_unique_id", "") or str(video_message.id)
        title = (getattr(media, "file_name", None) or "video").strip() or "video"
        task_id, err = await task_manager.register(
            user_id, message.chat.id, "hardsub", title,
            build_dedupe_key(user_id, file_uid, "hardsub", ""),
            link=getattr(message, "link", "") or "",
        )
        if not task_id:
            return await message.reply(err)

        await announce_task(message)

        hardsub_queue.append((message, video_message, task_id))
        if len(hardsub_queue) == 1:
            sub_msg, vid_msg, tid = hardsub_queue[0]
            await process_hardsub_task(client, sub_msg, vid_msg, tid)

    else:
        return 

            
#------------ADD-SOFT-SUBTITLES-------------#

# 🔧 Main processing function
async def process_subtitle_task(client, message: Message, video_message: Message = None, task_id: str = None):
    from_user = message.from_user.id
    if task_id and task_manager.is_cancelled(task_id):
        return await on_subtitle_task_complete(client, task_id)

    video_path = subtitle_path = output_path = None
    processing = None

    if not video_message:
        video_message = subtitle_requests.pop(from_user, None)
    if not video_message:
        await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ ғɪʟᴇ ᴅᴇᴛᴇᴄᴛᴇᴅ.")
        return await on_subtitle_task_complete(client, task_id)

    video_file = video_message.video or video_message.document
    if not video_file:
        await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ ғɪʟᴇ ᴅᴇᴛᴇᴄᴛᴇᴅ.")
        return await on_subtitle_task_complete(client, task_id)

    # SECURITY: file_name is user-supplied and becomes a path component - block traversal
    file_name = safe_media_name(video_file.file_name or f"video{Path(video_file.file_id).suffix or '.mp4'}")
    video_ext = Path(file_name).suffix.lower()

    if not message.document or not (message.document.file_name or "").endswith((".srt", ".ass")):
        await message.reply("❗ Pʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ .sʀᴛ ᴏʀ .ᴀss sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ.")
        return await on_subtitle_task_complete(client, task_id)

    try:
        if not task_id:
            processing = await flood_retry(
                message.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ..."
            )
        d_start = time.time()

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            # Download video
            video_path = await video_message.download(
                file_name=os.path.join(DOWNLOAD_LOCATION, file_name),
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ᴠɪᴅᴇᴏ...", processing, d_start)
            )

            # Download subtitle
            subtitle_path = await message.download(
                file_name=os.path.join(DOWNLOAD_LOCATION, safe_media_name(message.document.file_name)),
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ sᴜʙs...", processing, time.time())
            )

        if task_id and task_manager.is_cancelled(task_id):
            return

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        # Convert to mkv if mp4
        if video_ext == ".mp4":
            mkv_path = os.path.join(DOWNLOAD_LOCATION, f"converted_{Path(video_path).stem}.mkv")
            video_path = await convert_to_mkv(video_path, mkv_path)

        # Output path
        output_path = os.path.join(DOWNLOAD_LOCATION, f"subtitled_{os.path.basename(video_path)}")

        # Embed subtitle with ffmpeg
        progress_path = os.path.join(DOWNLOAD_LOCATION, f"progress_{from_user}.txt")
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', video_path, '-i', subtitle_path,
            '-c', 'copy', '-map', '0', '-map', '1:s:0',
            '-metadata:s:s:0', 'language=eng', '-metadata:s:s:0', 'title=@NexonBots',
            '-disposition:s:0', 'default', '-y', output_path,
        ]

        SUB_START = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(video_path)

            while process.returncode is None:
                if task_id and task_manager.is_cancelled(task_id):
                    break
                await asyncio.sleep(2)
                if not os.path.exists(progress_path):
                    continue
                try:
                    with open(progress_path, "r") as f:
                        lines = f.readlines()
                    progress_data = dict(line.strip().split("=", 1) for line in lines if "=" in line)

                    out_time_us = int(progress_data.get("out_time_us", "0").replace("N/A", "0"))
                    out_time = out_time_us / 1_000_000
                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    elapsed = time.time() - SUB_START
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>sᴜʙᴛɪᴛʟᴇ ᴇᴍʙᴇᴅᴅɪɴɢ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if not task_id and processing:
                            await flood_retry(processing.edit_text, progress_text)
                        if task_id:
                            await task_manager.update_progress(task_id, percent_display, eta=eta_str)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"Subtitle progress parse error: {e}")
                    continue

        await asyncio.gather(parse_progress(), process.wait())

        if not os.path.exists(output_path):
            await message.reply("❌ Subtitle embedding failed.")
            return

        subbed_time = TimeFormatter((time.time() - SUB_START) * 1000)
        u_start = time.time()

        # ✅ Add metadata before uploading
        try:
            metadata_status = await db.get_metadata(from_user)
            if metadata_status and metadata_status.lower() == "on":
                if not task_id and processing:
                    processing = await flood_retry(processing.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(DOWNLOAD_LOCATION, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, from_user)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        # Caption (same as hardsub)
        caption = (
            f"<blockquote>{os.path.basename(output_path)}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nSubbed: {subbed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        # Upload logic same as hardsub but with destination awareness
        file_size = os.path.getsize(output_path)
        thumb = await db.get_thumbnail(from_user)
        spoiler_enabled = await db.get_user_spoiler(from_user)
        media_preference = await db.get_media_preference(from_user) or "video"
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
                status_msg=(UploadSink(task_id) if task_id else processing),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=from_user,
                reply_to_id=message.id,
                task_id=task_id,
            )

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await process_subtitle_task(client, message, video_message, task_id)

    except Exception as e:
        LOGGER.error(f"Subtitle task error: {e}")
        if processing:
            await flood_retry(processing.edit_text, f"⚠️ {str(e)} ⚠️")

    finally:
        for f in [video_path, subtitle_path, output_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except:
                pass
        if task_id:
            await task_manager.complete(task_id)
        await on_subtitle_task_complete(client, task_id)


# 🚀 On task completion, proceed to next
async def on_subtitle_task_complete(client, task_id=None):
    if subtitle_queue:
        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(subtitle_queue, task_id)
    while subtitle_queue:
        item = subtitle_queue[0]
        tid = item[2] if isinstance(item, tuple) and len(item) == 3 else (item[1] if isinstance(item, tuple) and len(item) == 2 else None)
        if tid and task_manager.is_cancelled(tid):
            await task_manager.complete(tid)
            subtitle_queue.pop(0)
            continue
        if isinstance(item, tuple) and len(item) == 3:
            sub_msg, vid_msg, tid = item
            await process_subtitle_task(client, sub_msg, vid_msg, tid)
        elif isinstance(item, tuple) and len(item) == 2:
            sub_msg, tid = item
            await process_subtitle_task(client, sub_msg, None, tid)
        else:
            await process_subtitle_task(client, item)
        break

#------------ADD-HARD-SUBTITLES-------------#  

async def process_hardsub_task(client, message: Message, video_message: Message = None, task_id: str = None):
    user_id = message.from_user.id

    user_dir = os.path.join(HSUB_LOCATION, f"{user_id}_{task_id or message.id}")
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)
    os.makedirs(user_dir, exist_ok=True)

    video_path = subtitle_path = output_path = None
    processing = None
    heavy_acquired = False

    try:
        if task_id and task_manager.is_cancelled(task_id):
            return

        if not video_message:
            video_message = hardsub_requests.pop(user_id, None)
        if not video_message:
            await message.reply("⚠️ Request expired or not found. Please use /hsub again and reply to the video.")
            return

        video_file = video_message.video or video_message.document
        if not video_file:
            await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ ғɪʟᴇ ᴅᴇᴛᴇᴄᴛᴇᴅ.")
            return

        if not message.document or not (message.document.file_name or "").endswith((".srt", ".ass")):
            await message.reply("❗ Pʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ .sʀᴛ ᴏʀ .ᴀss sᴜʙᴛɪᴛʟᴇ ғɪʟᴇ.")
            return

        if not task_id:
            processing = await flood_retry(message.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ...")

        # === Downloads ===
        d_start = time.time()
        # SECURITY: file_name is user-supplied and becomes a path component - block traversal
        file_name = safe_media_name(video_file.file_name or f"video{Path(video_file.file_id).suffix or '.mp4'}")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            # VIDEO DOWNLOAD
            video_path = await video_message.download(
                file_name=os.path.join(user_dir, file_name),
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ᴠɪᴅᴇᴏ...", processing, d_start)
            )

            # SUBTITLE DOWNLOAD
            subtitle_path = await message.download(
                file_name=os.path.join(user_dir, safe_media_name(message.document.file_name)),
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ sᴜʙs...", processing, time.time())
            )

        if task_id and task_manager.is_cancelled(task_id):
            if processing:
                try:
                    await processing.delete()
                except Exception:
                    pass
            return

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        # === Verify + sanitize paths ===
        if not video_path or not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            await message.reply("❌ Video download failed or file missing/empty.")
            return
        if not subtitle_path or not os.path.exists(subtitle_path) or os.path.getsize(subtitle_path) == 0:
            await message.reply("❌ Subtitle download failed or file missing/empty.")
            return

        def _sanitize_name(name: str) -> str:
            # Allow letters, digits, space, dash, underscore, dot
            name = re.sub(r"[^\w\-\.\s]", "_", name)
            name = re.sub(r"[ _]+", " ", name).strip()
            return name or "input"

        # Sanitize video file path (avoid commas/brackets/odd chars)
        in_ext = os.path.splitext(video_path)[1] or ".mp4"
        safe_in_name = _sanitize_name(os.path.basename(video_path))
        if not safe_in_name.lower().endswith(in_ext.lower()):
            safe_in_name += in_ext
        safe_in_path = os.path.join(user_dir, safe_in_name)
        if os.path.abspath(video_path) != os.path.abspath(safe_in_path):
            try:
                os.link(video_path, safe_in_path)  # fast if same FS
            except Exception:
                shutil.copy2(video_path, safe_in_path)
            video_path = safe_in_path

        # === remove all embedded soft subtitles first ===
        cleaned_in_path = os.path.join(
            user_dir,
            _sanitize_name(os.path.splitext(os.path.basename(video_path))[0] + " (nosub)") + in_ext
        )
        removed = await remove_all_subtitles(video_path, cleaned_in_path)
        if removed:
            video_path = cleaned_in_path
        else:
            LOGGER.warning("Soft-sub removal failed; proceeding with original input.")

        # Build safe output name from sanitized base
        in_base = os.path.splitext(os.path.basename(video_path))[0]
        out_base = _sanitize_name(f"{in_base} (subbed)")
        output_path = os.path.join(user_dir, f"{out_base}.mp4")

        # === Robust hardsub for problematic videos ===
        selected_font = locals().get("selected_font", "auto") or "auto"
        res = locals().get("res", "original") or "original"
        fps_pref = locals().get("fps", "original") or "original"

        fonts_dirs = get_fonts_dirs()

        def _esc(p: str) -> str:
            return (p.replace("\\", "\\\\")
                     .replace(":", "\\:")
                     .replace(",", "\\,")
                     .replace("'", "\\'")
                     .replace("[", "\\[")
                     .replace("]", "\\]"))

        async def _ffprobe_stream(path: str):
            # SECURITY: argv list instead of create_subprocess_shell
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,avg_frame_rate,side_data_list,tags',
                '-of', 'json', path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, _ = await proc.communicate()
            try:
                data = json.loads(out)
                return data.get("streams", [{}])[0]
            except Exception:
                return {}

        safe_sub_path = os.path.join(user_dir, "subs_safe.ass")
        try:
            with open(subtitle_path, "rb") as f:
                raw = f.read()
            try:
                txt = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                txt = raw.decode("latin-1")
            txt = txt.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
            with open(safe_sub_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(txt)
        except Exception:
            safe_sub_path = subtitle_path

        stream = await _ffprobe_stream(video_path)

        rotate = 0
        try:
            tags = stream.get("tags") or {}
            if "rotate" in tags:
                rotate = int(tags["rotate"])
            else:
                sdl = stream.get("side_data_list") or []
                for sd in sdl:
                    if sd.get("rotation") is not None:
                        rotate = int(sd["rotation"])
                        break
        except Exception:
            pass
        r = ((rotate % 360) + 360) % 360

        src_fps = 0.0
        afr = stream.get("avg_frame_rate") or "0/0"
        try:
            num, den = afr.split("/")
            src_fps = float(num) / float(den) if den != "0" else 0.0
        except Exception:
            pass

        def _bucket_fps(v: float) -> int:
            if v <= 0: return 30
            if 23 <= v < 24.5: return 24
            if 24.5 <= v < 27: return 25
            if 27 <= v < 40: return 30
            if 40 <= v < 55: return 50
            return 60

        if str(fps_pref).strip().lower() != "original":
            try:
                out_fps = max(1, int(float(str(fps_pref))))
            except Exception:
                out_fps = _bucket_fps(src_fps)
        else:
            out_fps = _bucket_fps(src_fps)

        pre = []
        if r == 90:
            pre.append("transpose=1")
        elif r == 270:
            pre.append("transpose=2")
        elif r == 180:
            pre.append("hflip,vflip")

        sub_escaped = _esc(safe_sub_path)
        fontsdir_escaped = _esc(":".join(fonts_dirs))
        if selected_font == "auto":
            sub_filter = f"subtitles={sub_escaped}:charenc=UTF-8:fontsdir={fontsdir_escaped}"
        else:
            font_name = os.path.splitext(os.path.basename(selected_font))[0].replace("'", "\\'")
            sub_filter = (
                f"subtitles={sub_escaped}:charenc=UTF-8:fontsdir={fontsdir_escaped}:"
                f"force_style='FontName={font_name}'"
            )

        vf_parts = pre + [sub_filter]

        if res == "original" or not res:
            vf_parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos")
        else:
            try:
                tw, th = (int(x) for x in str(res).split(":"))
                if tw % 2: tw -= 1
                if th % 2: th -= 1
                vf_parts.append(f"scale={tw}:{th}:flags=lanczos")
            except Exception:
                vf_parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos")

        vf_parts.append(f"fps={int(out_fps)}")
        vf_parts.append("format=yuv420p")

        vf_arg = ",".join(vf_parts)

        progress_path = os.path.join(user_dir, "ffmpeg_progress.txt")
        if os.path.exists(progress_path):
            os.remove(progress_path)

        try:
            out_fps_int = int(out_fps)
        except Exception:
            out_fps_int = 30

        # Acquire heavy slot: max 1 heavy task (encode / watermark / hardsub) bot-wide
        if not task_id and processing:
            await flood_retry(processing.edit_text, "⚙️ Pʀᴇᴘᴀʀɪɴɢ ʜᴀʀᴅsᴜʙ...")
        if task_id:
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

        # SECURITY: argv list - no shlex.quote -> shlex.split round-trip (mangles embedded quotes)
        hardsub_cmd = [
            'ffmpeg', '-hide_banner', '-nostdin', '-y', '-v', 'error', '-stats',
            '-analyzeduration', '200M', '-probesize', '200M',
            '-fflags', '+genpts+discardcorrupt', '-err_detect', 'ignore_err', '-ignore_unknown',
            '-progress', progress_path,
            '-i', video_path,
            '-vf', vf_arg,
            '-r', str(out_fps_int),
            '-c:v', codec[0], '-preset', preset[0], '-crf', str(crf[0]),
            '-vsync', '1',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            '-max_muxing_queue_size', '8192',
            output_path,
        ]

        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*hardsub_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(video_path)

            while process.returncode is None:
                if task_id and task_manager.is_cancelled(task_id):
                    break
                await asyncio.sleep(2)
                if not os.path.exists(progress_path):
                    continue
                try:
                    with open(progress_path, "r") as f:
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

                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ʜᴀʀᴅsᴜʙ ᴇɴᴄᴏᴅɪɴɢ</b></blockquote>\n"
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
                    LOGGER.warning(f"Hardsub progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
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

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            await message.reply("❌ Hᴀʀᴅsᴜʙ ғᴀɪʟᴇᴅ. Fɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ.")
            return

        # === Upload logic ===
        file_size = os.path.getsize(output_path)
        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                if not task_id and processing:
                    processing = await flood_retry(processing.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(user_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        caption = (
            f"<blockquote>{os.path.basename(output_path)}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nSubbed: {compressed_time}</blockquote>\n"
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

        # Upload slot: max 1 concurrent upload bot-wide
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
        if processing:
            try:
                await processing.delete()
            except Exception:
                pass

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await process_hardsub_task(client, message, video_message, task_id)

    except Exception as e:
        LOGGER.error(f"Hardsub error: {e}")
        if processing:
            await flood_retry(processing.edit_text, f"⚠️ {str(e)} ⚠️")

    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
        if task_id and heavy_acquired:
            task_manager.release_heavy()
            heavy_acquired = False
        if task_id:
            await task_manager.complete(task_id)
        await on_hardsub_task_complete(client, task_id)


async def on_hardsub_task_complete(client, task_id=None):
    if hardsub_queue:
        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(hardsub_queue, task_id)
    while hardsub_queue:
        item = hardsub_queue[0]
        tid = item[2] if isinstance(item, tuple) and len(item) == 3 else (item[1] if isinstance(item, tuple) and len(item) == 2 else None)
        if tid and task_manager.is_cancelled(tid):
            await task_manager.complete(tid)
            hardsub_queue.pop(0)
            continue
        if isinstance(item, tuple) and len(item) == 3:
            sub_msg, vid_msg, tid = item
            await process_hardsub_task(client, sub_msg, vid_msg, tid)
        elif isinstance(item, tuple) and len(item) == 2:
            sub_msg, tid = item
            await process_hardsub_task(client, sub_msg, None, tid)
        else:
            await process_hardsub_task(client, item)
        break

#--------------REMOVE-SUBTITLES---------------#

async def remove_all_subtitles(input_path, output_path):
    try:
        cmd = [
            "ffmpeg", "-i", input_path,
            "-map", "0:v", "-map", "0:a?",
            "-c", "copy",
            output_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()
        return process.returncode == 0
    except Exception:
        return False

async def process_rsub_task(client, message: Message, task_id: str = None):
    user_id = message.from_user.id
    if task_id and task_manager.is_cancelled(task_id):
        return

    user_dir = os.path.join("app/rsub", f"{user_id}_{task_id or message.id}")
    os.makedirs(user_dir, exist_ok=True)

    sent_msg = None
    try:
        replied = message.reply_to_message
        file = (replied.video or replied.document) if replied else None
        if not file:
            await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ғɪʟᴇ ғᴏᴜɴᴅ. Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")
            return

        # Paths
        input_path = os.path.join(user_dir, "input_file")
        output_path = os.path.join(user_dir, f"{safe_media_name(Path(file.file_name or 'video').stem)}_nosubs.mkv")
        progress_path = os.path.join(user_dir, "ffmpeg_progress.txt")

        if os.path.exists(progress_path):
            os.remove(progress_path)

        # Download
        d_start = time.time()
        if not task_id:
            sent_msg = await message.reply("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ...", quote=True)

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            downloaded_path = await client.download_media(
                file,
                file_name=input_path,
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", sent_msg, d_start)
            )

        if task_id and task_manager.is_cancelled(task_id):
            return

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        # Remove subtitles with progress
        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
        total_duration = get_video_duration(downloaded_path)
        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        remove_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', downloaded_path, '-map', '0:v', '-map', '0:a?', '-c', 'copy',
            output_path,
        ]

        REMOVE_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*remove_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
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

                    elapsed = time.time() - REMOVE_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ʀᴇᴍᴏᴠɪɴɢ sᴜʙᴛɪᴛʟᴇs</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if not task_id and sent_msg:
                            await flood_retry(sent_msg.edit_text, progress_text)
                        if task_id:
                            await task_manager.update_progress(task_id, percent_display, eta=eta_str)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"Rsub progress parse error: {e}")
                    continue

        await asyncio.gather(parse_progress(), process.wait())

        if not os.path.exists(output_path):
            if not task_id and sent_msg:
                await flood_retry(sent_msg.edit_text, "❌ Fᴀɪʟᴇᴅ ᴛᴏ ʀᴇᴍᴏᴠᴇ sᴜʙᴛɪᴛʟᴇs.")
            elif task_id:
                await message.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ʀᴇᴍᴏᴠᴇ sᴜʙᴛɪᴛʟᴇs.")
            return

        # Upload
        file_size = os.path.getsize(output_path)
        u_start = time.time()
        processed_time = TimeFormatter((time.time() - REMOVE_START_TIME) * 1000)

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                if not task_id and sent_msg:
                    sent_msg = await flood_retry(sent_msg.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(user_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        caption = (
            f"<blockquote>{os.path.basename(output_path)}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nProcessed: {processed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(output_path, caption, media_preference)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        thumb = await db.get_thumbnail(user_id)

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

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await process_rsub_task(client, message, task_id)

    except Exception as e:
        LOGGER.error(f"Rsub error: {e}")
        await flood_retry(message.reply, f"⚠️ {str(e)} ⚠️")

    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
        if task_id:
            await task_manager.complete(task_id)
        if rsub_queue:
            # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
            drop_queue_item(rsub_queue, task_id)
        while rsub_queue:
            item = rsub_queue[0]
            tid = item[1] if isinstance(item, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                rsub_queue.pop(0)
                continue
            if isinstance(item, tuple):
                await process_rsub_task(client, item[0], item[1])
            else:
                await process_rsub_task(client, item)
            break


#--------------EXTRACT-SUBTITLES---------------#

async def process_extract_sub(client, message: Message, task_id: str = None):
    user_id = message.from_user.id
    work_dir = os.path.join(DOWNLOAD_LOCATION, f"extract_{user_id}_{task_id or message.id}")
    os.makedirs(work_dir, exist_ok=True)

    downloading = None
    extracting = None
    uploading = None

    try:
        if task_id and task_manager.is_cancelled(task_id):
            return
        replied = message.reply_to_message
        file = (replied.video or replied.document) if replied else None
        if not file:
            await message.reply("⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ ᴀᴛᴛᴀᴄʜᴇᴅ. Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")
            return

        if not task_id:
            try:
                downloading = await message.reply("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...")
            except Exception:
                pass

        input_path = os.path.join(work_dir, "input_file")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            downloaded_path = await client.download_media(
                file,
                file_name=input_path,
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", downloading, time.time())
            )

        if downloading:
            try:
                await downloading.delete()
            except Exception:
                pass

        if task_id and task_manager.is_cancelled(task_id):
            return

        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)

        if not task_id:
            try:
                extracting = await message.reply("🔍 Exᴛʀᴀᴄᴛɪɴɢ Sᴜʙᴛɪᴛʟᴇs...")
            except Exception:
                pass

        sub_output_base = os.path.join(work_dir, "subtitle")
        extracted_any = False

        # Detect subtitle stream index and codec
        probe_cmd = [
            "ffprobe", "-loglevel", "error", "-select_streams", "s",
            "-show_entries", "stream=index,codec_name", "-of", "csv=p=0",
            downloaded_path
        ]
        proc = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        subtitle_info = stdout.decode().strip().split("\n")

        subtitle_streams = []
        for line in subtitle_info:
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[0].isdigit():
                index, codec = int(parts[0]), parts[1].strip()
                ext = "srt" if codec == "subrip" else "ass" if codec == "ass" else codec
                subtitle_streams.append((index, ext))

        if not subtitle_streams:
            if extracting:
                try:
                    await extracting.edit("⚠️ Vɪᴅᴇᴏ ᴍᴀʏ ʙᴇ hᴀʀᴅsᴜʙʙᴇᴅ ᴏʀ ʜᴀs ɴᴏ sᴜʙᴛɪᴛʟᴇs.")
                except Exception:
                    pass
            else:
                await message.reply("⚠️ Vɪᴅᴇᴏ ᴍᴀʏ ʙᴇ hᴀʀᴅsᴜʙʙᴇᴅ ᴏʀ ʜᴀs ɴᴏ sᴜʙᴛɪᴛʟᴇs.")
            return

        for i, (idx, ext) in enumerate(subtitle_streams):
            out_path = f"{sub_output_base}_{i+1}.{ext}"
            cmd = [
                "ffmpeg", "-y", "-i", downloaded_path,
                "-map", f"0:s:{i}", "-c:s", "copy", out_path
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()

            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                extracted_any = True

                # Only clean subtitles if they are .srt
                if ext == "srt":
                    with open(out_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    cleaned_lines = []
                    for line in lines:
                        if "-->" in line or line.strip().isdigit() or line.strip() == "":
                            cleaned_lines.append(line)
                        else:
                            cleaned_lines.append(clean_subtitle_text(line) + "\n")

                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.writelines(cleaned_lines)

        if extracting:
            try:
                await extracting.delete()
            except Exception:
                pass

        if not extracted_any:
            await message.reply("⚠️ Fᴀɪʟᴇᴅ ᴛᴏ ᴇxᴛʀᴀᴄᴛ ᴀɴʏ sᴜʙᴛɪᴛʟᴇs. Vɪᴅᴇᴏ ᴍᴀʏ ʙᴇ hᴀʀᴅsᴜʙʙᴇᴅ.")
            return

        # --- Determine destination (DM / Channel / Group) ---
        pref = (await db.get_upload_preference(user_id)) or "group"
        channel_id = await db.get_user_channel(user_id)

        if pref == "dm":
            dest_chat_id = user_id
            reply_to = None
        elif pref == "channel":
            if not channel_id:
                dest_chat_id = message.chat.id
                reply_to = message.id
            else:
                dest_chat_id = channel_id
                reply_to = None
        else:
            dest_chat_id = message.chat.id
            reply_to = message.id

        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)

        if not task_id:
            try:
                uploading = await message.reply("📤 Uᴘʟᴏᴀᴅɪɴɢ Sᴜʙᴛɪᴛʟᴇs...")
            except Exception:
                pass

        # Send each extracted subtitle to destination
        for i, (_, ext) in enumerate(subtitle_streams):
            sub_file = f"{sub_output_base}_{i+1}.{ext}"
            if not os.path.exists(sub_file):
                continue

            subtitle_caption = build_media_caption(
                sub_file,
                timings=[("Subtitle Track", f"#{i+1} ({ext.upper()})")],
                delivery="document",
            )

            file_size = os.path.getsize(sub_file)
            send_kwargs = dict(
                chat_id=dest_chat_id,
                document=sub_file,
                file_name=tg_safe_upload_name(os.path.basename(sub_file)),
                caption=subtitle_caption,
                reply_to_message_id=reply_to,
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📤 Uᴘʟᴏᴀᴅɪɴɢ...", (uploading or message), time.time())
            )
            while True:
                try:
                    sent = await client.send_document(**send_kwargs)
                    await dump_copy(client, sent)
                    break
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                except Exception as e:
                    LOGGER.warning(f"Failed to send subtitle #{i+1}: {e}")
                    break

        if uploading:
            try:
                await uploading.delete()
            except Exception:
                pass

        # If user selected Channel but hasn't set one, notify them
        if pref == "channel" and not channel_id:
            try:
                await message.reply("⚠️ You selected Channel as upload destination but haven't set one — subtitles sent here instead.")
            except Exception:
                pass

        # Notify user if upload destination is not the current group
        if pref != "group":
            dest_name = "DM" if pref == "dm" else "Channel"
            mention = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>"
            text = Localisation.UPLOAD_SENT_TEXT.format(
                mention=mention,
                dest=dest_name
            )
            try:
                await client.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

    except Exception as e:
        LOGGER.error(f"Extract sub error: {e}")
        try:
            await message.reply(f"❌ Eʀʀᴏʀ: <code>{e}</code>")
        except Exception:
            pass

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if task_id:
            await task_manager.complete(task_id)
        if extractsub_queue:
            # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
            drop_queue_item(extractsub_queue, task_id)
        while extractsub_queue:
            next_item = extractsub_queue[0]
            tid = next_item[1] if isinstance(next_item, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                extractsub_queue.pop(0)
                continue
            if isinstance(next_item, tuple):
                await process_extract_sub(client, next_item[0], next_item[1])
            else:
                await process_extract_sub(client, next_item)
            break

#---------------------------------------------#


def get_fonts_dirs():
    font_dirs = set()
    for root, _, files in os.walk("."):
        for file in files:
            if file.lower().endswith((".ttf", ".otf")):
                font_dirs.add(os.path.abspath(root))
    return font_dirs



async def safe_telegram_call(func, *args, **kwargs):
    """Safely call a Telegram API method with FloodWait handling."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            print(f"⚠️ FloodWait: Sleeping for {e.value} seconds before retrying {func.__name__}")
            await asyncio.sleep(e.value)
        except Exception:
            raise

        


