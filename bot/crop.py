# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, CROP_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.utils import *
from bot.response import *
from bot.helper_funcs.display_progress import *
from bot.helper_funcs.split_uploader import smart_split_and_upload
from bot.plugins.status_message_fn import (
    eval_message_f,
    exec_message_f,
    upload_log_file
)
from bot.fsub import *
from bot.premium import *
from bot.localisation import Localisation
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
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from bot.helper_funcs.media_caption import enhance_media_caption
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode
import asyncio, os, time, subprocess
from pathlib import Path
from PIL import Image


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)


async def safe_send(func, *args, **kwargs):
    """Run Telegram send functions safely with FloodWait handling."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            raise

def get_video_dimensions(file_path: str):
    """
    Returns (width, height) of video using ffprobe.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        dims = result.stdout.decode().strip()
        if "x" in dims:
            w, h = dims.split("x")
            return int(w), int(h)
    except Exception as e:
        print(f"get_video_dimensions error: {e}")
    return None, None


def detect_aspect_ratio(width, height):
    """
    Map width/height to nearest standard aspect ratio string.
    """
    if not width or not height:
        return "16:9"  # default fallback

    ratio = width / height
    aspect_map = {
        "1:1": 1.0,
        "16:9": 16/9,
        "9:16": 9/16,
        "4:5": 4/5,
        "21:9": 21/9
    }

    # Find closest match
    closest = min(aspect_map.items(), key=lambda kv: abs(kv[1] - ratio))
    return closest[0]


# Example /crop command
@app.on_message(filters.command(["crop", f"crop@{BOT_USERNAME}"]))
async def crop_handler(app: Client, message: Message):
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
        return await message.reply_text(
            "<blockquote>Reply to a video or document with /crop to start cropping.</blockquote>"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "1:1 (Square)",
                callback_data=f"crop:1_1:{message.from_user.id}:{message.reply_to_message.id}"
            ),
            InlineKeyboardButton(
                "16:9 (Widescreen)",
                callback_data=f"crop:16_9:{message.from_user.id}:{message.reply_to_message.id}"
            )
        ],
        [
            InlineKeyboardButton(
                "9:16 (Vertical)",
                callback_data=f"crop:9_16:{message.from_user.id}:{message.reply_to_message.id}"
            ),
            InlineKeyboardButton(
                "4:5 (Portrait)",
                callback_data=f"crop:4_5:{message.from_user.id}:{message.reply_to_message.id}"
            )
        ],
        [
            InlineKeyboardButton(
                "21:9 (Cinema)",
                callback_data=f"crop:21_9:{message.from_user.id}:{message.reply_to_message.id}"
            ),
            InlineKeyboardButton("❌ Cancel", callback_data="close")
        ]
    ])

    sent_crop = await message.reply_to_message.reply_text(
        "<b>🎬 Choose an aspect ratio to crop:</b>",
        reply_markup=keyboard
    )
    if sent_crop and message.from_user and message.reply_to_message:
        register_pending_button(sent_crop.chat.id, sent_crop.id, message.from_user.id, message.reply_to_message.id)


