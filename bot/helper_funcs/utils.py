# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# the logging things
import logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)


from bot import (
    CROP_LOCATION,
    DOWNLOAD_LOCATION,
    DOWNLOAD_LOCATION1,
    DOWNLOAD_LOCATION2,
    DOWNLOAD_LOCATION3,
    DOWNLOAD_LOCATION4,
    DOWNLOAD_LOCATION5,
    DOWNLOAD_LOCATION6,
    DOWNLOAD_LOCATION7,
    data,
    data1,
    data2,
    data3,
    data4,
    data5,
    data6,
    data7,
    crop,
)
from database import db
from bot.localisation import Localisation
from bot.helper_funcs.display_progress import *
from pyrogram.types import Message
from datetime import datetime as dt
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys, re, aiofiles, mimetypes
from pathlib import Path
from pyrogram import Client, filters #InputFile
import pyrogram
from pyrogram.types import Message, InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from mimetypes import guess_type
from bot.config import Config
from PIL import Image, ImageOps
from pathlib import Path
from pyrogram.errors import FloodWait

# SECURITY: Sanitize user-supplied media name to avoid path traversal & argument injection.
# IMPORTANT: this must be defined BEFORE the incoming_message_fn import below. That module
# does `from bot.helper_funcs.utils import safe_media_name` at module level, so if the
# import below runs first, utils is still partially initialized and the import explodes
# with a circular-import ImportError (bot never starts).
def safe_media_name(name: str) -> str:
    name = os.path.basename(name or "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "input"


from bot.plugins.incoming_message_fn import *
from bot.crop import add_crop_task
from bot.task_manager import task_manager, build_dedupe_key


THUMB_URL = "https://i.ibb.co/wrdKRrzs/x.jpg"  # Correct direct image URL
THUMB_PATH = Path("temp_thumb.jpg")
#Define video extensions
VIDEO_EXTS = ('.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.wmv')


# SECURITY: pop only THIS job's entry from a work queue.
# A blind queue.pop(0) in a handler's `finally` deletes whatever happens to be at
# the head - i.e. another user's queued job - when this task was already dequeued,
# was never enqueued, or when two handlers finish out of order.
def drop_queue_item(queue, task_id):
    if not queue:
        return

    def _ident(item):
        # queue items are tuples whose last element is the task id, or a bare id
        return item[-1] if isinstance(item, tuple) else item

    if _ident(queue[0]) == task_id:
        queue.pop(0)
        return
    queue[:] = [item for item in queue if _ident(item) != task_id]

# SECURITY: Server-side authoritative storage for button ownership
PENDING_BUTTONS = {}

def register_pending_button(chat_id: int, message_id: int, owner_id: int, src_id: int):
    now = time.time()
    stale = [k for k, v in list(PENDING_BUTTONS.items()) if now - v.get("ts", 0) > 3600]
    for k in stale:
        PENDING_BUTTONS.pop(k, None)
    PENDING_BUTTONS[(int(chat_id), int(message_id))] = {
        "owner": int(owner_id),
        "src": int(src_id),
        "ts": now
    }

def get_pending_button(chat_id: int, message_id: int):
    now = time.time()
    info = PENDING_BUTTONS.get((int(chat_id), int(message_id)))
    if info and now - info.get("ts", 0) <= 3600:
        return info
    return None


async def download_thumbnail():
    async with aiohttp.ClientSession() as session:
        async with session.get(THUMB_URL) as resp:
            if resp.status == 200:
                with open(THUMB_PATH, 'wb') as f:
                    f.write(await resp.read())
            else:
                raise Exception(f"Failed to download thumbnail. HTTP Status: {resp.status}")


def clear_directory(directory):
    """Remove a task directory's contents without shell commands."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


# === Global crop queue worker ===
_crop_worker_task = None

async def _crop_worker():
    global _crop_worker_task
    try:
        while crop:
            item = crop[0]
            if len(item) == 4:
                message, user_id, ratio, task_id = item
            else:
                message, user_id, ratio = item
                task_id = None

            if task_id and task_manager.is_cancelled(task_id):
                try:
                    await task_manager.complete(task_id)
                except Exception:
                    pass
                if crop and crop[0] is item:
                    crop.pop(0)
                continue

            try:
                clear_directory(CROP_LOCATION)
                await add_crop_task(message, user_id, ratio, task_id)
            except asyncio.CancelledError:
                LOGGER.info(f"[Crop] Task {task_id} cancelled.")
            except Exception as e:
                LOGGER.error(f"[Crop] Error: {e}")
            finally:
                if task_id:
                    try:
                        await task_manager.complete(task_id)
                    except Exception:
                        pass
                if crop and crop[0] is item:
                    crop.pop(0)
    finally:
        _crop_worker_task = None

def _ensure_crop_worker():
    global _crop_worker_task
    if _crop_worker_task is None or _crop_worker_task.done():
        _crop_worker_task = asyncio.create_task(_crop_worker())

async def on_crop_task_complete():
    """Trigger crop queue runner."""
    _ensure_crop_worker()

async def add_crops(message: Message, user_id: int, ratio: str, task_id: str = None):
    """Executes crop worker for queue items."""
    _ensure_crop_worker()


# === Shared compress worker infrastructure ===

async def _auto_del(msg, delay: float = 30.0):
    """Fire-and-forget transient message cleanup."""
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass

async def _register_compress_task(message: Message, user_id: int, res_tag: str):
    """Shared entry for compress queues: manager register (dedupe) + status.

    Returns task_id or None (rejected -> error already replied)."""
    media = message.video or message.document
    file_uid = getattr(media, "file_unique_id", "") if media else str(message.id)
    title = ((getattr(media, "file_name", None) or "video").strip() or "video")
    task_id, err = await task_manager.register(
        user_id, message.chat.id, "encode", title,
        build_dedupe_key(user_id, file_uid, "encode", res_tag),
        link=getattr(message, "link", "") or "",
        res=res_tag,
    )
    if not task_id:
        try:
            await message.reply_text(err)
        except Exception:
            pass
        return None
    try:
        from bot.group_status import announce_task
        await announce_task(message)
    except Exception as e:
        LOGGER.warning(f"status announce failed: {e}")
    return task_id

_workers: dict[str, asyncio.Task] = {}

async def _process_compress_queue(q_name: str, queue_list: list, location: str, handler_fn):
    try:
        while queue_list:
            item = queue_list[0]
            message, user_id, task_id = item

            if task_id and task_manager.is_cancelled(task_id):
                try:
                    await task_manager.complete(task_id)
                except Exception:
                    pass
                if queue_list and queue_list[0] is item:
                    queue_list.pop(0)
                continue

            try:
                clear_directory(location)
                await handler_fn(message, user_id, task_id)
            except asyncio.CancelledError:
                LOGGER.info(f"[{q_name}] Task {task_id} cancelled.")
            except Exception as e:
                LOGGER.error(f"[{q_name}] Task {task_id} failed: {e}")
            finally:
                if task_id:
                    try:
                        await task_manager.complete(task_id)
                    except Exception:
                        pass
                if queue_list and queue_list[0] is item:
                    queue_list.pop(0)
    finally:
        _workers.pop(q_name, None)

def _ensure_worker(q_name: str, queue_list: list, location: str, handler_fn):
    t = _workers.get(q_name)
    if t is None or t.done():
        _workers[q_name] = asyncio.create_task(_process_compress_queue(q_name, queue_list, location, handler_fn))

#-----------------MULTI-ENC------------------#

async def on_task_complete4():
    _ensure_worker("all", data4, DOWNLOAD_LOCATION4, incoming_compress_message_f4)

async def _run_task4(message: Message, user_id: int, task_id: str):
    _ensure_worker("all", data4, DOWNLOAD_LOCATION4, incoming_compress_message_f4)

async def add_task4(message: Message, user_id: int) -> bool:
    """Queue a multi-resolution job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "all")
    if not task_id:
        return False
    data4.append((message, user_id, task_id))
    _ensure_worker("all", data4, DOWNLOAD_LOCATION4, incoming_compress_message_f4)
    return True

