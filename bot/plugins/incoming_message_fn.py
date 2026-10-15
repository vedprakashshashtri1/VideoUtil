# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import datetime
import html
import logging
import os, random, json
import time, subprocess
import asyncio, shlex
from bot.helper_funcs.utils import safe_media_name
from contextlib import nullcontext
from bot.task_manager import (
    task_manager,
    PHASE_QUEUED,
    PHASE_DOWNLOADING,
    PHASE_PROCESSING,
    PHASE_UPLOADING,
)
from bot.group_status import make_manager_progress, UploadSink
from bot.localisation import Localisation
from bot import DOWNLOAD_LOCATION, AUTH_USERS, app, DOWNLOAD_LOCATION1, DOWNLOAD_LOCATION2, DOWNLOAD_LOCATION3, DOWNLOAD_LOCATION4, DOWNLOAD_LOCATION5, DOWNLOAD_LOCATION6, DOWNLOAD_LOCATION7, crf, resolution, audio_b, preset, codec, pid_list
from bot.helper_funcs.ffmpeg import *
from bot.helper_funcs.display_progress import (
    progress_for_pyrogram,
    TimeFormatter,
    safe_progress_edit
)
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from PIL import Image, ImageOps
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from database import db
from bot.config import Config
from bot.helper_funcs.media_caption import enhance_media_caption
from bot.helper_funcs.split_uploader import smart_split_and_upload
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

CURRENT_PROCESSES = {}
CHAT_FLOOD = {}
bot = app



BOT_USERNAME=Config.BOT_USERNAME
UPDATES_CHANNEL=Config.UPDATES_CHANNEL


# ---------------- START --------------------#

async def incoming_start_message_f(bot, update):
    """/start command handler"""

    await bot.send_photo(
        chat_id=update.chat.id,
        photo=random.choice(Config.PICS),
        caption=Localisation.START_TEXT.format(
            first=html.escape(update.from_user.first_name or ""),
            last=html.escape(update.from_user.last_name or ""),
            username=None if not update.from_user.username else '@' + html.escape(update.from_user.username),
            mention=update.from_user.mention,
            id=update.from_user.id
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('👨‍💻 ᴄʀᴇᴀᴛᴏʀ', url='https://t.me/Prime_Sujoy')],
            [
                InlineKeyboardButton('📢 Uᴘᴅᴀᴛᴇs', url='https://t.me/NexonBots'),
                InlineKeyboardButton('💬 Sᴜᴘᴘᴏʀᴛ', url='https://t.me/NexonBotsChat')
            ],
            [
                InlineKeyboardButton('ℹ️ Aʙᴏᴜᴛ', callback_data='about'),
                InlineKeyboardButton('❌ Cʟᴏsᴇ', callback_data='close')
            ]
        ]),
        reply_to_message_id=update.id,
    )



# --- Pattern for unwanted tags ---
TAG_PATTERN = re.compile(
    r'(?i)\[?(360p|240p|480p|720p|1080p|2160p|HDRip|WEB[-\s]?DL|WEBRip|HDcam|BluRay|BRRip|x264|x265|HEVC|H\.264|DD[+]? ?5[.]?1?)\]?',
    re.IGNORECASE
)


# ---------------- 144p --------------------#

