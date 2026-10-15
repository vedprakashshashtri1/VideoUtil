# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from datetime import datetime as dt
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys, re, mimetypes, aiofiles, json, shlex, glob, tempfile
from collections import defaultdict
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
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
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.fsub import *
from bot.localisation import Localisation
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
from bot.premium import *
from bot.merge_video import *
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


extractaudio_queue = []
extractaudio_requests = {}
remaudio_queue = []
remaudio_requests = {}
audio_requests = {}
audio_queue = []
addaudio_requests = {}
addaudio_queue = []
audio_choices = {}
addaudio_timers = {}
addaudio_button_msgs = {}


#----------------EXTRACT-AUDIO--------------#


@app.on_message(filters.command(["extract_audio", f"extract_audio@{BOT_USERNAME}"]))
async def handle_extract_audio(client, message: Message):
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
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇxᴛʀᴀᴄᴛ ᴀᴜᴅɪᴏ.")

    user_id = message.from_user.id
    replied = message.reply_to_message
    media = replied.video or replied.document
    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "audio", title,
        build_dedupe_key(user_id, file_uid, "extract_audio", ""),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    await announce_task(message)

    extractaudio_queue.append((message, task_id))
    if len(extractaudio_queue) == 1:
        await process_extract_audio(client, message, task_id)