async def add_crop_task(update: Message, user_id: int, ratio: str, task_id: str = None):
    """Handles video stretching (resize to ratio) with merge-style upload system,
    and sends the result to user's preferred upload destination (dm/channel/group).
    """
    if task_id and task_manager.is_cancelled(task_id):
        return

    d_start = time.time()
    msg = None
    if not task_id:
        msg = await safe_send(update.reply_text, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ...")

    try:
        media = update.video or update.document
        if not media:
            raise ValueError("Unsupported file type")

        # Setup paths
        download_dir = os.path.abspath(f"{CROP_LOCATION}/{user_id}/stretch_{task_id or update.id}")
        os.makedirs(download_dir, exist_ok=True)

        # SECURITY: media.file_name is user-supplied - strip any path component before joining
        original_name = safe_media_name(media.file_name or "video.mp4")
        raw_path = os.path.join(download_dir, f"raw_{original_name}")
        output_path = os.path.join(download_dir, f"stretched_{ratio}.mp4")
        progress_path = os.path.join(download_dir, f"stretch_progress.txt")

        # Download
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        try:
            async with dl_ctx:
                await update.download(
                    file_name=raw_path,
                    progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                    progress_args=(update._client, "📥 Downloading...", msg, d_start)
                )
        except (asyncio.CancelledError, Exception) as e:
            if task_id and task_manager.is_cancelled(task_id):
                return
            raise e

        if not os.path.exists(raw_path):
            raise FileNotFoundError("❌ Download failed")

        if task_id and task_manager.is_cancelled(task_id):
            return

        # Stretching filter (scale instead of crop)
        aspect_map = {
            "1_1": "1:1",
            "16_9": "16:9",
            "9_16": "9:16",
            "4_5": "4:5",
            "21_9": "21:9"
        }

        aspect = aspect_map.get(ratio, "16:9")

        # Run FFmpeg
        if os.path.exists(progress_path):
            os.remove(progress_path)

        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        ffmpeg_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-progress", progress_path,
            "-i", raw_path, "-c", "copy", "-aspect", aspect, output_path
        ]
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        if task_id:
            task_manager.register_process(task_id, process)

        async def parse_progress():
            total_duration = get_video_duration(raw_path)
            last_percent = -1
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
                    percent = min(100, (out_time / total_duration) * 100) if total_duration else 0
                    percent_display = round(percent, 2)

                    bar = "█" * int(percent/10) + "░" * (10-int(percent/10))
                    if percent_display != last_percent:
                        if task_id:
                            await task_manager.update_progress(task_id, percent_display)
                        elif msg:
                            await safe_send(msg.edit, f"📐 Rescaling [{ratio.replace('_',':')}]\n`[{bar}] {percent_display:.2f}%`")
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                except Exception:
                    continue

        await asyncio.gather(parse_progress(), process.wait())

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("❌ Stretching failed")

        if task_id and task_manager.is_cancelled(task_id):
            return

        if not task_id and msg:
            await safe_send(msg.edit, "📤 Uᴘʟᴏᴀᴅɪɴɢ...")

        # === Upload Handling (route to user's preferred destination) ===
        file_path = output_path
        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                from bot.helper_funcs.utils import add_metadata
                meta_output = os.path.join(download_dir, f"meta_{os.path.basename(output_path)}")
                output_path = await add_metadata(output_path, meta_output, user_id)
                file_path = output_path
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped in crop: {meta_err}")

        file_size = os.path.getsize(file_path)
        caption = f"✅ Stretched to {ratio.replace('_',':')} by {BOT_USERNAME}"

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            thumb_path = await update._client.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None
        width, height = get_video_dimensions(file_path) if media_preference == "video" else (None, None)

        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            await smart_split_and_upload(
                client=update._client,
                message=update,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else msg),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=update.id,
                task_id=task_id,
            )
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    except Exception as e:
        await safe_send(update.reply_text, f"❌ Stretch failed:\n`{e}`")
    finally:
        try:
            shutil.rmtree(download_dir)
        except:
            pass
        if task_id:
            await task_manager.complete(task_id)

def get_video_display_dimensions(file_path):
    """
    Get the display (stretched) width/height, considering SAR/DAR.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,sample_aspect_ratio",
                "-of", "csv=s=x:p=0",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        data = result.stdout.decode().strip()
        if not data:
            return 0, 0

        width, height, sar = data.split("x")
        width, height = int(width), int(height)

        if ":" in sar:
            num, den = sar.split(":")
            sar = float(num) / float(den)
        else:
            sar = 1.0

        display_width = int(round(width * sar))
        display_height = height
        return display_width, display_height
    except Exception as e:
        print(f"Failed to get display dimensions: {e}")
        return 0, 0


def generate_thumbnail(video_path, output_path):
    try:
        # Get proper display dimensions (DAR)
        disp_w, disp_h = get_video_display_dimensions(video_path)
        if not disp_w or not disp_h:
            disp_w, disp_h = 640, -1  # fallback

        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:02.000", "-i", video_path,
            "-vframes", "1",
            "-vf", f"scale={disp_w}:{disp_h},setsar=1",  # stretch to DAR
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"generate_thumbnail error: {e}")
        return None


async def process_thumbnail(thumb_path, video_path=None):
    if not thumb_path or not os.path.exists(thumb_path):
        print("User thumbnail not found.")
        if video_path and os.path.exists(video_path):
            # SECURITY: "downloads/" is never created - write the thumb next to the video
            output_path = os.path.join(os.path.dirname(video_path) or ".", f"{Path(video_path).stem}_thumb.jpg")
            thumb_path = await asyncio.to_thread(
                generate_thumbnail, video_path, output_path
            )

            if thumb_path:
                print(f"Generated thumbnail stretched to DAR.")
            else:
                print("Failed to generate thumbnail from video.")
                return None
        else:
            print("No valid video path provided for thumbnail generation.")
            return None
    else:
        print("Using user-provided thumbnail.")

    try:
        img = await asyncio.to_thread(Image.open, thumb_path)
        img = await asyncio.to_thread(lambda: img.convert("RGB"))
        await asyncio.to_thread(img.save, thumb_path, "JPEG", quality=95)

        print(f"Thumbnail processed successfully (DAR preserved): {thumb_path}")
        return thumb_path

    except Exception as e:
        print(f"Thumbnail processing failed: {e}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        return None