#-------------------144p--------------------#

async def on_task_complete5():
    _ensure_worker("144p", data5, DOWNLOAD_LOCATION5, incoming_compress_message_f5)

async def _run_task5(message: Message, user_id: int, task_id: str):
    _ensure_worker("144p", data5, DOWNLOAD_LOCATION5, incoming_compress_message_f5)

async def add_task5(message: Message, user_id: int) -> bool:
    """Queue a 144p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "144p")
    if not task_id:
        return False
    data5.append((message, user_id, task_id))
    _ensure_worker("144p", data5, DOWNLOAD_LOCATION5, incoming_compress_message_f5)
    return True

#------------------240p---------------------#

async def on_task_complete6():
    _ensure_worker("240p", data6, DOWNLOAD_LOCATION6, incoming_compress_message_f6)

async def _run_task6(message: Message, user_id: int, task_id: str):
    _ensure_worker("240p", data6, DOWNLOAD_LOCATION6, incoming_compress_message_f6)

async def add_task6(message: Message, user_id: int) -> bool:
    """Queue a 240p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "240p")
    if not task_id:
        return False
    data6.append((message, user_id, task_id))
    _ensure_worker("240p", data6, DOWNLOAD_LOCATION6, incoming_compress_message_f6)
    return True

#-----------------360p--------------------#

