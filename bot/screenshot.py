# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# /ss — Screenshot generator (animated-lamp + YT-bot pattern, local-file edition).
#
#   /ss (reply to video) -> choice buttons:
#     [5 Shots] [10 Shots]            -> equal-duration frames (YT formula)
#     [10% 25% 50% 75% 90%]           -> single instant frame at % of duration
#     [Custom]                        -> comma batch: "12, 1:23, 01:02:03, 50%"
# Screenshots are a LIGHT op: registered in task_manager (status + dedupe +
# cancel) but take no download/heavy/upload slot. Frame grabs run max 3 at
# a time with -threads 1, exactly like the YT bot.

import asyncio
import os
import re
import shutil
import time

from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME, app,
)
from database import db
from bot.helper_funcs.display_progress import (
    progress_for_pyrogram,
    TimeFormatter,
    humanbytes,
)
from contextlib import nullcontext
from bot.helper_funcs.utils import get_video_duration
from bot.task_manager import task_manager, PHASE_DOWNLOADING, PHASE_PROCESSING, PHASE_UPLOADING
from bot.fsub import is_subscribed, not_joined, short_url
from bot.premium import is_premium_user
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from bot.button_styles import InlineKeyboardButton
from pyrogram.types import InlineKeyboardMarkup

SS_MAX_BATCH = 10
SS_GRAB_PARALLEL = 3
# Partial-download policy: files bigger than this with all shots in the
# first 60% of the video only fetch the needed head bytes (fast path).
SS_PARTIAL_MIN_FILE = 30 * 1024 * 1024
SS_PARTIAL_MAX_FRAC = 0.6
SS_PARTIAL_MARGIN = 1.5
SS_PARTIAL_HEADROOM = 10 * 1024 * 1024


