# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, MERGE_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.response import *
from bot.split_videos import *
from bot.helper_funcs.display_progress import *
from bot.helper_funcs.split_uploader import (
    smart_split_and_upload,
    get_effective_uploader_and_limit,
)
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
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram.errors import FloodWait
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from bot.helper_funcs.media_caption import enhance_media_caption
import asyncio
import os, shutil
import time
import subprocess
from bot.localisation import Localisation
from asyncio.exceptions import TimeoutError
from bot.premium import *
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

merge_queue = []
user_merge_sessions = {}

MAX_VIDEOS = 12
SESSION_TIMEOUT = 300  # seconds


@app.on_message(filters.command(["merge", f"merge@{BOT_USERNAME}"]))
async def merge_command(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    if not message.from_user:
        return

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
    # Already in merge session
    if user_id in user_merge_sessions:
        msg = await message.reply("⚠️ Yᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴍᴇʀɢᴇ sᴇssɪᴏɴ.")
        asyncio.create_task(delete_after(30, msg))
        return

    # Start new session
    user_merge_sessions[user_id] = True
    msg = await message.reply(
        "📥 Sᴇɴᴅ ᴜᴘ ᴛᴏ 𝟷2 ᴠɪᴅᴇᴏs.\nWʜᴇɴ ᴅᴏɴᴇ, ᴘʀᴇss MERGE.\nTᴏ ᴄᴀɴᴄᴇʟ, ᴘʀᴇss CANCEL.",
        reply_markup=ReplyKeyboardMarkup([["MERGE", "CANCEL"]], resize_keyboard=True)
    )
    asyncio.create_task(delete_after(120, msg))

    try:
        await wait_for_merge_inputs(client, message, user_id)
    except TimeoutError:
        msg = await message.reply("⌛ Sᴇssɪᴏɴ ᴛɪᴍᴇᴏᴜᴛ. Pʟᴇᴀsᴇ sᴛᴀʀᴛ ᴀɢᴀɪɴ.", reply_markup=ReplyKeyboardRemove())
        asyncio.create_task(delete_after(30, msg))
    finally:
        user_merge_sessions.pop(user_id, None)


async def wait_for_merge_inputs(client: Client, origin_msg: Message, user_id: int):
    chat_id = origin_msg.chat.id
    videos = []
    processed_groups = set()

    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        remaining = int(SESSION_TIMEOUT - elapsed)
        if remaining <= 0:
            raise TimeoutError("Session timed out")

        try:
            incoming = await client.listen(chat_id=chat_id, user_id=user_id, timeout=remaining)
        except asyncio.TimeoutError:
            raise TimeoutError("Session timed out")

        if not incoming or not incoming.from_user or incoming.from_user.id != user_id:
            continue

        # ---- Text input ----
        if incoming.text:
            cmd = incoming.text.strip().upper()
            if cmd == "CANCEL":
                await incoming.reply("❌ Mᴇʀɢᴇ sᴇssɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ.", reply_markup=ReplyKeyboardRemove())
                return
            elif cmd == "MERGE":
                if not videos:
                    await incoming.reply("⚠️ Nᴏ ᴠɪᴅᴇᴏs ʀᴇᴄᴇɪᴠᴇᴅ ʏᴇᴛ.")
                    continue
                elif len(videos) < 2:
                    await incoming.reply("⚠️ Aᴛ ʟᴇᴀsᴛ 2 ᴠɪᴅᴇᴏs ᴀʀᴇ ʀᴇQᴜɪʀᴇᴅ ᴛᴏ ᴘᴇʀғᴏʀᴍ ᴍᴇʀɢᴇ.")
                    continue

                task_id, err = await task_manager.register(
                    user_id, chat_id, "merge", f"Merged ({len(videos)} videos)",
                    build_dedupe_key(user_id, str(origin_msg.id), "merge", ""),
                    link=getattr(origin_msg, "link", "") or "",
                )
                if not task_id:
                    await incoming.reply(err, reply_markup=ReplyKeyboardRemove())
                    return

                await announce_task(origin_msg)
                await incoming.reply("✅ ᴍᴇʀɢᴇ sᴛᴀʀᴛᴇᴅ!", reply_markup=ReplyKeyboardRemove())

                merge_queue.append((client, origin_msg, [v.id for v in videos], task_id))
                if len(merge_queue) == 1:
                    await process_merge_task(*merge_queue[0])
                return

        # ---- Media input ----
        new_videos = []

        if incoming.media_group_id:
            # Handle albums
            if incoming.media_group_id in processed_groups:
                continue
            processed_groups.add(incoming.media_group_id)

            msgs = await client.get_media_group(chat_id=chat_id, message_id=incoming.id)
            for msg in msgs:
                media = msg.video or msg.document
                if media:
                    new_videos.append(msg)

        else:
            # Handle single video(s), but batch if more come in quickly
            media = incoming.video or incoming.document
            if media:
                new_videos.append(incoming)

                # short buffer window to catch more videos
                try:
                    while True:
                        nxt = await asyncio.wait_for(client.listen(chat_id=chat_id, user_id=user_id), timeout=1.0)
                        if nxt.video or nxt.document:
                            new_videos.append(nxt)
                        else:
                            # put it back into queue if not a video
                            client._queue[chat_id].put_nowait(nxt)
                            break
                except asyncio.TimeoutError:
                    pass

        if not new_videos:
            continue

        # Add files while respecting MAX_VIDEOS
        for msg in new_videos:
            if len(videos) >= MAX_VIDEOS:
                warn_msg = await msg.reply("⚠️ Yᴏᴜ ᴄᴀɴ ᴏɴʟʏ ᴍᴇʀɢᴇ ᴜᴘ ᴛᴏ 𝟷𝟸 ᴠɪᴅᴇᴏs.")
                asyncio.create_task(delete_after(30, warn_msg))
                break
            videos.append(msg)

        # Single confirmation for the batch (sizes come from Telegram metadata —
        # no download/probe involved, so this stays in the millisecond range)
        total_bytes = 0
        for _m in videos:
            _media = _m.video or _m.document
            if _media and _media.file_size:
                total_bytes += _media.file_size
        # Predict with the SAME limit smart_split_and_upload will apply
        # (2000 MiB free / 4000 MiB premium string session).
        _uploader, tg_limit, _is_prem = await get_effective_uploader_and_limit()
        size_text = f"\nEstimated merged size: {humanbytes(total_bytes)}"
        if total_bytes > tg_limit:
            size_text += "\n⚠️ This merged video will exceed Telegram upload limit so it will perform default split."
        added_msg = await incoming.reply(f"✅ Aᴅᴅᴇᴅ **{len(videos)}** ғɪʟᴇ(ꜱ) ғᴏʀ ᴍᴇʀɢᴇ.{size_text}")
        asyncio.create_task(delete_after(30, added_msg))




# Auto-delete helper
async def delete_after(delay, msg: Message):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass


async def process_merge_task(client, user_msg: Message, videos: list, task_id: str = None):
    try:
        user_id = user_msg.from_user.id
        chat_id = user_msg.chat.id

        if task_id and task_manager.is_cancelled(task_id):
            return

        download_dir = os.path.abspath(f"{MERGE_LOCATION}/{user_id}/merge")
        os.makedirs(download_dir, exist_ok=True)

        msg = None
        if not task_id:
            msg = await safe_send(user_msg.reply, "📥 Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇs...")

        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)

        async def download_and_convert(i, msg_id):
            try:
                msg_obj = await safe_send(client.get_messages, chat_id, msg_id)
                media = msg_obj.video or msg_obj.document
                # SECURITY: media.file_name is user-supplied - strip any path component before joining
                filename = safe_media_name(media.file_name or f"part_{i}")
                raw_path = os.path.join(download_dir, f"raw_{i}_{filename}")
                mkv_path = os.path.join(download_dir, f"{i}.mkv")

                dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
                try:
                    async with dl_ctx:
                        await client.download_media(
                            msg_obj,
                            file_name=raw_path,
                            progress=(make_manager_progress(task_id) if task_id else progress_for_pyrogram),
                            progress_args=(client, f"Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғɪʟᴇ {i}...", msg, time.time())
                        )
                except (asyncio.CancelledError, Exception) as e:
                    if task_id and task_manager.is_cancelled(task_id):
                        return None
                    raise e

                ext = os.path.splitext(filename)[1].lower()
                if ext == ".mkv":
                    if msg:
                        await safe_send(msg.edit, f"✅ Sᴋɪᴘᴘɪɴɢ ᴄᴏɴᴠᴇʀsɪᴏɴ ғᴏʀ ғɪʟᴇ {i} (ᴀʟʀᴇᴀᴅʏ MKV)")
                    os.rename(raw_path, mkv_path)
                else:
                    if msg:
                        await safe_send(msg.edit, f"🛠 Cᴏɴᴠᴇʀᴛɪɴɢ ғɪʟᴇ {i} ᴛᴏ MKV...")
                    await convert_to_mkv(raw_path, mkv_path)

                if not os.path.exists(mkv_path) or os.path.getsize(mkv_path) == 0:
                    raise Exception(f"File {i} conversion failed")

                return mkv_path
            except Exception as e:
                if msg:
                    await safe_send(msg.edit, f"❌ Eʀʀᴏʀ ɪɴ ғɪʟᴇ {i}:\n`{e}`")
                return None

        tasks = [download_and_convert(i + 1, vid_id) for i, vid_id in enumerate(videos)]
        results = await asyncio.gather(*tasks)
        input_files = [os.path.abspath(f) for f in results if f]

        if not input_files:
            if msg:
                await safe_send(msg.edit, "❌ Nᴏ ᴠᴀʟɪᴅ ғɪʟᴇs ᴛᴏ ᴍᴇʀɢᴇ.")
            return

        if task_id and task_manager.is_cancelled(task_id):
            return

        # prepare concat list
        input_txt = os.path.join(download_dir, "input.txt")
        with open(input_txt, "w") as f:
            for file_path in input_files:
                f.write(f"file '{file_path}'\n")

        output_file = os.path.join(download_dir, "merged.mkv")
        progress_path = os.path.join(download_dir, "merge_progress.txt")

        if os.path.exists(progress_path):
            os.remove(progress_path)

        if msg:
            await safe_send(msg.edit, "🛠 Mᴇʀɢɪɴɢ ғɪʟᴇs...")
        if task_id:
            await task_manager.set_phase(task_id, PHASE_PROCESSING)

        merge_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", input_txt,
            "-map", "0", "-c", "copy",
            "-progress", progress_path,
            output_file
        ]

        MERGE_START = time.time()
        # SECURITY: stderr is drained concurrently below. An undrained PIPE fills its
        # 64KB buffer, ffmpeg then blocks on write and process.wait() never returns.
        process = await asyncio.create_subprocess_exec(
            *merge_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        if task_id:
            task_manager.register_process(task_id, process)

        stderr_buf = bytearray()

        async def _drain_stderr():
            try:
                while True:
                    chunk = await process.stderr.read(65536)
                    if not chunk:
                        break
                    stderr_buf.extend(chunk)
            except Exception:
                pass

        async def parse_merge_progress():
            last_percent = -1
            bar_length = 12
            total_duration = sum(get_video_duration(f) for f in input_files)

            # SECURITY: hard bound on this loop - asyncio.gather() below waits for it,
            # so an endless spin here hangs the whole job forever.
            deadline = MERGE_START + ((total_duration * 3 + 120) if total_duration else 600)
            zero_duration_ticks = 0

            while True:
                await asyncio.sleep(2)
                if time.time() > deadline:
                    LOGGER.warning("FFmpeg merge progress reader hit its deadline")
                    break
                if not os.path.exists(progress_path):
                    if process.returncode is not None:
                        break
                    continue
                try:
                    with open(progress_path, "r") as f:
                        lines = f.readlines()

                    progress_data = dict(line.strip().split("=", 1) for line in lines if "=" in line)
                    out_time_us = int(progress_data.get("out_time_us", "0").replace("N/A", "0"))
                    out_time = out_time_us / 1_000_000

                    if total_duration == 0:
                        # SECURITY: unknown duration - bound the wait instead of spinning
                        zero_duration_ticks += 1
                        if zero_duration_ticks >= 15 or process.returncode is not None:
                            break
                        continue

                    percent = min(100, (out_time / total_duration) * 100)
                    percent_display = round(percent, 2)

                    filled = int(bar_length * percent / 100)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    elapsed = time.time() - MERGE_START
                    eta = (elapsed * (100 - percent)) / (percent + 1e-5)
                    eta_str = TimeFormatter(eta * 1000)

                    progress_text = (
                        f"<blockquote><b>Mᴇʀɢɪɴɢ ғɪʟᴇs</b></blockquote>\n"
                        f"<code>[{bar}]</code>\n"
                        f"<b>ᴘʀᴏɢʀᴇss:</b> {percent_display:.2f}%\n"
                        f"<blockquote><b>ᴛɪᴍᴇ ʟᴇғᴛ:</b> {eta_str}</blockquote>\n"
                    )

                    if percent_display != last_percent:
                        if task_id:
                            await task_manager.update_progress(
                                task_id, percent_display, eta=eta_str
                            )
                        elif msg:
                            await safe_send(msg.edit, progress_text)
                        last_percent = percent_display

                    if progress_data.get("progress") == "end":
                        break
                    # ffmpeg is gone but never wrote "progress=end" - stop waiting
                    if process.returncode is not None:
                        break
                except Exception as e:
                    LOGGER.warning(f"FFmpeg merge progress parse error: {e}")
                    continue

        await asyncio.gather(parse_merge_progress(), process.wait(), _drain_stderr())

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            if msg:
                await safe_send(
                    msg.edit,
                    "❌ ᴍᴇʀɢᴇ ғᴀɪʟᴇᴅ\n" + bytes(stderr_buf).decode(errors="replace"),
                )
            return

        if task_id and task_manager.is_cancelled(task_id):
            return

        try:
            metadata_status = await db.get_metadata(user_id)
            if metadata_status and metadata_status.lower() == "on":
                if msg:
                    await flood_retry(msg.edit, "🧩 Aᴅᴅɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...")
                meta_output = os.path.join(MERGE_LOCATION, f"meta_{os.path.basename(output_file)}")
                output_file = await add_metadata(output_file, meta_output, user_id)
        except Exception as meta_err:
            LOGGER.warning(f"Metadata addition skipped: {meta_err}")

        if msg:
            await safe_send(msg.edit, "📤 Uᴘʟᴏᴀᴅɪɴɢ ᴍᴇʀɢᴇᴅ ᴠɪᴅᴇᴏ...")

        file_path = output_file
        file_size = os.path.getsize(file_path)
        caption = "🔥 ᴍᴇʀɢᴇ ᴅᴏɴᴇ — ᴇɴᴊᴏʏ!"

        thumb = await db.get_thumbnail(user_id)
        spoiler_enabled = await db.get_user_spoiler(user_id)
        media_preference = await db.get_media_preference(user_id) or "video"
        caption = enhance_media_caption(file_path, caption, media_preference)

        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_preference == "video":
            thumb_path = await process_thumbnail(None, video_path=file_path)
        else:
            thumb_path = await process_thumbnail_doc(None, video_path=file_path)

        duration = get_video_duration(file_path) if media_preference == "video" else None

        # Phase is owned by smart_split_and_upload: it sets PHASE_SPLITTING while
        # it carves parts out and PHASE_UPLOADING per part, so the status card
        # reads "Preparing split parts" instead of claiming to upload at 0%.
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            await smart_split_and_upload(
                client=client,
                message=user_msg,
                file_path=file_path,
                status_msg=(UploadSink(task_id) if task_id else msg),
                caption=caption,
                thumb_path=thumb_path,
                duration=int(duration) if duration else None,
                user_id=user_id,
                reply_to_id=user_msg.id,
                task_id=task_id,
            )
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    except Exception as e:
        await safe_send(user_msg.reply, f"❌ Merge failed:\n`{e}`")
    finally:
        try:
            shutil.rmtree(download_dir)
        except:
            pass

        if task_id:
            await task_manager.complete(task_id)

        # SECURITY: pop only this task's entry - blind pop(0) deletes another user's job
        drop_queue_item(merge_queue, task_id)
        while merge_queue:
            item = merge_queue[0]
            tid = item[-1] if isinstance(item, tuple) else None
            if tid and task_manager.is_cancelled(tid):
                await task_manager.complete(tid)
                merge_queue.pop(0)
                continue
            await process_merge_task(*item)
            break


async def safe_send(func, *args, retries=5, backoff=2, **kwargs):
    
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = min(e.value, 60)
            LOGGER.warning(f"FloodWait: sleeping for {wait_time}s...")
            await asyncio.sleep(wait_time)
        except (pyrogram.errors.RPCError, pyrogram.errors.FloodWait, pyrogram.errors.MessageNotModified) as e:
            wait = backoff * (attempt + 1)
            LOGGER.warning(f"Pyrogram error '{e}', retrying in {wait}s (attempt {attempt+1}/{retries})")
            await asyncio.sleep(wait)
        except Exception as e:
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