async def on_task_complete7():
    _ensure_worker("360p", data7, DOWNLOAD_LOCATION7, incoming_compress_message_f7)

async def _run_task7(message: Message, user_id: int, task_id: str):
    _ensure_worker("360p", data7, DOWNLOAD_LOCATION7, incoming_compress_message_f7)

async def add_task7(message: Message, user_id: int) -> bool:
    """Queue a 360p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "360p")
    if not task_id:
        return False
    data7.append((message, user_id, task_id))
    _ensure_worker("360p", data7, DOWNLOAD_LOCATION7, incoming_compress_message_f7)
    return True

#-------------------480p--------------------#

async def on_task_complete():
    _ensure_worker("480p", data, DOWNLOAD_LOCATION, incoming_compress_message_f)

async def _run_task(message: Message, user_id: int, task_id: str):
    _ensure_worker("480p", data, DOWNLOAD_LOCATION, incoming_compress_message_f)

async def add_task(message: Message, user_id: int) -> bool:
    """Queue a 480p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "480p")
    if not task_id:
        return False
    data.append((message, user_id, task_id))
    _ensure_worker("480p", data, DOWNLOAD_LOCATION, incoming_compress_message_f)
    return True

#-------------------720p--------------------#

async def on_task_complete1():
    _ensure_worker("720p", data1, DOWNLOAD_LOCATION1, incoming_compress_message_f1)

async def _run_task1(message: Message, user_id: int, task_id: str):
    _ensure_worker("720p", data1, DOWNLOAD_LOCATION1, incoming_compress_message_f1)

async def add_task1(message: Message, user_id: int) -> bool:
    """Queue a 720p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "720p")
    if not task_id:
        return False
    data1.append((message, user_id, task_id))
    _ensure_worker("720p", data1, DOWNLOAD_LOCATION1, incoming_compress_message_f1)
    return True

#------------------1080p---------------------#

async def on_task_complete2():
    _ensure_worker("1080p", data2, DOWNLOAD_LOCATION2, incoming_compress_message_f2)

async def _run_task2(message: Message, user_id: int, task_id: str):
    _ensure_worker("1080p", data2, DOWNLOAD_LOCATION2, incoming_compress_message_f2)

async def add_task2(message: Message, user_id: int) -> bool:
    """Queue a 1080p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "1080p")
    if not task_id:
        return False
    data2.append((message, user_id, task_id))
    _ensure_worker("1080p", data2, DOWNLOAD_LOCATION2, incoming_compress_message_f2)
    return True

#-----------------2160p--------------------#

async def on_task_complete3():
    _ensure_worker("4k", data3, DOWNLOAD_LOCATION3, incoming_compress_message_f3)

async def _run_task3(message: Message, user_id: int, task_id: str):
    _ensure_worker("4k", data3, DOWNLOAD_LOCATION3, incoming_compress_message_f3)

async def add_task3(message: Message, user_id: int) -> bool:
    """Queue a 2160p job. Returns False when rejected (duplicate/maintenance)."""
    task_id = await _register_compress_task(message, user_id, "4k")
    if not task_id:
        return False
    data3.append((message, user_id, task_id))
    _ensure_worker("4k", data3, DOWNLOAD_LOCATION3, incoming_compress_message_f3)
    return True