def clean_and_insert_resolution5(filename: str, resolution="[144p]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f5(update, user_id, task_id=None):
    """/compress command handler for user"""

    d_start = time.time()
    isAuto = True

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION5, f"status_{task_id or user_id}.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = safe_media_name(update.document.file_name)
        elif update.video:
            original_name = safe_media_name(update.video.file_name or "video.mp4")
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION5, f"{user_id}_input.temp")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟷𝟺𝟺ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION5
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution5(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        # Snapshot encoding settings
        cur_preset = str(preset[0])
        cur_codec = str(codec[0])
        cur_crf = str(crf[0])
        cur_audio_b = str(audio_b[0])

        # SECURITY: Build explicit argv list to prevent argument injection
        ffmpeg_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-progress", progress_path,
            "-i", saved_file_path,
            "-preset", cur_preset, "-c:v", cur_codec, "-crf", cur_crf,
            "-vf", "scale=256:144",
            "-map", "0:v", "-map", "0:a?", "-map", "0:s?", "-map_metadata", "0",
            "-c:a", "aac", "-b:a", cur_audio_b, "-c:s", "copy",
            compressed_path
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟷𝟺𝟺ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            if sent_message:
                try:
                    await sent_message.delete()
                except Exception:
                    pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                # safe edit target check
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION5, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = html.escape(os.path.basename(file_path))

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            try:
                thumb_path = await bot.download_media(thumb)
            except Exception:
                thumb_path = None
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Upload slot: max 1 upload, full speed, millisecond handoff.
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass
        for _f in (downloaded_file_path, compressed_path, progress_path, locals().get("meta_output"), locals().get("thumb_path")):
            try:
                if _f and os.path.exists(_f):
                    os.remove(_f)
            except Exception:
                pass
            
# ---------------- 240p --------------------#

def clean_and_insert_resolution6(filename: str, resolution="[240p]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f6(update, user_id, task_id=None):
    """/compress command handler for user"""

    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION6, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)



        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION6, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟸𝟺𝟶ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION6
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution6(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=426:240',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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
                    #out_time_us = int(progress_data.get("out_time_us", 0))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟸𝟺𝟶ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION6, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            thumb_path = await bot.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Upload slot: max 1 upload, full speed, millisecond handoff.
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass

# ---------------- 360p --------------------#

def clean_and_insert_resolution7(filename: str, resolution="[360p]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f7(update, user_id, task_id=None):
    """/compress command handler for user"""

    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION7, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)



        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION7, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟹𝟼𝟶ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION7
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution7(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=640:360',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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
                    #out_time_us = int(progress_data.get("out_time_us", 0))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟹𝟼𝟶ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends so the next queued
            # heavy job starts while THIS task moves on to upload (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION7, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            thumb_path = await bot.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Upload slot: max 1 upload at a time, full speed. The waiter starts
        # the millisecond the running upload releases (event-driven).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass

# ---------------- 480p --------------------#

def clean_and_insert_resolution(filename: str, resolution="[480p]") -> str:
    name, ext = os.path.splitext(filename)

    # Step 1: Remove all unwanted tags
    name_cleaned = TAG_PATTERN.sub('', name)

    # Step 2: Normalize spaces and brackets
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned)  # remove empty brackets
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  # normalize spaces

    # Step 3: Insert [480p] before the last tag if exists
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        # Replace the last tag with [480p][last_tag]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    # Step 4: Normalize brackets and spacing again
    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"

async def incoming_compress_message_f(update, user_id, task_id=None):
    """/compress command handler for user"""

    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟺𝟾𝟶ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)
        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=854:480',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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
                    #out_time_us = int(progress_data.get("out_time_us", 0))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟺𝟾𝟶ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends so the next queued
            # heavy job starts while THIS task moves on to upload (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            try:
                thumb_path = await bot.download_media(thumb)
            except Exception:
                thumb_path = None
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Upload slot: max 1 upload at a time, full speed. The waiter starts
        # the millisecond the running upload releases (event-driven).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            if sent_message:
                await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass

# ---------------- 720p --------------------#

def clean_and_insert_resolution1(filename: str, resolution="[720p]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f1(update, user_id, task_id=None):
    """/compress command handler for user"""
    
    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION1, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION1, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟽𝟸𝟶ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION1
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution1(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=1280:720',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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
                    #out_time_us = int(progress_data.get("out_time_us", 0))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟽𝟸𝟶ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends so the next queued
            # heavy job starts while THIS task moves on to upload (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION1, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            try:
                thumb_path = await bot.download_media(thumb)
            except Exception:
                thumb_path = None
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None
        
        # Upload slot: max 1 upload at a time, full speed. The waiter starts
        # the millisecond the running upload releases (event-driven).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            if sent_message:
                await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass


# ---------------- 1080p --------------------#

def clean_and_insert_resolution2(filename: str, resolution="[1080p]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f2(update, user_id, task_id=None):
    """/compress command handler for user"""
    
    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION2, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION2, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟷𝟶𝟾𝟶ᴘ Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION2
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution2(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=1920:1080',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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
                    #out_time_us = int(progress_data.get("out_time_us", 0))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟷𝟶𝟾𝟶ᴘ</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends so the next queued
            # heavy job starts while THIS task moves on to upload (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION2, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            try:
                thumb_path = await bot.download_media(thumb)
            except Exception:
                thumb_path = None
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None
        
        # Upload slot: max 1 upload at a time, full speed. The waiter starts
        # the millisecond the running upload releases (event-driven).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            if sent_message:
                await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass


# ---------------- 2160p --------------------#

def clean_and_insert_resolution3(filename: str, resolution="[4K]") -> str:
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  
    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()

    return f"{name_cleaned}.mkv"


async def incoming_compress_message_f3(update, user_id, task_id=None):
    """/compress command handler for user"""
    
    d_start = time.time()
    isAuto = True  

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION3, "status.json")

    try:
        # Update status JSON
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION3, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Downloaded file not found.")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        if task_id:
            # Shared status is the live view; keep the per-task message silent.
            # Stay "Queued" until the heavy slot is actually ours, so the card
            # never shows Encoding for a task that is still waiting.
            await task_manager.set_phase(task_id, PHASE_QUEUED)
            await task_manager.acquire_heavy()
            if task_manager.is_cancelled(task_id):
                task_manager.release_heavy()
                return
            heavy_acquired = True
            await task_manager.set_phase(task_id, PHASE_PROCESSING)
            # Drop stale download numbers (speed/bytes belong to download).
            await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0)
        else:
            await flood_retry(sent_message.edit_text, "⚙️ 𝟺K Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

        # Compression paths
        output_directory = DOWNLOAD_LOCATION3
        base_name = os.path.basename(downloaded_file_path)
        file_name_wo_ext = os.path.splitext(base_name)[0]
        compressed_file_name = clean_and_insert_resolution3(original_name) or original_name
        output_path = os.path.join(output_directory, compressed_file_name)
        saved_file_path = downloaded_file_path
        compressed_path = output_path
        progress_path = os.path.join(output_directory, f"{file_name_wo_ext}_ffmpeg_progress.txt")

        # Remove old progress file
        if os.path.exists(progress_path):
            os.remove(progress_path)

        # SECURITY: argv list, not an f-string + shlex.split (argument injection)
        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-progress', progress_path,
            '-i', saved_file_path,
            '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
            '-vf', 'scale=3840:2160',
            '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
            '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
            compressed_path,
        ]
        COMPRESSION_START_TIME = time.time()
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            last_percent = -1
            bar_length = 12
            total_duration = get_video_duration(saved_file_path)

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

                    current_size = 0
                    if os.path.exists(compressed_path):
                        current_size = os.path.getsize(compressed_path)

                    encoded_size = get_size(current_size)
                    elapsed = time.time() - COMPRESSION_START_TIME
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ ɪɴ 𝟺K</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            # Shared status only; per-task message stays silent.
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str,
                                done_bytes=current_size,
                            )
                        else:
                            await safe_progress_edit(sent_message, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg progress parse error: {e}")
                    continue

        try:
            await asyncio.gather(parse_progress(), process.wait())
        finally:
            # Free the heavy slot the instant encode ends so the next queued
            # heavy job starts while THIS task moves on to upload (pipeline).
            if task_id and heavy_acquired:
                task_manager.release_heavy()
                heavy_acquired = False

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            for _f in (compressed_path, downloaded_file_path, progress_path):
                try:
                    if _f and os.path.exists(_f):
                        os.remove(_f)
                except Exception:
                    pass
            return

        if not os.path.exists(compressed_path):
            raise Exception("❌ Cᴏᴍᴘʀᴇssɪᴏɴ ғᴀɪʟᴇᴅ.")

        file_size = os.path.getsize(compressed_path)
        if file_size == 0:
            raise Exception("⚠️ Fɪʟᴇ sɪᴢᴇ ᴇǫᴜᴀʟs ᴛᴏ 𝟶 B⚠️")

        compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
        u_start = time.time()

        # === Metadata step (use compressed_path as file_path) ===
        file_path = compressed_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                try:
                    if sent_message is not None:
                        await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                except Exception:
                    pass
                meta_output = os.path.join(DOWNLOAD_LOCATION3, f"meta_{os.path.basename(file_path)}")
                file_path = await add_metadata(file_path, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        upload_time = TimeFormatter((time.time() - u_start) * 1000)
        file_name = os.path.basename(file_path)

        caption = (
            f"<blockquote>{file_name}</blockquote>\n\n"
            f"<blockquote>Downloaded: {downloaded_time}\nCompressed: {compressed_time}</blockquote>\n"
            f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
        )

        chat_id = update.chat.id

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            try:
                thumb_path = await bot.download_media(thumb)
            except Exception:
                thumb_path = None
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Upload slot: max 1 upload at a time, full speed. The waiter starts
        # the millisecond the running upload releases (event-driven).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            _up_ok = await smart_split_and_upload(
                client=app,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else sent_message),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if task_id and not _up_ok:
            try:
                await update.reply_text("❌ Upload failed. Please try again.")
            except Exception:
                pass
        # Working message served its purpose (status message is the live view)
        try:
            if sent_message:
                await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass

    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass



# --- Pattern for unwanted tags ---

# ---------------- MULTI --------------------#


def clean_and_insert_resolution4(filename: str, resolution: str) -> str:
    """Clean file name and insert resolution before last tag"""
    name, ext = os.path.splitext(filename)
    name_cleaned = TAG_PATTERN.sub('', name)
    name_cleaned = re.sub(r'\[\s*\]', '', name_cleaned) 
    name_cleaned = re.sub(r'\s{2,}', ' ', name_cleaned).strip()  

    bracket_tags = re.findall(r'\[[^\]]+\]', name_cleaned)
    if bracket_tags:
        last_tag = bracket_tags[-1]
        name_cleaned = name_cleaned.replace(last_tag, f"{resolution}{last_tag}")
    else:
        name_cleaned = f"{name_cleaned} {resolution}"

    name_cleaned = re.sub(r'\s*\[', ' [', name_cleaned).strip()
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()
    return f"{name_cleaned}.mkv"

                    
async def incoming_compress_message_f4(update, user_id, task_id=None):
    """Download once -> encode to multiple resolutions -> upload according to user preference"""
    d_start = time.time()

    # Wired tasks (task_id set) use ONLY the shared status message as their
    # live view, so no per-task working message is created for them at all.
    sent_message = None
    if task_id is None:
        sent_message = await update.reply_text("📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ...")
    heavy_acquired = False

    status_path = os.path.join(DOWNLOAD_LOCATION4, "status.json")

    try:
        with open(status_path, 'w') as f:
            json.dump({'running': True, 'message': sent_message.id if sent_message else 0}, f, indent=2)

        if update.document:
            original_name = update.document.file_name
        elif update.video:
            original_name = update.video.file_name or "video.mp4"
        else:
            raise ValueError("Unsupported file type — must be a video or document.")

        # File path setup
        input_path = os.path.join(DOWNLOAD_LOCATION4, f"{user_id}_input.temp")

        # Download file (download slot: released the instant file hits disk).
        # Wired tasks report ONLY to the shared status (no per-task edits).
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                downloaded_file_path = await update.download(
                    file_name=input_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ...", sent_message, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        if not downloaded_file_path or not os.path.exists(downloaded_file_path):
            raise FileNotFoundError("❌ Download failed")

        downloaded_time = TimeFormatter((time.time() - d_start) * 1000)

        # Define resolutions and scales
        resolutions = {
            "144p": "256:144",
            "240p": "426:240",
            "360p": "640:360",
            "480p": "854:480",
            "720p": "1280:720",
            "1080p": "1920:1080"
        }

        results = []

        # Encode each resolution sequentially
        for res, scale in resolutions.items():
            if task_id and task_manager.is_cancelled(task_id):
                break

            if task_id:
                # Shared status is the live view; keep the per-task message silent.
                # Stay "Queued" until the heavy slot is actually ours.
                await task_manager.set_phase(task_id, PHASE_QUEUED)
                await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0, res=f"all ({res})")
                await task_manager.acquire_heavy()
                if task_manager.is_cancelled(task_id):
                    task_manager.release_heavy()
                    break
                heavy_acquired = True
                await task_manager.set_phase(task_id, PHASE_PROCESSING)
                await task_manager.update_progress(task_id, 0.0, "—", "—", done_bytes=0, total_bytes=0, res=f"all ({res})")
            else:
                await flood_retry(sent_message.edit_text, f"⚙️ {res} Eɴᴄᴏᴅɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss...")

            compressed_file_name = clean_and_insert_resolution4(original_name, f"[{res}]")
            compressed_path = os.path.join(DOWNLOAD_LOCATION4, compressed_file_name)
            progress_path = os.path.join(DOWNLOAD_LOCATION4, f"{res}_ffmpeg_progress.txt")

            if os.path.exists(progress_path):
                os.remove(progress_path)

            # SECURITY: argv list, not an f-string + shlex.split (argument injection)
            ffmpeg_cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-progress', progress_path,
                '-i', downloaded_file_path,
                '-preset', str(preset[0]), '-c:v', str(codec[0]), '-crf', str(crf[0]),
                '-vf', f'scale={scale}',
                '-map', '0:v', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0',
                '-c:a', 'aac', '-b:a', str(audio_b[0]), '-c:s', 'copy',
                compressed_path,
            ]

            COMPRESSION_START_TIME = time.time()
            process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
            if task_id:
                task_manager.register_process(task_id, process)

            async def parse_progress():
                last_percent = -1
                bar_length = 12
                total_duration = get_video_duration(downloaded_file_path)
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
                        current_size = 0
                        if os.path.exists(compressed_path):
                            current_size = os.path.getsize(compressed_path)
                        eta = (time.time() - COMPRESSION_START_TIME) * (100 - percent) / (percent + 1e-5)
                        eta_str = TimeFormatter(eta * 1000)
                        if percent_display != last_percent:
                            if task_id:
                                await task_manager.update_progress(
                                    task_id, percent_display, eta=eta_str,
                                    done_bytes=current_size, res=f"all ({res})",
                                )
                            else:
                                await safe_progress_edit(sent_message,
                                    f"<blockquote><b>ᴇɴᴄᴏᴅɪɴɢ {res}</b></blockquote>\n"
                                    f"<code>[{bar}]</code>\n"
                                    f"<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {percent_display:.2f}%\n"
                                    f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n")
                            last_percent = percent_display
                        if progress_data.get("progress") == "end":
                            break
                    except Exception:
                        continue

            try:
                await asyncio.gather(parse_progress(), process.wait())
            finally:
                if task_id and heavy_acquired:
                    task_manager.release_heavy()
                    heavy_acquired = False

            if task_id and task_manager.is_cancelled(task_id):
                break

            if not os.path.exists(compressed_path):
                raise Exception(f"{res} compression failed")

            compressed_time = TimeFormatter((time.time() - COMPRESSION_START_TIME) * 1000)
            results.append((res, compressed_path, compressed_time))

        if task_id and task_manager.is_cancelled(task_id):
            try:
                if sent_message:
                    await sent_message.delete()
            except Exception:
                pass
            return

        # Upload all versions
        for res, compressed_path, compressed_time in results:
            if task_id and task_manager.is_cancelled(task_id):
                break

            file_size = os.path.getsize(compressed_path)
            if file_size == 0:
                continue

            u_start = time.time()
            file_name = os.path.basename(compressed_path)

            try:
                metadata_status = await db.get_metadata(user_id)
                if metadata_status and metadata_status.lower() == "on":
                    try:
                        if sent_message is not None:
                            await flood_retry(sent_message.edit_text, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                    except Exception:
                        pass
                    meta_output = os.path.join(DOWNLOAD_LOCATION4, f"meta_{os.path.basename(compressed_path)}")
                    compressed_path = await add_metadata(compressed_path, meta_output, user_id)
            except Exception as meta_err:
                LOGGER.warning(f"Metadata addition skipped: {meta_err}")

            caption = (
                f"<blockquote>{file_name}</blockquote>\n\n"
                f"<blockquote>Downloaded: {downloaded_time}\nCompressed ({res}): {compressed_time}</blockquote>\n"
                f"ENCODED BY - {BOT_USERNAME}\nBOT BY - @{UPDATES_CHANNEL}"
            )

            thumb = await db.get_thumbnail(user_id)
            spoiler_enabled = await db.get_user_spoiler(user_id)
            media_preference = await db.get_media_preference(user_id) or "video"
            caption = enhance_media_caption(compressed_path, caption, media_preference)

            if thumb:
                try:
                    thumb_path = await bot.download_media(thumb)
                except Exception:
                    thumb_path = None
            elif media_preference == "video":
                thumb_path = await process_thumbnail(None, video_path=compressed_path)
            else:
                thumb_path = await process_thumbnail_doc(None, video_path=compressed_path)

            duration = get_video_duration(compressed_path) if media_preference == "video" else None

            if task_id:
                await task_manager.set_phase(task_id, PHASE_UPLOADING)
                await task_manager.update_progress(task_id, res=f"all ({res})")
            ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
            async with ul_ctx:
                _up_ok = await smart_split_and_upload(
                    client=app,
                    message=update,
                    file_path=compressed_path,
                    status_msg=(UploadSink(task_id) if task_id else sent_message),
                    caption=caption,
                    thumb_path=thumb_path,
                    duration=int(duration) if duration else None,
                    user_id=user_id,
                    reply_to_id=update.id,
                    task_id=task_id,
                )
            if task_id and not _up_ok:
                try:
                    await update.reply_text("❌ Upload failed. Please try again.")
                except Exception:
                    pass

        try:
            if sent_message:
                await sent_message.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"Error: {e}")
        try:
            if sent_message:
                await flood_retry(sent_message.edit_text, f"⚠️ {str(e)} ⚠️")
        except Exception:
            pass
    finally:
        if task_id and heavy_acquired:
            task_manager.release_heavy()
        if task_id:
            await task_manager.complete(task_id)
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
            except Exception:
                pass


# -------------- FUCK-OFF ------------------#

async def incoming_cancel_message_f(bot, update):
    """/cancel command"""
    if update.from_user.id not in AUTH_USERS:
        try:
            await update.message.delete()
        except:
            pass
        return

    status = DOWNLOAD_LOCATION + "/status.json"
    if os.path.exists(status):
        inline_keyboard = [
            [
                InlineKeyboardButton("Yes 🚫", callback_data="fuckingdo"),
                InlineKeyboardButton("No 🤗", callback_data="fuckoff")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard)
        await update.reply_text("Are you sure? 🚫 This will stop the compression!", reply_markup=reply_markup, quote=True)
    else:
        await bot.send_message(
            chat_id=update.chat.id,
            text="No active compression exists",
            reply_to_message_id=update.id
        )

# -------------VIDEO-TOOLS-------------#

def generate_thumbnail(video_path, output_path):
    try:
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", "00:00:02.000", "-vframes", "1",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            return output_path
        else:
            return None
    except Exception as e:
        print(f"generate_thumbnail error: {e}")
        return None


def get_video_duration(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout = result.stdout.decode().strip()
        if not stdout:
            raise ValueError("ffprobe returned empty output")

        data = json.loads(stdout)

        # First, try format.duration
        duration = data.get("format", {}).get("duration")
        if duration:
            return float(duration)

        # Fallback: check streams
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and stream.get("duration"):
                return float(stream.get("duration"))

        raise ValueError("Duration not found in format or streams.")
    except Exception as e:
        LOGGER.warning(f"Failed to get duration for {file_path}: {e}")
        return 0.0

# -------------- THUMBNAIL ------------------#

async def process_thumbnail(thumb_path, video_path=None):
    if not thumb_path or not os.path.exists(thumb_path):
        print("User thumbnail not found.")
        # No user thumbnail found — try to generate from video if path is available
        if video_path and os.path.exists(video_path):
            # SECURITY: "downloads/" is never created - write the thumb next to the video
            output_path = os.path.join(os.path.dirname(video_path) or ".", f"{Path(video_path).stem}_thumb.jpg")
            thumb_path = await asyncio.to_thread(generate_thumbnail, video_path, output_path)
            if thumb_path:
                print("Generated thumbnail from video.")
            else:
                print("Failed to generate thumbnail from video.")
                return None
        else:
            print("No valid video path provided for thumbnail generation.")
            return None
    else:
        print("Using user-provided thumbnail.")

    try:
        # Open and convert image to RGB
        img = await asyncio.to_thread(Image.open, thumb_path)
        img = await asyncio.to_thread(lambda: img.convert("RGB"))

        # Resize while preserving aspect ratio of 1280x698 → 320x174
        target_width = 320
        target_height = int(target_width * 698 / 1280)  # = 174
        img = await asyncio.to_thread(lambda: img.resize((target_width, target_height), Image.LANCZOS))

        # Save with high JPEG quality to prevent downgrade
        await asyncio.to_thread(img.save, thumb_path, "JPEG", quality=95)

        print(f"Thumbnail processed successfully: {thumb_path}")
        return thumb_path

    except Exception as e:
        print(f"Thumbnail processing failed: {e}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        return None

async def process_thumbnail_doc(thumb_path, video_path=None):
    if not thumb_path or not os.path.exists(thumb_path):
        print("PDF thumbnail not found.")
        # Try generating from video
        if video_path and os.path.exists(video_path):
            # SECURITY: "downloads/" is never created - write the thumb next to the video
            output_path = os.path.join(os.path.dirname(video_path) or ".", f"{Path(video_path).stem}_pdf_thumb.jpg")
            thumb_path = await asyncio.to_thread(generate_thumbnail, video_path, output_path)
            if thumb_path:
                print("Generated thumbnail from video.")
            else:
                print("Failed to generate thumbnail from video.")
                return None
        else:
            print("No valid video path provided for PDF thumbnail generation.")
            return None
    else:
        print("Using user-provided thumbnail for PDF.")

    try:
        # Open and convert to RGB
        img = await asyncio.to_thread(Image.open, thumb_path)
        img = await asyncio.to_thread(lambda: img.convert("RGB"))

        # Resize to fit within 320x320 (maintains aspect ratio)
        img = await asyncio.to_thread(lambda: ImageOps.contain(img, (320, 320), Image.LANCZOS))

        # Pad to exactly 320x320 (black background)
        img = await asyncio.to_thread(lambda: ImageOps.pad(img, (320, 320), color=(0, 0, 0)))

        # Save with high quality
        await asyncio.to_thread(img.save, thumb_path, "JPEG", quality=95)

        print(f"PDF Thumbnail processed successfully: {thumb_path}")
        return thumb_path

    except Exception as e:
        print(f"PDF Thumbnail processing failed: {e}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        return None


# -------------- UPLOADING ------------------#


def get_size(path: str) -> int:
    """Returns the size of a file in bytes."""
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def format_size(size_bytes: int) -> str:
    """Returns human-readable file size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

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


async def cleanup_files(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            LOGGER.error(f"Error removing {path}: {e}")

async def add_metadata(input_path, output_path, user_id):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found in PATH")

    output_dir = os.path.dirname(output_path) or "."
    os.makedirs(output_dir, exist_ok=True)

    metadata = {
        'title': await db.get_title(user_id),
        'video': await db.get_video(user_id),
        'audio': await db.get_audio(user_id),
        'subtitle': await db.get_subtitle(user_id),
        'artist': await db.get_artist(user_id),
        'author': await db.get_author(user_id),
        'encoded_by': await db.get_encoded_by(user_id),
        'custom_tag': await db.get_custom_tag(user_id),
        'commentz': await db.get_commentz(user_id)
    }

    cmd = [
        ffmpeg,
        '-hide_banner',
        '-i', input_path,
        '-map', '0',
        '-c', 'copy',
        '-metadata', f'title={metadata["title"]}',
        '-metadata:s:v', f'title={metadata["video"]}',
        '-metadata:s:s', f'title={metadata["subtitle"]}',
        '-metadata:s:a', f'title={metadata["audio"]}',
        '-metadata', f'artist={metadata["artist"]}',
        '-metadata', f'author={metadata["author"]}',
        '-metadata', f'encoded_by={metadata["encoded_by"]}',
        '-metadata', f'comment={metadata["commentz"]}',
        '-metadata', f'custom_tag={metadata["custom_tag"]}',
        '-loglevel', 'error',
        '-y'
    ]

    ext = os.path.splitext(output_path)[1].lower()
    fmt = 'mp4' if ext == '.mp4' else 'matroska'
    if fmt == 'mp4':
        cmd += ['-movflags', 'use_metadata_tags']
    cmd += ['-f', fmt, output_path]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            LOGGER.error(f"FFmpeg error: {error_msg}")

            if os.path.exists(output_path):
                os.remove(output_path)

            raise RuntimeError(f"Metadata addition failed: {error_msg}")

        return output_path

    except Exception as e:
        LOGGER.error(f"Metadata processing failed: {e}")
        await cleanup_files(output_path)
        raise