async def safe_telegram_call(func, *args, **kwargs):
    """Helper to handle FloodWait for Telegram API calls."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)


async def process_extract_audio(client, message: Message, task_id: str = None):
    user_id = message.from_user.id
    work_dir = os.path.join("audio", f"{user_id}_{task_id or message.id}")
    downloading = None
    extracting = None

    try:
        if task_id and task_manager.is_cancelled(task_id):
            return

        os.makedirs(work_dir, exist_ok=True)
        replied = message.reply_to_message
        file = (replied.video or replied.document) if replied else None
        if not file:
            await safe_telegram_call(message.reply, "⚠️ Nᴏ ᴠᴀʟɪᴅ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴘʀᴏᴄᴇss. Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")
            return

        if not task_id:
            downloading = await safe_telegram_call(message.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...")

        orig_name = getattr(file, "file_name", None) or "input.mp4"
        _, ext = os.path.splitext(orig_name)
        if not ext:
            ext = ".mp4"
        input_path = os.path.join(work_dir, f"input_file{ext}")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            downloaded_path = await client.download_media(
                file,
                file_name=input_path,
                progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ", downloading, time.time())
            )

        if downloading:
            try:
                await safe_telegram_call(downloading.delete)
            except Exception:
                pass

        if not downloaded_path or not os.path.exists(downloaded_path):
            raise FileNotFoundError(f"Downloaded media file not found: {downloaded_path}")

        if task_id and task_manager.is_cancelled(task_id):
            return

        if not task_id:
            extracting = await safe_telegram_call(message.reply, "🎧 Dᴇᴛᴇᴄᴛɪɴɢ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋs...")

        ffprobe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index,codec_name:stream_tags=language,title",
            "-of", "json", downloaded_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *ffprobe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        try:
            audio_info = json.loads(stdout.decode())
        except Exception:
            audio_info = {}
        audio_streams = audio_info.get("streams", [])

        if not audio_streams:
            if extracting:
                try:
                    await safe_telegram_call(extracting.delete)
                except Exception:
                    pass
            await safe_telegram_call(message.reply, "❌ Nᴏ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋs ғᴏᴜɴᴅ.")
            return

        # Get thumbnail (if available)
        thumb = await db.get_thumbnail(user_id)
        try:
            thumb_path = await client.download_media(thumb) if thumb else await process_thumbnail_doc(None, video_path=downloaded_path)
        except Exception:
            thumb_path = None

        if thumb_path and not os.path.exists(thumb_path):
            thumb_path = None

        out_paths = []
        if extracting:
            await safe_telegram_call(extracting.edit, "🎧 Exᴛʀᴀᴄᴛɪɴɢ ᴀʟʟ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋs...")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        # Total duration for progress
        total_duration = get_video_duration(downloaded_path) or 0
        if not total_duration and file and getattr(file, "duration", None):
            try:
                total_duration = float(file.duration)
            except Exception:
                total_duration = 0

        total_streams = len(audio_streams)

        for i, stream in enumerate(audio_streams):
            if task_id and task_manager.is_cancelled(task_id):
                break

            tags = stream.get("tags", {}) or {}
            lang = tags.get("language") or f"track_{i+1}"
            title = tags.get("title") or f"Track_{i+1}"
            codec = (stream.get("codec_name") or "aac").lower()

            safe_name = re.sub(r'[^\w\-_\. ]', '_', f"{lang}_{title}_{i+1}").strip('_')
            if not safe_name:
                safe_name = f"track_{i+1}"
            out_file = os.path.join(work_dir, f"output_{safe_name}.mp3")
            progress_path = os.path.join(work_dir, f"progress_{i}.txt")

            if os.path.exists(progress_path):
                os.remove(progress_path)

            ffmpeg_cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-progress", progress_path,
                "-i", downloaded_path,
                "-map", f"0:a:{i}", "-vn",
                "-c:a", "libmp3lame", "-b:a", "192k",
                "-metadata", f"title={title}",
                "-metadata", "artist=@NexonBots",
                "-metadata", "album=@NexonBots",
                "-y",
                out_file
            ]

            sent_message = None
            if not task_id:
                sent_message = await safe_telegram_call(message.reply, f"🎧 Exᴛʀᴀᴄᴛɪɴɢ {lang} ({i+1}/{total_streams})...")

            stream_start_time = time.time()
            process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
            if task_id:
                task_manager.register_process(task_id, process)

            async def parse_progress():
                last_percent = -1
                bar_length = 12

                while process.returncode is None:
                    if task_id and task_manager.is_cancelled(task_id):
                        try:
                            process.kill()
                        except Exception:
                            pass
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

                        percent = min(100.0, (out_time / total_duration) * 100.0)
                        track_fraction = 100.0 / total_streams
                        overall_percent = min(100.0, round((i * track_fraction) + (percent / total_streams), 2))
                        percent_display = round(percent, 2)

                        filled = int(bar_length * percent / 100)
                        bar = '█' * filled + '░' * (bar_length - filled)

                        elapsed = time.time() - stream_start_time
                        eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                        eta_str = TimeFormatter(eta * 1000)

                        progress_text = (
                            f"<blockquote><b>🎧 Exᴛʀᴀᴄᴛɪɴɢ {lang} ({i+1}/{total_streams})</b></blockquote>\n"
                            f"<code>[{bar}]</code>\n"
                            f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                            f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                        )

                        if percent_display != last_percent:
                            if not task_id and sent_message:
                                await safe_telegram_call(sent_message.edit_text, progress_text)
                            if task_id:
                                await task_manager.update_progress(task_id, overall_percent, eta=eta_str)
                            last_percent = percent_display

                        if progress_data.get("progress") == "end":
                            break
                    except Exception as e:
                        LOGGER.warning(f"FFmpeg progress parse error: {e}")
                        continue

            await asyncio.gather(parse_progress(), process.wait())
            if sent_message:
                try:
                    await sent_message.delete()
                except Exception:
                    pass

            if task_id and task_manager.is_cancelled(task_id):
                return

            if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                duration = get_audio_duration(out_file)
                out_paths.append((out_file, lang, title, duration))

        if extracting:
            try:
                await safe_telegram_call(extracting.delete)
            except Exception:
                pass

        if not out_paths:
            if not (task_id and task_manager.is_cancelled(task_id)):
                await safe_telegram_call(message.reply, "❌ Nᴏ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋs ᴄᴏᴜʟᴅ ʙᴇ ᴇxᴛʀᴀᴄᴛᴇᴅ.")
            return

        # Destination
        pref = (await db.get_upload_preference(user_id)) or "group"
        channel_id = await db.get_user_channel(user_id)

        notify_missing_channel = False
        if pref == "dm":
            dest_chat_id = user_id
            reply_to = None
        elif pref == "channel":
            if not channel_id:
                dest_chat_id = message.chat.id
                reply_to = message.id
                notify_missing_channel = True
            else:
                dest_chat_id = channel_id
                reply_to = None
        else:
            dest_chat_id = message.chat.id
            reply_to = message.id

        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            for idx, (out_path, lang, title, duration) in enumerate(out_paths, start=1):
                track_details = [("Audio Track", f"{idx} ({lang})")]
                if title:
                    track_details.append(("Title", title))
                caption = build_media_caption(
                    out_path,
                    timings=track_details,
                    delivery="audio",
                )

                while True:
                    try:
                        sent = await client.send_audio(
                            chat_id=dest_chat_id,
                            audio=out_path,
                            file_name=tg_safe_upload_name(os.path.basename(out_path)),
                            caption=caption,
                            reply_to_message_id=reply_to,
                            thumb=thumb_path,
                            duration=duration,
                            title=title,
                            performer="Nᴇxᴏɴ_Bᴏᴛs",
                            progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                            progress_args=(client, caption, message.reply_to_message or message, time.time())
                        )
                        await dump_copy(client, sent)
                        break
                    except FloodWait as fw:
                        await asyncio.sleep(fw.value + 1)
                    except Exception as e:
                        LOGGER.warning(f"Failed to send audio #{idx} directly: {e}")
                        break

        # If user selected Channel but hasn't set one, notify them
        if pref == "channel" and notify_missing_channel:
            await safe_telegram_call(message.reply, "⚠️ You selected Channel as upload destination but haven't set one — audio files sent here instead.")

        if pref != "group":
            dest_name = "DM" if pref == "dm" else "Channel"
            mention = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
            text = Localisation.UPLOAD_SENT_TEXT.format(
                mention=mention,
                dest=dest_name
            )
            try:
                await client.send_message(chat_id=message.chat.id, text=text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    except Exception as e:
        await safe_telegram_call(message.reply, f"❌ Eʀʀᴏʀ: <code>{e}</code>")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if task_id:
            await task_manager.complete(task_id)
        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(extractaudio_queue, task_id)
        while extractaudio_queue:
            next_item = extractaudio_queue[0]
            tid = next_item[1] if isinstance(next_item, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                extractaudio_queue.pop(0)
                continue
            if isinstance(next_item, tuple):
                await process_extract_audio(client, next_item[0], next_item[1])
            else:
                await process_extract_audio(client, next_item)
            break


#----------------REMOVE-AUDIO--------------#

@app.on_message(filters.command(["remaudio", f"remaudio@{BOT_USERNAME}"]))
async def handle_remaudio(client, message: Message):
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
        return await message.reply("⚠️ Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴀᴜᴅɪᴏ.")

    user_id = message.from_user.id
    replied = message.reply_to_message
    media = replied.video or replied.document
    file_uid = getattr(media, "file_unique_id", "") or str(replied.id)
    title = (getattr(media, "file_name", None) or "video").strip() or "video"
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "audio", title,
        build_dedupe_key(user_id, file_uid, "remaudio", ""),
        link=getattr(message, "link", "") or "",
    )
    if not task_id:
        return await message.reply(err)

    await announce_task(message)

    remaudio_queue.append((message, task_id))
    if len(remaudio_queue) == 1:
        await process_remaudio_task(client, message, task_id)


async def process_remaudio_task(client, message: Message, task_id: str = None):
    user_id = message.from_user.id
    base_dir = os.path.join(tempfile.gettempdir(), "video-util", "raudio", f"{user_id}_{task_id or message.id}")
    sent_message = None

    try:
        if task_id and task_manager.is_cancelled(task_id):
            return

        replied = message.reply_to_message
        file = (replied.video or replied.document) if replied else None
        if not file:
            return await message.reply("⚠️ Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ/ᴅᴏᴄᴜᴍᴇɴᴛ.")

        os.makedirs(base_dir, exist_ok=True)
        d_start = time.time()
        if not task_id:
            sent_message = await safe_telegram_call(message.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...")

        input_path = os.path.join(base_dir, file.file_name or "input.mkv")
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_path = await client.download_media(
                    file,
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e
        if sent_message:
            try:
                await sent_message.delete()
            except Exception:
                pass

        if task_id and task_manager.is_cancelled(task_id):
            return

        if not downloaded_path or not os.path.exists(downloaded_path):
            return await message.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ.")

        # Step 1: Probe audio tracks
        cmd_probe = [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "csv=p=0", downloaded_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd_probe, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        audio_lines = stdout.decode().strip().splitlines()
        track_count = len(list(filter(None, audio_lines)))

        choice = None
        if track_count > 1:
            buttons = [[
                InlineKeyboardButton("❌ Rᴇᴍᴏᴠᴇ Aʟʟ", callback_data=f"audio_remove_{user_id}")
            ]]
            for line in audio_lines:
                if not line.strip():
                    continue
                parts = line.split(",")
                idx = parts[0]
                lang = parts[1] if len(parts) > 1 and parts[1].strip() else f"Track {idx}"
                buttons.append([InlineKeyboardButton(lang, callback_data=f"audio_{idx}_{user_id}")])

            ask_msg = await safe_telegram_call(
                message.reply,
                "🎚 Sᴇʟᴇᴄᴛ ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋ ᴛᴏ ʀᴇᴍᴏᴠᴇ (ᴡɪᴛʜɪɴ 𝟸 ᴍɪɴs):",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

            for _ in range(120):
                if user_id in audio_choices:
                    choice = audio_choices.pop(user_id)
                    break
                await asyncio.sleep(1)

            try:
                await ask_msg.delete()
            except Exception:
                pass

        # Step 2: Build ffmpeg command
        orig_name, ext = os.path.splitext(os.path.basename(downloaded_path))
        output_path = os.path.join(base_dir, f"{orig_name}_audio{ext}")

        progress_path = os.path.join(base_dir, "ffmpeg_progress.txt")
        if os.path.exists(progress_path):
            os.remove(progress_path)

        if not choice or choice.startswith("audio_remove"):
            # SECURITY: argv list, not an f-string + shlex.split (argument injection)
            ffmpeg_cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-progress', progress_path,
                '-i', downloaded_path,
                '-map', '0', '-map', '-0:a', '-c', 'copy',
                '-movflags', '+faststart', output_path,
            ]
        elif choice.startswith("audio_"):
            idx = int(choice.split("_")[1])
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", downloaded_path],
                capture_output=True, text=True, timeout=30
            )
            # SECURITY: malformed ffprobe output must not crash the handler
            try:
                info = json.loads(probe.stdout)
            except ValueError:
                info = {}

            maps = []
            for s in info.get("streams", []):
                sid = s["index"]
                if s.get("codec_type") == "audio" and sid == idx:
                    continue
                maps += ["-map", f"0:{sid}"]

            ffmpeg_cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-progress', progress_path,
                '-i', downloaded_path,
            ] + maps + [
                '-c', 'copy', '-movflags', '+faststart', output_path,
            ]
        else:
            ffmpeg_cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-progress', progress_path,
                '-i', downloaded_path,
                '-map', '0', '-map', '-0:a', '-c', 'copy',
                '-movflags', '+faststart', output_path,
            ]

        # Step 3: Run with progress
        if not task_id:
            sent_message = await safe_telegram_call(message.reply, "🔇 Rᴇᴍᴏᴠɪɴɢ ᴀᴜᴅɪᴏ...")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        COMPRESSION_START_TIME = time.time()
        # SECURITY: ffmpeg_cmd is an argv list - never re-tokenize it through shlex
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(downloaded_path)

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

                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>Rᴇᴍᴏᴠɪɴɢ Aᴜᴅɪᴏ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if not task_id and sent_message:
                            await safe_telegram_call(sent_message.edit_text, progress_text)
                        if task_id:
                            await task_manager.update_progress(task_id, percent_display, eta=eta_str)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        await asyncio.gather(parse_progress(), process.wait())
        if sent_message:
            try:
                await sent_message.delete()
            except Exception:
                pass

        if not os.path.exists(output_path):
            return await message.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴀᴜᴅɪᴏ.")

        # Step 4: Upload
        removed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        file_name = os.path.basename(output_path)

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                meta_output = os.path.join(base_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Audio Removed: {removed_time}</blockquote>\n"
            f"PROCESSED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
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

        # --- Determine destination (DM / Channel / Group) ---
        pref = (await db.get_upload_preference(user_id)) or "group"
        channel_id = await db.get_user_channel(user_id)

        if pref == "dm":
            dest_chat_id = user_id
            reply_to = None
        elif pref == "channel":
            if not channel_id:
                await flood_retry(message.reply, "⚠️ Channel not set — sending result here instead.")
                dest_chat_id = message.chat.id
                reply_to = message.id
            else:
                dest_chat_id = channel_id
                reply_to = None
        else:
            dest_chat_id = message.chat.id
            reply_to = message.id

        uploading = None
        if not task_id:
            uploading = await safe_telegram_call(message.reply, "📤 Uploading...")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            await smart_split_and_upload(
                client=client,
                message=message,
                file_path=output_path,
                status_msg=(UploadSink(task_id) if task_id else uploading),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=message.id,
                task_id=task_id,
            )

        if uploading:
            try:
                await uploading.delete()
            except Exception:
                pass

        # Notify user if upload destination is not the current group
        if pref != "group":
            dest_name = "DM" if pref == "dm" else "Channel"
            mention = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
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
            except Exception as e:
                LOGGER.warning(f"Failed to send upload notification: {e}")

    except Exception as e:
        await message.reply(f"❌ Eʀʀᴏʀ: <code>{e}</code>")

    finally:
        shutil.rmtree(base_dir, ignore_errors=True)
        if task_id:
            await task_manager.complete(task_id)
        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(remaudio_queue, task_id)
        while remaudio_queue:
            next_item = remaudio_queue[0]
            tid = next_item[1] if isinstance(next_item, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                remaudio_queue.pop(0)
                continue
            if isinstance(next_item, tuple):
                await process_remaudio_task(client, next_item[0], next_item[1])
            else:
                await process_remaudio_task(client, next_item)
            break


#----------------ADD-AUDIO--------------#

# ---------------- COMMAND ---------------- #
@app.on_message(filters.command(["addaudio", f"addaudio@{BOT_USERNAME}"]))
async def handle_addaudio(client, message: Message):
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
        return await message.reply("❗ Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ғɪʟᴇ.")

    media = reply.video or reply.document
    if reply.document:
        mime = reply.document.mime_type or guess_type(reply.document.file_name or "")[0]
        if not mime or not mime.startswith("video/"):
            return await message.reply("⚠️ Nᴏɴ-ᴠɪᴅᴇᴏ ғɪʟᴇ.")

    audio_requests[message.from_user.id] = reply

    msg = await message.reply("🎧 Nᴏᴡ sᴇɴᴅ ᴀᴜᴅɪᴏ ғɪʟᴇs (.aac, .mp3, .m4a, etc.) ᴛᴏ ᴍᴇʀɢᴇ ɪɴᴛᴏ ᴠɪᴅᴇᴏ.")
    await asyncio.sleep(30)
    try: await msg.delete()
    except: pass 

# -------------- AUDIO HANDLER -------------- #

pending_batches = {} 
locks = defaultdict(asyncio.Lock) 

@app.on_message(filters.audio)
async def handle_audio_file(client, message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id

    if user_id not in audio_requests:
        return

    # Init user request if first time
    if user_id not in addaudio_requests:
        addaudio_requests[user_id] = {
            "video_msg": audio_requests[user_id],
            "audio_msgs": []
        }

    # Add audio
    addaudio_requests[user_id]["audio_msgs"].append(message)

    # Debounce: schedule/update a batch update
    if user_id in pending_batches:
        pending_batches[user_id].cancel()

    pending_batches[user_id] = asyncio.create_task(
        send_addaudio_status(client, message, user_id)
    )


async def send_addaudio_status(client, message, user_id):
    try:
        await asyncio.sleep(1.5)  # collect all audios in this window

        async with locks[user_id]:  # prevent race
            audio_count = len(addaudio_requests[user_id]["audio_msgs"])

            # Buttons
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Sᴛᴀʀᴛ ᴀᴅᴅɪɴɢ", callback_data=f"addaudio_done:{user_id}")],
                [InlineKeyboardButton("🫷 ᴡᴀɪᴛ, sᴇɴᴅɪɴɢ ᴍᴏʀᴇ 🫸", callback_data=f"addaudio_more:{user_id}")]
            ])

            text = (
                f"🎧 {audio_count} ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋ{'s' if audio_count > 1 else ''} ʀᴇᴄᴇɪᴠᴇᴅ.\n\n"
                "Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇɴᴅ ᴍᴏʀᴇ ᴀᴜᴅɪᴏ ғɪʟᴇs ᴏʀ sᴛᴀʀᴛ ᴍᴇʀɢɪɴɢ ɴᴏᴡ?"
            )

            if user_id in addaudio_button_msgs:
                try:
                    await addaudio_button_msgs[user_id].edit_text(text, reply_markup=keyboard)
                except Exception:
                    addaudio_button_msgs[user_id] = await message.reply(text, reply_markup=keyboard)
            else:
                addaudio_button_msgs[user_id] = await message.reply(text, reply_markup=keyboard)

            button_msg = addaudio_button_msgs[user_id]

            # Restart 30s merge timer
            if user_id in addaudio_timers:
                addaudio_timers[user_id].cancel()

            addaudio_timers[user_id] = asyncio.create_task(
                start_addaudio_timer(client, user_id, 30, button_msg)
            )

    except asyncio.CancelledError:
        pass


async def start_addaudio_timer(client, user_id, timeout, button_msg):
    try:
        await asyncio.sleep(timeout)

        try:
            await button_msg.delete()
        except:
            pass

        if user_id not in addaudio_queue and user_id in addaudio_requests:
            addaudio_queue.append(user_id)
            await process_addaudio_task(client, user_id)

    except asyncio.CancelledError:
        pass

# ---------------- PROCESSOR ---------------- #
async def process_addaudio_task(client, user_id):
    video_msg = None
    task_id = None
    base_dir = None
    try:
        request = addaudio_requests.get(user_id)
        if not request:
            return

        video_msg = request['video_msg']
        audio_msgs = request['audio_msgs']
        video_file = video_msg.video or video_msg.document

        media = video_msg.video or video_msg.document
        file_uid = getattr(media, "file_unique_id", "") or str(video_msg.id)
        title = (getattr(media, "file_name", None) or "video").strip() or "video"
        task_id, err = await task_manager.register(
            user_id, video_msg.chat.id, "audio", title,
            build_dedupe_key(user_id, file_uid, "addaudio", ""),
            link=getattr(video_msg, "link", "") or "",
        )
        if not task_id:
            if video_msg:
                await video_msg.reply(err)
            return

        await announce_task(video_msg)

        if task_manager.is_cancelled(task_id):
            return

        base_dir = os.path.join("app/addaudio", f"{user_id}_{task_id}")
        os.makedirs(base_dir, exist_ok=True)

        # Step 1: Download video
        video_path = os.path.join(base_dir, "input_video.mkv")
        await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id)
        async with dl_ctx:
            video_dl = await client.download_media(
                video_file,
                file_name=video_path,
                progress=make_manager_progress(task_id),
            )

        if task_manager.is_cancelled(task_id):
            return

        if not video_dl or not os.path.exists(video_dl):
            return await video_msg.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴠɪᴅᴇᴏ.")

        # Step 2: Download all audios
        audio_paths = []
        for idx, audio_msg in enumerate(audio_msgs, start=1):
            if task_manager.is_cancelled(task_id):
                return
            audio_file = audio_msg.audio or audio_msg.document
            audio_path = os.path.join(base_dir, f"input_audio_{idx}.m4a")

            audio_dl = await client.download_media(
                audio_file,
                file_name=audio_path,
                progress=make_manager_progress(task_id),
            )
            audio_paths.append((audio_dl, audio_msg.caption or ""))

        if task_manager.is_cancelled(task_id):
            return

        # Step 3: Add audio to video with ffmpeg + progress
        output_path = os.path.join(base_dir, "output_added_audio.mkv")
        progress_path = os.path.join(base_dir, "ffmpeg_progress.txt")
        if os.path.exists(progress_path):
            os.remove(progress_path)

        ffmpeg_cmd = await build_add_audio_ffmpeg(video_dl, audio_paths, output_path, progress_path)

        await task_manager.set_phase(task_id, PHASE_PROCESSING)
        COMPRESSION_START_TIME = time.time()
        # SECURITY: ffmpeg_cmd is already an argv list - never re-tokenize it through shlex
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            total_duration = get_video_duration(video_dl)

            while True:
                await asyncio.sleep(2)
                if task_manager.is_cancelled(task_id):
                    try:
                        process.kill()
                    except Exception:
                        pass
                    break
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

                    percent = min(100.0, (out_time / total_duration) * 100.0)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100.0 - percent)) / (percent + 1e-5) if percent > 0 else 0
                    eta_str = TimeFormatter(eta * 1000)

                    await task_manager.update_progress(task_id, percent, eta=eta_str)

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        await asyncio.gather(parse_progress(), process.wait())

        if task_manager.is_cancelled(task_id):
            return

        if not os.path.exists(output_path):
            return await video_msg.reply("❌ Fᴀɪʟᴇᴅ ᴛᴏ ᴀᴅᴅ ᴀᴜᴅɪᴏ.")

        # Step 4: Upload
        added_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        file_name = os.path.basename(output_path)

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                meta_output = os.path.join(base_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Audio Added: {added_time}</blockquote>\n"
            f"PROCESSED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(output_path, caption, media_preference)
        spoiler_enabled = await db.get_user_spoiler(user_id)

        # Thumbnail
        thumb = await db.get_thumbnail(user_id)
        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=output_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=output_path)

        duration = get_video_duration(output_path) if media_preference == "video" else None

        # --- Determine destination (DM / Channel / Group) ---
        pref = (await db.get_upload_preference(user_id)) or "group"
        channel_id = await db.get_user_channel(user_id)

        if pref == "dm":
            dest_chat_id = user_id
            reply_to = None
        elif pref == "channel":
            if not channel_id:
                # fallback to original chat and inform user later
                await flood_retry(video_msg.reply, "⚠️ Channel not set — sending result here instead.")
                dest_chat_id = video_msg.chat.id
                reply_to = video_msg.id
            else:
                dest_chat_id = channel_id
                reply_to = None
        else:
            dest_chat_id = video_msg.chat.id
            reply_to = video_msg.id

        await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id)
        async with ul_ctx:
            await smart_split_and_upload(
                client=client,
                message=video_msg,
                file_path=output_path,
                status_msg=UploadSink(task_id),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=video_msg.id,
                task_id=task_id,
            )

        # Notify user if upload destination is not the original group
        if pref != "group":
            dest_name = "DM" if pref == "dm" else "Channel"
            mention = f"<a href='tg://user?id={user_id}'>{video_msg.from_user.first_name}</a>"

            text = Localisation.UPLOAD_SENT_TEXT.format(
                mention=mention,
                dest=dest_name
            )

            try:
                await client.send_message(
                    chat_id=video_msg.chat.id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                LOGGER.warning(f"Failed to send upload notification: {e}")

    except Exception as e:
        if video_msg:
            await safe_telegram_call(video_msg.reply, f"❌ Eʀʀᴏʀ: <code>{e}</code>")

    finally:
        if base_dir:
            shutil.rmtree(base_dir, ignore_errors=True)
        if task_id:
            await task_manager.complete(task_id)
        # SECURITY: addaudio_queue holds bare user ids - drop only this user's entry
        drop_queue_item(addaudio_queue, user_id)
        addaudio_requests.pop(user_id, None)
        if len(addaudio_queue) > 0:
            await process_addaudio_task(client, addaudio_queue[0])


# helper to build ffmpeg command
async def build_add_audio_ffmpeg(video_path, audio_list, output_path, progress_path):
    def detect_language(file_path, caption=""):
        text = f"{file_path} {caption}".lower()
        if "hin" in text or "hindi" in text: return "hin", "Hindi"
        if "eng" in text or "english" in text: return "eng", "English"
        if "tam" in text or "tamil" in text: return "tam", "Tamil"
        if "tel" in text or "telugu" in text: return "tel", "Telugu"
        if "kan" in text or "kannada" in text: return "kan", "Kannada"
        if "jpn" in text or "kannada" in text: return "jpn", "Japanese"
        if "mal" in text or "malayalam" in text: return "mal", "Malayalam"
        if "mar" in text or "marathi" in text: return "mar", "Marathi"
        return "und", "Unknown"

    # Count existing audio tracks
    ffprobe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "json", video_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *ffprobe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    try:
        audio_streams = json.loads(stdout.decode()).get("streams", [])
    except (ValueError, AttributeError):
        # SECURITY: malformed ffprobe output must not crash the handler
        audio_streams = []
    existing_audio_count = len(audio_streams)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-progress", progress_path,
        "-i", video_path
    ]
    for a, _ in audio_list:
        cmd.extend(["-i", a])

    cmd.extend(["-map", "0:v", "-map", "0:a?", "-map", "0:s?"])
    for i in range(len(audio_list)):
        cmd.extend(["-map", f"{i+1}:a"])

    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-c:s", "copy"])

    for i, (a, cap) in enumerate(audio_list):
        lang_code, lang_name = detect_language(a, cap)
        track_index = existing_audio_count + i
        cmd.extend([
            f"-metadata:s:a:{track_index}", f"language={lang_code}",
            f"-metadata:s:a:{track_index}", f"title=Anime Cruise - {lang_name}"
        ])

    cmd.extend(["-disposition:a:0", "0"])
    cmd.extend([f"-disposition:a:{existing_audio_count}", "default"])
    cmd.append(output_path)

    # SECURITY: return a real argv list - quoting then re-splitting mangles embedded quotes
    return cmd