#----------------Utility-------------------#


async def convert_to_mkv(input_path, output_path):
    """Convert video file to MKV format (exclude unsupported streams)"""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found in PATH")

    cmd = [
        ffmpeg,
        '-hide_banner',
        '-i', input_path,
        '-map', '0:v?',  # video
        '-map', '0:a?',  # audio
        '-map', '0:s?',  # subtitles 
        '-c', 'copy',
        '-f', 'matroska',
        '-y',
        output_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        raise RuntimeError(f"MKV conversion failed: {error_msg}")

    return output_path


cancel_tasks = {}


async def update_progress_ui(
    current: int,
    total: int,
    client,
    stage: str,
    message,
    start_time: float,
    tag: str = ""
):
    if total == 0:
        total = 1
    now = time.time()
    elapsed = now - start_time
    speed = current / elapsed if elapsed else 0.001
    eta = round((total - current) / speed)
    percentage = round((current / total) * 100, 2)

    # Visual progress bar
    filled = math.floor(percentage / 10)
    progress_bar = "●" * filled + "○" * (10 - filled)

    mins, secs = divmod(eta, 60)
    eta_str = f"{mins}m, {secs}s"

    text = (
        f"<blockquote><b>{stage.upper()} ɪɴ ᴘʀᴏɢʀᴇss</b> </blockquote>\n"
        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
        f"<blockquote><b>ᴘʀᴏɢʀᴇss:</b> {percentage}%</blockquote>\n"
        f"<blockquote><code>[{progress_bar}]</code></blockquote>"
    )

    # Inline cancel button
    cancel_key = f"{message.chat.id}_{message.id}_{tag}"
    cancel_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌", callback_data=f"cancel_{cancel_key}")]
    ])

    try:
        await message.edit_text(text, reply_markup=cancel_btn)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await message.edit_text(text, reply_markup=cancel_btn)
        except:
            pass
    except:
        pass


async def simulate_ffmpeg_progress(duration, client, message, tag="embed"):
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed >= duration:
            break
        current = min(elapsed, duration)
        await update_progress_ui(
            current=current,
            total=duration,
            client=client,
            stage="Embedding",
            message=message,
            start_time=start,
            tag=tag
        )
        await asyncio.sleep(3)


def ts(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        ((str(days) + "d, ") if days else "")
        + ((str(hours) + "h, ") if hours else "")
        + ((str(minutes) + "m, ") if minutes else "")
        + ((str(seconds) + "s, ") if seconds else "")
        + ((str(milliseconds) + "ms, ") if milliseconds else "")
    )
    return tmp[:-2]

def checkKey(dict, key):
  if key in dict.keys():
    return True
  else:
    return False

#async def on_task_complete():
    #del data[0]
    #if len(data) > 0:
      #await add_task(data[0])


# -------------------------------
# Button Markup Builder
# -------------------------------
def build_media_keyboard(selected=None, user_id=None):
    selected = selected or "video"

    def mark(label, value):
        return f"✅ {label}" if value == selected.lower() else label

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                mark("Dᴏᴄᴜᴍᴇɴᴛ", "document"),
                callback_data=f"setmedia_document:{user_id}"
            ),
            InlineKeyboardButton(
                mark("Vɪᴅᴇᴏ", "video"),
                callback_data=f"setmedia_video:{user_id}"
            ),
        ],
        [InlineKeyboardButton("Cʟᴏsᴇ", callback_data="close")]
    ])
# -------------------------------

# --------------------------
# SPOILER KEYBOARD BUILDER
# --------------------------

def build_spoiler_keyboard(selected: bool = False, user_id: int = None):
    """
    Build inline keyboard for spoiler toggle.
    selected: current spoiler state (True/False).
    """
    def mark(label, value: bool):
        return f"✅ {label}" if value == selected else label

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                mark("ᴏɴ", True),
                callback_data=f"spoiler_true:{user_id}"
            ),
            InlineKeyboardButton(
                mark("ᴏғғ", False),
                callback_data=f"spoiler_false:{user_id}"
            ),
        ],
        [InlineKeyboardButton("⛔ Cʟᴏsᴇ", callback_data="close")]
    ])