async def safe_telegram_call(func, *args, **kwargs):
    """Local FloodWait-safe wrapper (same pattern as audio/split_videos)."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)


# --- Pure helpers (headless-testable) ---------------------------------

def parse_timestamp_spec(spec: str, duration: float) -> float | None:
    """'90' | '1:23' | '01:02:03' | '50%' -> seconds (clamped). None if bad."""
    if duration is None or duration <= 0:
        return None
    s = (spec or "").strip().replace(" ", "")
    if not s:
        return None
    try:
        if s.endswith("%"):
            pct = float(s[:-1])
            if pct < 0 or pct > 100:
                return None
            ts = duration * pct / 100.0
        elif ":" in s:
            parts = s.split(":")
            if len(parts) > 3 or not all(p for p in parts):
                return None
            nums = [float(p) for p in parts]
            if any(n < 0 for n in nums):
                return None
            ts = 0.0
            for n in nums:
                ts = ts * 60.0 + n
        else:
            ts = float(s)
            if ts < 0:
                return None
    except ValueError:
        return None
    return min(ts, max(0.0, duration - 0.1))


def parse_batch(text: str, duration: float) -> list[float]:
    """Comma-separated batch -> sorted unique clamped timestamps (max 10)."""
    out: list[float] = []
    for part in (text or "").replace(";", ",").split(","):
        ts = parse_timestamp_spec(part, duration)
        if ts is not None and not any(abs(ts - t) < 0.05 for t in out):
            out.append(ts)
        if len(out) >= SS_MAX_BATCH:
            break
    return sorted(out)


def equal_timestamps(duration: float, count: int) -> list[float]:
    """Evenly spaced frames across duration (YT-bot formula with end margin)."""
    if duration is None or duration <= 0 or count <= 0:
        return []
    end = max(0.05, float(duration) - min(0.5, float(duration) * 0.05))
    return [end * (i + 0.5) / count for i in range(count)]


def plan_timestamps(mode: str, arg, duration: float) -> tuple[list[float], str]:
    """Timestamps + label for a mode. Pure (headless-testable)."""
    if mode == "equal":
        return equal_timestamps(duration, int(arg)), f"{arg} equal shots"
    if mode == "percent":
        ts = parse_timestamp_spec(f"{arg}%", duration)
        return ([ts] if ts is not None else []), f"{arg}%"
    return parse_batch(str(arg), duration), "custom"


def partial_budget(max_ts: float, duration: float, file_size: int) -> int:
    """Head bytes worth fetching, or 0 for a full download.

    A frame at X% needs roughly the first X% of bytes (plus margin); late
    shots (or small files) always take the full file — unavoidable.
    """
    if not duration or duration <= 0 or not file_size:
        return 0
    if file_size <= SS_PARTIAL_MIN_FILE or max_ts <= 0:
        return 0
    frac = max_ts / duration
    if not 0 < frac <= SS_PARTIAL_MAX_FRAC:
        return 0
    budget = int(frac * file_size * SS_PARTIAL_MARGIN) + SS_PARTIAL_HEADROOM
    return budget if budget < file_size else 0


async def partial_fetch(client, file_obj, dest_path: str, budget: int) -> str | None:
    """Stream only the first `budget` bytes (for early-frame screenshots)."""
    import aiofiles

    written = 0
    try:
        async with aiofiles.open(dest_path, "wb") as f:
            async for chunk in client.stream_media(file_obj):
                if not chunk:
                    continue
                if written + len(chunk) > budget:
                    chunk = chunk[: max(0, budget - written)]
                await f.write(chunk)
                written += len(chunk)
                if written >= budget:
                    break
        return dest_path if written > 0 else None
    except Exception as e:
        LOGGER.warning(f"partial fetch failed: {e}")
        return None


# --- Frame grabbing (YT-bot invocation) --------------------------------

async def grab_frames(
    input_path: str, timestamps: list[float], out_dir: str, task_id: str | None = None
) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    limiter = asyncio.Semaphore(max(1, min(SS_GRAB_PARALLEL, len(timestamps) or 1)))
    total_shots = len(timestamps)
    completed_shots = 0
    count_lock = asyncio.Lock()

    async def grab_one(idx: int, ts: float) -> str | None:
        nonlocal completed_shots
        out_file = os.path.join(out_dir, f"ss_{idx + 1}.jpg")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-threads", "1",
            "-ss", f"{ts:.3f}",
            "-i", input_path,
            "-vframes", "1",
            "-vf", "scale='min(2160,iw)':-2",
            "-q:v", "2",
            "-y", out_file,
        ]
        async with limiter:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                if task_id:
                    task_manager.register_process(task_id, proc)
                _, stderr = await proc.communicate()
                if task_manager.is_cancelled(task_id) if task_id else False:
                    return None
                if proc.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                    async with count_lock:
                        completed_shots += 1
                        if task_id and total_shots > 0:
                            pct = round((completed_shots / total_shots) * 100.0, 1)
                            await task_manager.update_progress(
                                task_id, pct, detail=f"{completed_shots}/{total_shots} shots"
                            )
                    return out_file
                err = (stderr or b"").decode("utf-8", errors="ignore")[-300:]
                LOGGER.warning(f"screenshot {idx + 1} @{ts:.1f}s failed: {err}")
            except Exception as e:
                LOGGER.warning(f"screenshot {idx + 1} error: {e}")
            finally:
                if not (os.path.exists(out_file) and os.path.getsize(out_file) > 0):
                    async with count_lock:
                        completed_shots += 1
                        if task_id and total_shots > 0:
                            pct = round((completed_shots / total_shots) * 100.0, 1)
                            await task_manager.update_progress(
                                task_id, pct, detail=f"{completed_shots}/{total_shots} shots"
                            )
        return None

    results = await asyncio.gather(*[grab_one(i, ts) for i, ts in enumerate(timestamps)])
    return [p for p in results if p]


# --- Bot handlers ------------------------------------------------------

def _ss_keyboard(user_id: int, msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5️⃣ Shots", callback_data=f"vss5:{user_id}:{msg_id}"),
                InlineKeyboardButton("🔟 Shots", callback_data=f"vss10:{user_id}:{msg_id}"),
            ],
            [
                InlineKeyboardButton("10%", callback_data=f"vssp:10:{user_id}:{msg_id}"),
                InlineKeyboardButton("25%", callback_data=f"vssp:25:{user_id}:{msg_id}"),
                InlineKeyboardButton("50%", callback_data=f"vssp:50:{user_id}:{msg_id}"),
                InlineKeyboardButton("75%", callback_data=f"vssp:75:{user_id}:{msg_id}"),
                InlineKeyboardButton("90%", callback_data=f"vssp:90:{user_id}:{msg_id}"),
            ],
            [
                InlineKeyboardButton("⏱ Custom", callback_data=f"vssc:{user_id}:{msg_id}"),
                InlineKeyboardButton("❌", callback_data="close"),
            ],
        ]
    )


async def _ss_gates(client: Client, message: Message) -> int | None:
    """Shared AUTH/FSub/verify gates. Returns user_id or None (stop)."""
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        await message.reply_text("Not authorized.")
        return None
    if not message.from_user:
        return None
    user_id = message.from_user.id
    is_premium = await is_premium_user(user_id)
    if not await is_subscribed(client, user_id):
        return await not_joined(client, message) or None
    verify_status = await db.get_verify_status(user_id)
    VERIFY_EXPIRE = await db.get_verified_time()
    SHORT_URL_1 = await db.get_shortener_url1()
    SHORT_API_1 = await db.get_shortener_api1()
    SHORT_URL_2 = await db.get_shortener_url2()
    SHORT_API_2 = await db.get_shortener_api2()
    if (SHORT_API_1 and SHORT_URL_1) or (SHORT_API_2 and SHORT_URL_2):
        if (
            verify_status["is_verified"]
            and VERIFY_EXPIRE is not None
            and VERIFY_EXPIRE < (time.time() - verify_status["verified_time"])
        ):
            await db.update_verify_status(user_id, is_verified=False)
            verify_status = await db.get_verify_status(user_id)
        if not is_premium and not verify_status["is_verified"]:
            await short_url(client, message)
            return None
    return user_id


@app.on_message(filters.command(["ss", f"ss@{BOT_USERNAME}"]))
async def ss_handler(client: Client, message: Message):
    user_id = await _ss_gates(client, message)
    if not user_id:
        return
    replied = message.reply_to_message
    if not replied or not (replied.video or replied.document):
        return await message.reply_text(
            "<blockquote>Reply to a video/document with /ss to take screenshots.</blockquote>"
        )
    await message.reply_to_message.reply_text(
        "<b>Choose screenshots:</b>",
        reply_markup=_ss_keyboard(user_id, replied.id),
    )


async def handle_ss_callback(client: Client, query, user_id: int, is_admin: bool = False):
    """Screenshot button entry, called by the single shared callback
    dispatcher in call_back_button_handler.py (vss* prefix).

    NOTE: standalone bare @app.on_callback_query handlers starve on wzgram
    when several exist, so this must NOT be registered separately.
    """
    data = getattr(query, "data", "") or ""
    # ACK FIRST: user must ALWAYS see a response to the tap, even if the
    # work below fails. Also logs proof that the handler fired.
    try:
        await query.answer("📸 Taking screenshots…", show_alert=False)
    except Exception:
        pass
    try:
        LOGGER.info(f"screenshot button tapped: {data} by {getattr(query.from_user, 'id', '?')}")
    except Exception:
        pass
    try:
        parts = data.split(":")
        kind = parts[0]
        if kind == "vssp":
            _, pct, owner_id, msg_id = parts
        else:
            owner_id, msg_id = parts[1], parts[2]
            pct = None
    except (ValueError, IndexError):
        return await query.answer("❌ Invalid button.", show_alert=True)

    user_id = int(getattr(query.from_user, "id", user_id) or user_id)
    if str(user_id) != str(owner_id) and not is_admin:
        return await query.answer("⛔ Not your request!", show_alert=True)
    try:
        await query.message.delete()
    except Exception:
        pass
    try:
        reply_msg = await client.get_messages(query.message.chat.id, int(msg_id))
    except Exception:
        return await query.message.reply_text("⚠️ Original file not found.")

    if kind == "vssc":
        ask = await query.message.reply_text(
            "⏱ Send timestamps (comma separated).\n"
            "Formats: <code>12</code> sec, <code>1:23</code>, <code>01:02:03</code>, <code>50%</code>\n"
            "Example: <code>5, 1:30, 75%</code> (max 10)",
            reply_to_message_id=reply_msg.id,
        )
        try:
            incoming = await client.listen(
                chat_id=query.message.chat.id, user_id=int(owner_id), timeout=60
            )
            custom_text = incoming.text or ""
            try:
                await incoming.delete()
            except Exception:
                pass
        except Exception:
            return await ask.edit_text("⌛ Timed out. Send /ss again.")
        await _run_shots(client, query.message, reply_msg, int(owner_id), "custom", custom_text)
        try:
            await ask.delete()
        except Exception:
            pass
    elif kind == "vssp":
        await _run_shots(client, query.message, reply_msg, int(owner_id), "percent", pct)
    else:
        count = 10 if kind == "vss10" else 5
        await _run_shots(client, query.message, reply_msg, int(owner_id), "equal", count)


async def _run_shots(client, status_chat_msg, reply_msg, user_id: int, mode: str, arg) -> None:
    file_obj = reply_msg.video or reply_msg.document
    if not file_obj:
        return await status_chat_msg.reply_text("⚠️ Reply to a valid video/document.")
    file_uid = getattr(file_obj, "file_unique_id", "") or str(reply_msg.id)
    task_id, err = await task_manager.register(
        user_id, status_chat_msg.chat.id, "screenshot",
        getattr(file_obj, "file_name", None) or "video",
        f"{user_id}:{file_uid}:ss:{mode}:{arg}",
        link=getattr(reply_msg, "link", "") or "",
    )
    if not task_id:
        return await status_chat_msg.reply_text(err)

    # Bind the shared status (reply_msg is alive; the buttons message isn't).
    try:
        from bot.group_status import announce_task, make_manager_progress
        await announce_task(reply_msg)
    except Exception as e:
        LOGGER.warning(f"status attach failed: {e}")

    work_dir = os.path.join(DOWNLOAD_LOCATION, f"ss_{user_id}_{task_id}")
    os.makedirs(work_dir, exist_ok=True)
    sent = None
    try:
        # No slot: screenshots are LIGHT (single-frame grabs, -threads 1).
        # Plan FIRST from Telegram metadata (duration is instant) so we only
        # fetch the bytes the shots actually need (fast path for early shots).
        meta_duration = getattr(file_obj, "duration", 0) or 0
        file_size = getattr(file_obj, "file_size", 0) or 0
        planned, label = ([], "")
        if meta_duration > 0:
            planned, label = plan_timestamps(mode, arg, meta_duration)
            if not planned:
                return await safe_telegram_call(status_chat_msg.reply, "❌ No valid timestamps.")
        budget = partial_budget(max(planned), meta_duration, file_size) if planned else 0

        await task_manager.set_phase(task_id, PHASE_DOWNLOADING)
        d_start = time.time()
        input_path = os.path.join(work_dir, "input.mkv")
        downloaded = None
        partial_used = False
        dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
        async with dl_ctx:
            if budget:
                downloaded = await partial_fetch(client, file_obj, input_path, budget)
                partial_used = True
            else:
                downloaded = await client.download_media(
                    file_obj, file_name=input_path,
                    progress=make_manager_progress(task_id),
                    progress_args=(client, "📥 Downloading…", None, d_start),
                )
        if task_manager.is_cancelled(task_id):
            return
        if not downloaded or not os.path.exists(downloaded):
            return await safe_telegram_call(status_chat_msg.reply, "❌ Download failed.")

        duration = get_video_duration(downloaded) or meta_duration
        if not duration or duration <= 0:
            return await safe_telegram_call(status_chat_msg.reply, "❌ Could not read video duration.")
        if planned and meta_duration > 0:
            timestamps = planned
        else:
            timestamps, label = plan_timestamps(mode, arg, duration)
        if not timestamps:
            return await safe_telegram_call(status_chat_msg.reply, "❌ No valid timestamps.")

        await task_manager.set_phase(task_id, PHASE_PROCESSING)
        shots = await grab_frames(downloaded, timestamps, work_dir, task_id)
        if not shots and partial_used:
            # Partial head missed (VBR) — ONE full retry, then whatever we get.
            try:
                os.remove(input_path)
            except Exception:
                pass
            dl_ctx = task_manager.download_slot(task_id) if task_id else nullcontext()
            async with dl_ctx:
                downloaded = await client.download_media(
                    file_obj, file_name=input_path,
                    progress=make_manager_progress(task_id),
                    progress_args=(client, "📥 Downloading…", None, d_start),
                )
            if downloaded and os.path.exists(downloaded):
                duration = get_video_duration(downloaded) or duration
                timestamps, label = plan_timestamps(mode, arg, duration)
                shots = await grab_frames(downloaded, timestamps, work_dir, task_id)

        if task_manager.is_cancelled(task_id):
            return
        if not shots:
            return await safe_telegram_call(status_chat_msg.reply, "❌ No screenshots captured.")

        caption = f"📸 {label} — {TimeFormatter(int(duration) * 1000)} video"
        spoiler = await db.get_user_spoiler(user_id)
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
            await task_manager.update_progress(task_id, 100.0, detail="Uploading photos...")
        ul_ctx = task_manager.upload_slot(task_id) if task_id else nullcontext()
        async with ul_ctx:
            if len(shots) == 1:
                await client.send_photo(
                    chat_id=status_chat_msg.chat.id, photo=shots[0],
                    caption=caption, reply_to_message_id=reply_msg.id,
                    has_spoiler=bool(spoiler),
                )
            else:
                media = [InputMediaPhoto(shots[0], caption=caption, has_spoiler=bool(spoiler))]
                media += [InputMediaPhoto(p, has_spoiler=bool(spoiler)) for p in shots[1:]]
                await client.send_media_group(
                    chat_id=status_chat_msg.chat.id, media=media,
                    reply_to_message_id=reply_msg.id,
                )
    except FloodWait as fw:
        await asyncio.sleep(getattr(fw, "value", 5) + 1)
    except Exception as e:
        LOGGER.warning(f"screenshot task failed: {e}")
        await safe_telegram_call(status_chat_msg.reply, f"❌ Error: <code>{e}</code>")
    finally:
        try:
            if sent:
                await sent.delete()
        except Exception:
            pass
        shutil.rmtree(work_dir, ignore_errors=True)
        await task_manager.complete(task_id)