# ✅ Metadata button builder (spoiler-style)
def build_metadata_keyboard(current: str, user_id: int):
    """Build metadata control keyboard with right/cross indicators"""
    is_on = current.lower() == "on"
    is_off = current.lower() == "off"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Oɴ {'✓' if is_on else '✗'}",
                callback_data=f"metadata_on:{user_id}"
            ),
            InlineKeyboardButton(
                f"Oғғ {'✓' if is_off else '✗'}",
                callback_data=f"metadata_off:{user_id}"
            ),
        ],
        [
            InlineKeyboardButton("Mᴇᴛᴀᴅᴀᴛᴀ Hᴇʟᴘ", callback_data=f"metadata_info:{user_id}")
        ]
    ])

# -------------- UPLOADING ------------------#

def build_upload_keyboard(selected=None, user_id=None, channel_id=None):
    selected = selected or "group"

    def mark(label, value):
        return f"✅ {label}" if value == selected.lower() else label

    buttons = [
        [
            InlineKeyboardButton(
                mark("DM", "dm"),
                callback_data=f"upload_dm:{user_id}"
            ),
            InlineKeyboardButton(
                mark("Channel", "channel"),
                callback_data=f"upload_channel:{user_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                mark("This Group", "group"),
                callback_data=f"upload_group:{user_id}"
            )
        ],
        [InlineKeyboardButton("Cʟᴏsᴇ", callback_data="close")]
    ]

    # If user hasn’t set channel, disable "Channel" button
    if not channel_id:
        buttons[0][1] = InlineKeyboardButton(
            "❌ Set Channel First",
            callback_data="upload_nochannel"
        )

    return InlineKeyboardMarkup(buttons)






# -------------------------------


def get_video_duration(file_path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        duration_str = result.stdout.decode().strip()
        return int(float(duration_str))
    except Exception as e:
        print(f"Failed to get duration: {e}")
        return 0

def get_video_dimensions(file_path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",  # first video stream
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        dimensions = result.stdout.decode().strip()
        if "x" in dimensions:
            width, height = map(int, dimensions.split("x"))
            return width, height
        return 0, 0
    except Exception as e:
        print(f"Failed to get dimensions: {e}")
        return 0, 0

# -------------- THUMBNAIL ------------------#

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
                print("Generated thumbnail from video for PDF.")
            else:
                print("Failed to generate PDF thumbnail from video.")
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


# Utility to get duration of audio in seconds
def get_audio_duration(file_path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        duration_str = result.stdout.decode().strip()
        return int(float(duration_str))
    except Exception as e:
        print(f"Failed to get audio duration: {e}")
        return 0

# -------------- UPLOADING ------------------#

def clean_subtitle_text(text):
    return re.sub(r"<.*?>", "", text).strip()

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

# Auto-delete helper
async def delete_after(delay, msg: Message):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass


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

async def safe_send(func, *args, retries=5, backoff=2, **kwargs):

    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = min(e.value, 60)
            LOGGER.warning(f"FloodWait: sleeping for {wait_time}s...")
            await asyncio.sleep(wait_time)
        except (pyrogram.errors.RPCError, pyrogram.errors.FloodWait, pyrogram.errors.MessageNotModified) as e:
            # transient Pyrogram errors
            wait = backoff * (attempt + 1)
            LOGGER.warning(f"Pyrogram error '{e}', retrying in {wait}s (attempt {attempt+1}/{retries})")
            await asyncio.sleep(wait)
        except Exception as e:
            # special handling for empty/cannot copy messages
            err_msg = str(e).lower()
            if "empty messages cannot be copied" in err_msg or "message not found" in err_msg:
                wait = backoff * (attempt + 1)
                LOGGER.warning(f"Message not ready: {e}, retrying in {wait}s (attempt {attempt+1}/{retries})")
                await asyncio.sleep(wait)
            elif attempt == retries - 1:
                raise e
            else:
                wait = backoff * (attempt + 1)
                LOGGER.warning(f"Unknown error: {e}, retrying in {wait}s (attempt {attempt+1}/{retries})")
                await asyncio.sleep(wait)




