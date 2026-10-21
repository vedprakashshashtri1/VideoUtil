# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Advanced file split & upload subsystem.

Supports:
- Dynamic size limit detection (2GB standard vs 4GB verified Telegram Premium session).
- Raw binary chunking for ANY file format (.001, .002, ... rejoining recreates byte-for-byte exact file).
- Media-aware normal splitting via FFmpeg stream-copy with graceful binary fallback.
- Streamlined delivery (Video vs Document based on user preference, binary parts always as Document).
- Full integration with existing queue, progress callback, destination routing, and temporary file cleanup.
"""

import asyncio
import html
import os
import re
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

from bot import LOGGER, app
from bot.config import Config
from bot.task_manager import task_manager, PHASE_SPLITTING, PHASE_UPLOADING
from bot.helper_funcs.display_progress import (
    FINISHED_PROGRESS_STR,
    UN_FINISHED_PROGRESS_STR,
    TimeFormatter,
    humanbytes,
)
from bot.helper_funcs.media_caption import enhance_media_caption
from bot.helper_funcs.flags import (
    flags_from_message,
    parse_split_size,
    sanitize_name,
    UTIL_FLAG_KINDS,
)
from bot.helper_funcs.thumb_resolver import resolve_thumb_flag
from bot.helper_funcs.dump import dump_copy
from bot.localisation import Localisation
from database import db
from pyrogram import StopTransmission
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from urllib.parse import quote

# Default split thresholds — Telegram's REAL upload limits.
# Free accounts: exactly 2000 MiB; Premium: 4000 MiB. Binary 2 GiB/4 GiB
# values are rejected by Telegram (see telegramdesktop/tdesktop#26688),
# so files are only split once they cross these byte counts.
MAX_TG_SPLIT_SIZE_NORMAL = 2000 * 1024 * 1024   # 2,097,152,000 bytes (2000 MiB)
MAX_TG_SPLIT_SIZE_PREMIUM = 4000 * 1024 * 1024  # 4,194,304,000 bytes (4000 MiB)

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".mov", ".avi", ".flv", ".webm",
    ".m4v", ".ts", ".m2ts", ".mts", ".wmv", ".3gp", ".3g2",
    ".asf", ".vob", ".mpg", ".mpeg", ".ogv", ".divx", ".rmvb",
    ".rm", ".f4v", ".f4p", ".mpe", ".mpv", ".m2v"
}

# ffprobe reports codec_type=video for still images - never treat them as video
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff",
    ".heic", ".avif", ".jfif",
}

# Probed against the live API (2026): Telegram stores a filename VERBATIM
# only while the FULL name is <= 64 characters. Longer names get every run
# of non-alphanumerics collapsed to a single "_" and the part before the
# last dot capped at 64, which eats the dots in "X.10bit.mkv.001" /
# "X.10.part001.mkv" -> "X.10bit_mkv.001" / "X.10_part001.mkv". Shaping the
# send-time attribute to <= 64 keeps the stored name deterministic while
# on-disk names and captions keep the full real name.
TG_SAFE_NAME = 64


def tg_safe_upload_name(name: str) -> str:
    """Shape an upload filename to <= 64 chars so Telegram keeps it verbatim
    instead of collapsing punctuation runs (".mkv" -> "_mkv")."""
    if len(name) <= TG_SAFE_NAME:
        return name
    stem, ext = os.path.splitext(name)
    title, tail = os.path.splitext(stem)
    budget = TG_SAFE_NAME - len(tail) - len(ext)
    if budget < 1:
        return ext[:TG_SAFE_NAME]
    title = re.sub(r"[^A-Za-z0-9._]+", "_", title)[:budget].rstrip("._-") or "file"
    return title[:budget] + tail + ext


class TaskCancelled(StopTransmission):
    """Raised on /cancel to abort an in-flight upload or split.

    Subclasses StopTransmission because Pyrogram's save_file re-raises only
    that one from the progress reporter (plain exceptions are swallowed) and
    send_* turns it into a None return instead of a traceback.
    """


_SEX_CLIENT = None
_PREMIUM_VERIFIED = None


def get_sex_client():
    """Lazily initialize the user session client if configured."""
    global _SEX_CLIENT
    if _SEX_CLIENT is not None:
        return _SEX_CLIENT

    if Config.USER_SESSION_STRING:
        try:
            from pyrogram import Client
            _SEX_CLIENT = Client(
                "Renamer_Premium",
                api_id=Config.STRING_API_ID,
                api_hash=Config.STRING_API_HASH,
                session_string=Config.USER_SESSION_STRING
            )
            LOGGER.info("Advanced Split: User session client initialized.")
        except Exception as e:
            LOGGER.error(f"Advanced Split: Failed to initialize USER_SESSION_STRING client: {e}")
            _SEX_CLIENT = None

    return _SEX_CLIENT


async def verify_premium_client() -> Tuple[bool, Optional[object]]:
    """
    Verify whether the user session client is present and has active Telegram Premium.
    Never assumes a session has 4GB without verifying is_premium.
    """
    global _PREMIUM_VERIFIED
    client = get_sex_client()
    if not client:
        return False, None

    if _PREMIUM_VERIFIED is not None:
        return _PREMIUM_VERIFIED, client

    try:
        if not getattr(client, "is_connected", False):
            await client.start()
            started_here = True
        else:
            started_here = False

        me = await client.get_me()
        is_prem = bool(getattr(me, "is_premium", False))
        _PREMIUM_VERIFIED = is_prem
        LOGGER.info(f"Advanced Split: User session verified. is_premium={is_prem}")

        if started_here:
            await client.stop()

        return is_prem, client
    except Exception as e:
        LOGGER.warning(f"Advanced Split: Failed to verify user session is_premium: {e}")
        _PREMIUM_VERIFIED = False
        return False, client


async def get_effective_uploader_and_limit(
    mode: Optional[str] = None, file_size: int = 0
) -> Tuple[object, int, bool]:
    """
    Determine the appropriate uploader client, max byte limit, and premium status.
    - If user session client is available and verified is_premium: 4GB limit.
    - Otherwise: standard bot client and 2GB limit.
    mode: NexonBots transmission flag - "bot" | "user" | "both" (None = default).
    """
    is_prem, sex_client = await verify_premium_client()
    if mode == "user":
        if not sex_client:
            raise RuntimeError("-ut needs USER_SESSION_STRING to be set")
        return sex_client, (MAX_TG_SPLIT_SIZE_PREMIUM if is_prem else MAX_TG_SPLIT_SIZE_NORMAL), is_prem
    if mode == "bot":
        return app, MAX_TG_SPLIT_SIZE_NORMAL, False
    if mode == "both":
        # NexonBots hybrid: <=2GB by bot, >2GB by the (premium) user session
        if file_size > MAX_TG_SPLIT_SIZE_NORMAL and is_prem and sex_client:
            return sex_client, MAX_TG_SPLIT_SIZE_PREMIUM, True
        return app, MAX_TG_SPLIT_SIZE_NORMAL, False
    if is_prem and sex_client:
        return sex_client, MAX_TG_SPLIT_SIZE_PREMIUM, True
    return app, MAX_TG_SPLIT_SIZE_NORMAL, False


async def safe_flood_call(func, *args, **kwargs):
    """Execute a coroutine function with automatic FloodWait retry."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = int(e.value or 1)
            LOGGER.warning(f"Advanced Split: FloodWait encountered. Sleeping {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception:
            raise


def is_video_file(file_path: str) -> bool:
    """Check if the given file has a video extension or contains valid video stream."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return False
    if ext in VIDEO_EXTENSIONS:
        return True
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0", str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "video" in res.stdout.lower():
            return True
    except Exception:
        pass
    return False


def get_video_duration(file_path: str) -> Optional[float]:
    """Extract media duration in seconds via ffprobe, ffmpeg or hachoir with multi-tier fallbacks."""
    # 1. ffprobe format duration
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        val = result.stdout.strip()
        if val and val != "N/A":
            dur = float(val)
            if dur > 0:
                return dur
    except Exception:
        pass

    # 2. ffprobe video stream duration
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        val = result.stdout.strip()
        if val and val != "N/A":
            dur = float(val)
            if dur > 0:
                return dur
    except Exception:
        pass

    # 3. ffmpeg -i parsing Duration from stderr
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(file_path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = result.stderr or result.stdout or ""
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
        if m:
            hours, mins, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
            dur = (hours * 3600) + (mins * 60) + secs
            if dur > 0:
                return dur
    except Exception:
        pass

    # 4. hachoir metadata fallback
    try:
        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser
        parser = createParser(str(file_path))
        if parser:
            with parser:
                meta = extractMetadata(parser)
                if meta and meta.has("duration"):
                    dur = meta.get("duration").total_seconds()
                    if dur > 0:
                        return float(dur)
    except Exception:
        pass

    return None


def binary_split_file(
    file_path: str,
    chunk_size: int,
    output_dir: Optional[str] = None,
    buffer_size: int = 4 * 1024 * 1024,
    task_id: Optional[str] = None,
) -> List[str]:
    """
    Raw byte chunking for ANY file format (.001, .002, ...).
    Rejoining them in numerical order recreates byte-for-byte exact original file.
    Uses buffered stream I/O (default 4MB buffer) to handle 50GB-100GB+ files with minimal RAM.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found for binary split: {file_path}")

    base_name = os.path.basename(file_path)
    out_dir = output_dir or os.path.dirname(file_path)
    os.makedirs(out_dir, exist_ok=True)

    parts: List[str] = []
    part_num = 1
    current_part_path = os.path.join(out_dir, f"{base_name}.{part_num:03d}")
    current_out = open(current_part_path, "wb")
    parts.append(current_part_path)
    written_in_part = 0

    try:
        with open(file_path, "rb") as src:
            while True:
                if task_id and task_manager.is_cancelled(task_id):
                    raise TaskCancelled(task_id)
                remaining_in_chunk = chunk_size - written_in_part
                read_amount = min(buffer_size, remaining_in_chunk)
                buf = src.read(read_amount)
                if not buf:
                    break

                current_out.write(buf)
                written_in_part += len(buf)

                if written_in_part >= chunk_size:
                    current_out.close()
                    part_num += 1
                    current_part_path = os.path.join(out_dir, f"{base_name}.{part_num:03d}")
                    current_out = open(current_part_path, "wb")
                    parts.append(current_part_path)
                    written_in_part = 0
    finally:
        if not current_out.closed:
            current_out.close()

    # Clean up empty trailing part if file size was an exact multiple
    if parts and os.path.getsize(parts[-1]) == 0:
        empty_part = parts.pop()
        try:
            os.remove(empty_part)
        except OSError:
            pass

    return parts


async def normal_split_video(
    file_path: str,
    chunk_size: int,
    output_dir: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Tuple[List[str], str]:
    """
    Splits video files using FFmpeg stream copy (-c copy) into independently playable parts.
    Splits sequentially so that each part stays just below the upload limit
    (2000 MiB standard / 4000 MiB premium) and the final part contains the remainder.
    Automatically falls back to binary_split_file only if not a video or if FFmpeg fails completely.
    """
    if not is_video_file(file_path):
        LOGGER.warning(f"Advanced Split: {file_path} is not a video file. Falling back to Binary Split.")
        return binary_split_file(file_path, chunk_size, output_dir=output_dir, task_id=task_id), "binary"

    total_bytes = os.path.getsize(file_path)
    if total_bytes <= chunk_size:
        return [file_path], "normal"

    duration = get_video_duration(file_path)
    if not duration or duration <= 0:
        LOGGER.warning(f"Advanced Split: Could not probe video duration for {file_path}. Falling back to Binary Split.")
        return binary_split_file(file_path, chunk_size, output_dir=output_dir, task_id=task_id), "binary"

    out_dir = output_dir or os.path.dirname(file_path)
    os.makedirs(out_dir, exist_ok=True)

    base, ext = os.path.splitext(os.path.basename(file_path))
    if not ext or ext.lower() not in VIDEO_EXTENSIONS:
        ext = ".mkv"
    parts: List[str] = []

    current_start = 0.0
    part_num = 1
    async def _run_ffmpeg_cut(ss_val: float, dur_val: Optional[float], target_file: str, fs_bytes: Optional[int] = None) -> Optional[str]:
        """Tries stream copy across 4 strategies so it never fails."""
        async def _try_cmd(cmd_args: list, out_f: str) -> bool:
            try:
                p = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await p.communicate()
                return p.returncode == 0 and os.path.exists(out_f) and os.path.getsize(out_f) > 0
            except Exception:
                return False

        def _finish(cmd: list, out_f: str) -> list:
            if fs_bytes:
                cmd += ["-fs", str(int(fs_bytes))]
            cmd.append(out_f)
            return cmd

        # 1. Full stream copy (v, a, s) with chapters stripped
        cmd1 = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{ss_val:.3f}",
            "-i", file_path,
        ]
        if dur_val is not None:
            cmd1 += ["-t", f"{dur_val:.3f}"]
        cmd1 += [
            "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
            "-map_chapters", "-1",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
        ]
        if target_file.lower().endswith(".mp4"):
            cmd1 += ["-movflags", "+faststart"]
        cmd1 = _finish(cmd1, target_file)

        if await _try_cmd(cmd1, target_file):
            return target_file

        # 2. Fallback: Video + Audio only (incompatible subtitles dropped)
        cmd2 = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{ss_val:.3f}",
            "-i", file_path,
        ]
        if dur_val is not None:
            cmd2 += ["-t", f"{dur_val:.3f}"]
        cmd2 += [
            "-map", "0:v?", "-map", "0:a?",
            "-map_chapters", "-1",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
        ]
        if target_file.lower().endswith(".mp4"):
            cmd2 += ["-movflags", "+faststart"]
        cmd2 = _finish(cmd2, target_file)

        if await _try_cmd(cmd2, target_file):
            return target_file

        # 3. Fallback: bare -c copy
        cmd3 = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{ss_val:.3f}",
            "-i", file_path,
        ]
        if dur_val is not None:
            cmd3 += ["-t", f"{dur_val:.3f}"]
        cmd3 += [
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
        ]
        cmd3 = _finish(cmd3, target_file)

        if await _try_cmd(cmd3, target_file):
            return target_file

        # 4. Fallback: if container was .mp4 and failed, switch to .mkv (MKV accepts all codecs)
        if not target_file.lower().endswith(".mkv"):
            mkv_file = os.path.splitext(target_file)[0] + ".mkv"
            cmd4 = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{ss_val:.3f}",
                "-i", file_path,
            ]
            if dur_val is not None:
                cmd4 += ["-t", f"{dur_val:.3f}"]
            cmd4 += [
                "-map", "0:v?", "-map", "0:a?",
                "-map_chapters", "-1",
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
            ]
            cmd4 = _finish(cmd4, mkv_file)
            if await _try_cmd(cmd4, mkv_file):
                return mkv_file

        return None

    try:
        # Byte-limited cut (same engine as NexonBots): ffmpeg stops writing at
        # ~chunk_size actual bytes instead of estimating duration from bitrate.
        fs_limit = max(1_000_000, chunk_size - 3_000_000)
        while current_start < duration - 1.0:
            if task_id and task_manager.is_cancelled(task_id):
                raise TaskCancelled(task_id)
            part_path = os.path.join(out_dir, f"{base}.part{part_num:03d}{ext}")

            cut_res = None
            for _attempt in range(6):
                cut_res = await _run_ffmpeg_cut(current_start, None, part_path, fs_limit)
                if not cut_res or not os.path.exists(cut_res) or os.path.getsize(cut_res) == 0:
                    raise RuntimeError(f"FFmpeg split failed for part {part_num}")

                actual_size = os.path.getsize(cut_res)
                if actual_size <= chunk_size:
                    break

                # Overshot the limit: shrink -fs and redo this part
                try:
                    os.remove(cut_res)
                except OSError:
                    pass
                fs_limit -= (actual_size - chunk_size) + 5_000_000
                if fs_limit < 1_000_000:
                    raise RuntimeError(f"Could not split part {part_num} within limit {chunk_size} bytes.")
                cut_res = None
            else:
                raise RuntimeError(f"Could not split part {part_num} within limit {chunk_size} bytes.")

            parts.append(cut_res)

            part_duration = get_video_duration(cut_res)
            if not part_duration or part_duration <= 1.0:
                raise RuntimeError(f"Split stalled: invalid duration for part {part_num}")

            current_start += part_duration
            part_num += 1

        if not parts:
            raise RuntimeError("Zero parts created by normal split.")

        return parts, "normal"
    except TaskCancelled:
        raise
    except Exception as e:
        LOGGER.warning(f"Advanced Split: Normal split failed ({e}). Falling back to Binary Split.")
        for p in parts:
            try:
                if os.path.exists(p) and p != file_path:
                    os.remove(p)
            except OSError:
                pass
        return binary_split_file(file_path, chunk_size, output_dir=output_dir, task_id=task_id), "binary"


def make_split_progress_callback(
    bot_client,
    status_msg,
    mode_name: str,
    orig_size: int,
    split_size: int,
    part_idx: int,
    total_parts: int,
    start_time: float,
    task_id=None,
):
    """
    Builds a specialized progress callback displaying Mode, Part X of Y,
    Speed, ETA, and progress bar.

    With task_id set, progress goes ONLY to the shared status (no message
    edits); otherwise the legacy per-task message is edited as before.
    """
    last_update = [0.0]

    async def callback(current, total):
        if task_id and task_manager.is_cancelled(task_id):
            raise TaskCancelled(task_id)
        now = time.time()
        diff = now - start_time
        if diff == 0:
            return
        if now - last_update[0] < 4.0 and current != total:
            return
        last_update[0] = now

        try:
            pct = (current * 100) / total if total > 0 else 0
        except ZeroDivisionError:
            pct = 0

        speed = current / diff if diff > 0 else 0
        eta = round((total - current) / speed) * 1000 if speed > 0 else 0
        total_eta_str = TimeFormatter(milliseconds=eta)

        if task_id:
            try:
                await task_manager.update_progress(
                    task_id, pct,
                    f"{humanbytes(speed)}/s", total_eta_str,
                    done_bytes=min(orig_size, (part_idx - 1) * split_size + current),
                    total_bytes=orig_size,
                )
            except Exception:
                pass
            return

        filled = int(pct // 10)
        bar = FINISHED_PROGRESS_STR * filled + UN_FINISHED_PROGRESS_STR * (10 - filled)

        text = (
            f"📤 <b>Uᴘʟᴏᴀᴅɪɴɢ...</b>\n"
            f"<blockquote><b>Mode:</b> <code>{mode_name}</code>\n"
            f"<b>Part:</b> <code>{part_idx} / {total_parts}</code>\n"
            f"<b>Part Size:</b> <code>{humanbytes(total)}</code>\n"
            f"<b>Original Size:</b> <code>{humanbytes(orig_size)}</code></blockquote>\n"
            f"<blockquote><code>[{bar}]</code>\n"
            f"<b>Progress:</b> {pct:.2f}%\n"
            f"{humanbytes(current)} of {humanbytes(total)}\n"
            f"Speed: {humanbytes(speed)}/s | ETA: {total_eta_str}</blockquote>"
        )
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    return callback


def _rename_output(file_path: str, new_name: str) -> str:
    """Apply the -n flag to the file about to be uploaded."""
    try:
        target = sanitize_name(new_name)
        directory = os.path.dirname(file_path) or "."
        if os.path.isfile(file_path) and not os.path.splitext(target)[1]:
            src_ext = os.path.splitext(file_path)[1]
            if src_ext:
                target += src_ext
        dest = os.path.join(directory, target)
        if os.path.abspath(dest) == os.path.abspath(file_path):
            return file_path
        if os.path.exists(dest):
            base, ext = os.path.splitext(target)
            dest = os.path.join(directory, f"{base}_{int(time.time())}{ext}")
        os.rename(file_path, dest)
        LOGGER.info(f"Advanced Split: -n renamed -> {dest}")
        return dest
    except Exception as e:
        LOGGER.warning(f"Advanced Split: -n rename failed: {e}")
        return file_path


def choose_split_mode(file_path: str, pref_split: Optional[str]) -> str:
    """Non-video files (archives, any extension) always use Binary Split;
    videos follow the user's Normal/Binary preference."""
    if pref_split == "binary" or not is_video_file(file_path):
        return "Binary Split"
    return "Normal Split"


async def smart_split_and_upload(
    client,
    message,
    file_path: str,
    status_msg,
    caption: str = "",
    thumb_path: Optional[str] = None,
    duration: Optional[int] = None,
    user_id: Optional[int] = None,
    reply_to_id: Optional[int] = None,
    task_id: Optional[str] = None,
    split_size: Optional[int] = None,
    media_pref: Optional[str] = None,
    transmission: Optional[str] = None,
    use_msg_flags: bool = True,
) -> bool:
    """
    Unified entry point for advanced file splitting and upload.
    - Dynamically evaluates file size vs account limits.
    - Honors user preferences: Send Video As (Video vs Document) and Split Mode (Normal vs Binary).
    - If size <= limit: uploads directly.
    - If size > limit: splits according to preference and uploads sequentially.
    - Non-video files automatically use Binary Split.
    - Binary parts are ALWAYS uploaded as Telegram Documents.
    - Does NOT remove the original file until all parts have uploaded successfully.
    """
    if not os.path.exists(file_path):
        LOGGER.error(f"Advanced Split: file {file_path} does not exist.")
        return False

    uid = user_id or (message.from_user.id if message.from_user else message.chat.id)

    # NexonBots style flags on the invoking command (util commands). /leech parses
    # them itself and calls with use_msg_flags=False + explicit params.
    if use_msg_flags:
        try:
            _, uflags = flags_from_message(message)
        except Exception:
            uflags = {}
        if "-n" in uflags and isinstance(uflags["-n"], str) and uflags["-n"].strip():
            file_path = _rename_output(file_path, uflags["-n"]) or file_path
        if "-t" in uflags:
            try:
                t_path, t_skip, t_err = await resolve_thumb_flag(client, uflags["-t"])
            except Exception as e:
                t_path, t_skip, t_err = None, False, str(e)
            if t_err:
                LOGGER.warning(f"[Flags] -t ignored: {t_err}")
            if t_skip:
                thumb_path = None
            elif t_path:
                thumb_path = t_path
        if split_size is None and "-sp" in uflags:
            split_size = parse_split_size(uflags.get("-sp")) or None
        if media_pref is None:
            if uflags.get("-doc"):
                media_pref = "document"
            elif uflags.get("-med"):
                media_pref = "video"

    if not os.path.exists(file_path):
        LOGGER.error(f"Advanced Split: file missing after flag rename.")
        return False

    orig_size = os.path.getsize(file_path)

    # Fetch user preferences
    pref_media, pref_split, pref_dest, pref_spoiler, channel_id, upload_location = await asyncio.gather(
        db.get_media_preference(uid),
        db.get_split_mode(uid),
        db.get_upload_preference(uid),
        db.get_user_spoiler(uid),
        db.get_user_channel(uid),
        db.get_upload_location(uid),
    )
    if media_pref in ("video", "document"):
        pref_media = media_pref

    # Determine destination chat
    notify_missing_channel = False
    if pref_dest == "dm":
        dest_chat_id = uid
        reply_to = None
    elif pref_dest == "channel":
        if channel_id:
            dest_chat_id = channel_id
            reply_to = None
        else:
            dest_chat_id = message.chat.id
            reply_to = reply_to_id or message.id
            notify_missing_channel = True
    else:  # group
        dest_chat_id = message.chat.id
        reply_to = reply_to_id or message.id

    # Determine uploader client and max size limit (-hl/-bt/-ut aware)
    uploader_client, max_limit, is_prem = await get_effective_uploader_and_limit(
        transmission, orig_size
    )
    use_proxy_copy = (uploader_client != app and max_limit > MAX_TG_SPLIT_SIZE_NORMAL)

    # Custom -sp split size: cap it below the hard upload limit
    if split_size and split_size > 0:
        split_size = min(split_size, max_limit - (5 * 1024 * 1024))

    # Check if splitting is necessary (size > TG limit, or > custom -sp)
    # Google Drive destination: no Telegram size limit - never split the file
    # unless the user explicitly forced a chunk size with -sp.
    if upload_location == "gdrive":
        need_split = bool(split_size and split_size > 0 and orig_size > split_size)
        if not need_split:
            LOGGER.info("Advanced Split: gdrive destination - skipping TG size split")
    else:
        need_split = orig_size > max_limit or (
            split_size and split_size > 0 and orig_size > split_size
        )
    if not need_split:
        # Direct single file upload
        if task_id:
            await task_manager.set_phase(task_id, PHASE_UPLOADING)
        try:
            return await _upload_single_file(
                bot_client=client,
                uploader_client=uploader_client,
                use_proxy_copy=use_proxy_copy,
                dest_chat_id=dest_chat_id,
                reply_to=reply_to,
                file_path=file_path,
                status_msg=status_msg,
                caption=caption,
                thumb_path=thumb_path,
                duration=duration,
                is_video=(pref_media == "video" and is_video_file(file_path)),
                has_spoiler=bool(pref_spoiler),
                pref_dest=pref_dest,
                notify_missing_channel=notify_missing_channel,
                message=message,
                uid=uid,
                task_id=task_id
            )
        except TaskCancelled:
            LOGGER.info(f"Advanced Split: cancelled by user (task {task_id})")
            return False

    # Splitting required
    if task_id:
        await task_manager.set_phase(task_id, PHASE_SPLITTING)
    LOGGER.info(f"Advanced Split: input file: {os.path.basename(file_path)}")
    split_dir = os.path.join(os.path.dirname(file_path), f"split_{int(time.time())}")
    os.makedirs(split_dir, exist_ok=True)

    mode_name = choose_split_mode(file_path, pref_split)
    requested_mode = mode_name
    # Leave a safety margin (5MB) below max limit; -sp can lower it further
    chunk_target = max_limit - (5 * 1024 * 1024)
    if split_size and split_size > 0 and split_size < chunk_target:
        chunk_target = split_size
    await status_msg.edit_text(
        f"✂️ <b>Sᴘʟɪᴛᴛɪɴɢ ғɪʟᴇ</b> (target <code>{humanbytes(chunk_target)}</code>/part)\n"
        f"<blockquote><b>Mode:</b> <code>{mode_name}</code>\n"
        f"<b>Original Size:</b> <code>{humanbytes(orig_size)}</code>\n"
        f"Pʀᴇᴘᴀʀɪɴɢ sᴘʟɪᴛ ᴘᴀʀᴛs...</blockquote>"
    )

    parts: List[str] = []
    try:
        if mode_name == "Binary Split":
            parts = binary_split_file(file_path, chunk_target, output_dir=split_dir, task_id=task_id)
            mode_name = "Binary Split"
        else:
            parts, used = await normal_split_video(file_path, chunk_target, output_dir=split_dir, task_id=task_id)
            mode_name = "Binary Split" if used == "binary" else "Normal Split"

        if not parts:
            raise RuntimeError("Splitting produced zero output files.")

        total_parts = len(parts)
        LOGGER.info(f"Advanced Split: Created {total_parts} parts using {mode_name}")
        if mode_name != requested_mode:
            LOGGER.warning(
                f"Advanced Split: requested {requested_mode} but {mode_name} was used "
                f"for {file_path} (silent fallback inside normal_split_video)."
            )

        # Upload parts sequentially
        drive_uploaded = False
        for idx, part in enumerate(parts, 1):
            if task_id and task_manager.is_cancelled(task_id):
                raise TaskCancelled(task_id)
            part_size = os.path.getsize(part)
            part_name = os.path.basename(part)
            is_binary_part = (mode_name == "Binary Split") or not is_video_file(part)

            # Caption for this part - title = the part's REAL on-disk name
            part_caption = enhance_media_caption(
                part,
                legacy_caption=caption,
                delivery="document" if is_binary_part or pref_media == "document" else "video",
                file_name=part_name,
            )
            part_caption += f"\n\n🧩 <b>Part {idx} of {total_parts}</b>"
            if idx == 1 and mode_name != requested_mode:
                part_caption += (
                    f"\n⚠️ <b>{requested_mode}</b> unavailable — "
                    f"<b>{mode_name}</b> used instead (check bot logs)"
                )

            # Duration for video parts
            part_duration = get_video_duration(part) if not is_binary_part else None
            p_dur = int(part_duration) if part_duration else None

            progress_cb = make_split_progress_callback(
                bot_client=client,
                status_msg=status_msg,
                mode_name=mode_name,
                orig_size=orig_size,
                split_size=part_size,
                part_idx=idx,
                total_parts=total_parts,
                start_time=time.time(),
                task_id=task_id
            )

            if task_id:
                await task_manager.set_phase(task_id, PHASE_UPLOADING)
            success = await _upload_file_dispatch(
                bot_client=client,
                uploader_client=uploader_client,
                use_proxy_copy=use_proxy_copy,
                dest_chat_id=dest_chat_id,
                reply_to=reply_to,
                file_path=part,
                caption=part_caption,
                thumb_path=thumb_path,
                duration=p_dur,
                is_video=(not is_binary_part and pref_media == "video"),
                has_spoiler=bool(pref_spoiler),
                progress_cb=progress_cb,
                task_id=task_id,
                uid=uid,
                user_name=(message.from_user.first_name if message.from_user else "User")
            )

            if not success:
                raise RuntimeError(f"Failed to upload part {idx}/{total_parts}")

            if isinstance(success, DriveUploadResult):
                drive_uploaded = True
                continue

            # Mirror each finished part into the optional dump channel.
            try:
                await dump_copy(client, success)
            except Exception:
                pass

        # Notify upload location if not group
        if not drive_uploaded and pref_dest != "group":
            dest_name = "DM" if pref_dest == "dm" else "Channel"
            first_name = message.from_user.first_name if message.from_user else "User"
            mention = f"<a href='tg://user?id={uid}'>{first_name}</a>"
            text = Localisation.UPLOAD_SENT_TEXT.format(mention=mention, dest=dest_name)
            try:
                await safe_flood_call(client.send_message, chat_id=message.chat.id, text=text, parse_mode=ParseMode.HTML)
            except Exception as e:
                LOGGER.warning(f"Failed to send destination notification: {e}")

        if not drive_uploaded and pref_dest == "channel" and notify_missing_channel:
            try:
                await safe_flood_call(
                    message.reply,
                    "⚠️ You selected Channel as upload destination but haven't set one — files sent here instead."
                )
            except Exception:
                pass

        await safe_flood_call(status_msg.delete)
        return True

    except TaskCancelled:
        LOGGER.info(f"Advanced Split: cancelled by user (task {task_id})")
        return False
    except Exception as e:
        LOGGER.error(f"Advanced Split: Processing failed: {e}")
        await safe_flood_call(
            status_msg.edit_text,
            f"❌ <b>Sᴘʟɪᴛ & Uᴘʟᴏᴀᴅ Fᴀɪʟᴇᴅ:</b>\n<code>{e}</code>"
        )
        return False
    finally:
        # Clean up split directory and its parts
        try:
            if os.path.exists(split_dir):
                shutil.rmtree(split_dir, ignore_errors=True)
        except Exception:
            pass


class DriveUploadResult:
    """Truthy marker: the file went to Google Drive instead of Telegram."""
    __slots__ = ("file_id", "name", "size")

    def __init__(self, file_id, name, size):
        self.file_id = file_id
        self.name = name
        self.size = size


async def _drive_upload_dispatch(bot_client, dest_chat_id, reply_to, file_path, progress_cb, task_id, uid, user_name=None):
    from bot.helper_funcs import gdrive as gdrive_mod

    drive_uid = await gdrive_mod.upload_drive_uid(uid)
    if not drive_uid:
        try:
            await safe_flood_call(
                bot_client.send_message,
                dest_chat_id,
                "❌ <b>Google Drive is not connected.</b>\n"
                "Open Settings → ☁️ Google Drive and connect, or switch Location back to Telegram.",
                reply_to_message_id=reply_to,
            )
        except Exception:
            pass
        return False
    folder_id = await gdrive_mod.resolve_upload_folder(uid, drive_uid)
    try:
        result = await gdrive_mod.drive_upload_file(
            drive_uid,
            file_path,
            progress_cb=progress_cb,
            folder_id=folder_id,
            cancel_check=(lambda: task_manager.is_cancelled(task_id)) if task_id else None,
        )
    except gdrive_mod.UploadCancelled:
        if task_id:
            raise TaskCancelled(task_id)
        return False
    except gdrive_mod.GDriveError as e:
        LOGGER.error(f"Drive upload failed for {os.path.basename(file_path)}: {e}")
        try:
            await safe_flood_call(
                bot_client.send_message,
                dest_chat_id,
                f"❌ <b>Google Drive upload failed:</b>\n<code>{e}</code>",
                reply_to_message_id=reply_to,
            )
        except Exception:
            pass
        return False

    size = os.path.getsize(file_path)
    buttons = [
        [
            InlineKeyboardButton(
                "☁️ Link",
                url=(
                    "https://drive.google.com/uc"
                    f"?export=download&id={result['id']}"
                ),
            )
        ]
    ]
    index_base = (getattr(Config, "INDEX_URL", "") or "").rstrip("/")
    # Index/View only make sense when the file landed on the owner's indexed
    # drive - a user's own-drive upload is invisible to the owner's index.
    indexed = drive_uid == int(getattr(Config, "OWNER_ID", 0) or 0)
    if index_base and indexed:
        prefix = (getattr(Config, "GDRIVE_INDEX_PREFIX", "") or "").strip("/")
        rel = f"{prefix}/{result['name']}" if prefix else result["name"]
        index_url = f"{index_base}/0:/{quote(rel, safe='/:')}"
        buttons[0].append(InlineKeyboardButton("🔗 Index", url=index_url))
        buttons.append([InlineKeyboardButton("▶ View", url=f"{index_url}?a=view")])
    mime = result.get("mime") or "application/octet-stream"
    owner = html.escape(str(user_name or "User"))
    text = (
        "✅ <b>Upload Complete!</b>\n"
        f"├ 📂 Name: <b><code>{html.escape(result['name'])}</code></b>\n"
        f"├ 💿 Size: <b>{humanbytes(size).replace(' ', '')}</b>\n"
        f"├ 📦 Type: <b>{html.escape(mime)}</b>\n"
        f"└ 👤 User: <b><a href=\"tg://user?id={uid}\">{owner}</a></b>"
    )
    try:
        await safe_flood_call(
            bot_client.send_message,
            dest_chat_id,
            text,
            reply_to_message_id=reply_to,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
        )
    except Exception as e:
        LOGGER.warning(f"Drive completion message failed: {e}")
    return DriveUploadResult(result["id"], result["name"], size)


async def _upload_file_dispatch(
    bot_client,
    uploader_client,
    use_proxy_copy: bool,
    dest_chat_id,
    reply_to,
    file_path: str,
    caption: str,
    thumb_path: Optional[str],
    duration: Optional[int],
    is_video: bool,
    has_spoiler: bool,
    progress_cb,
    task_id: Optional[str] = None,
    uid: Optional[int] = None,
    user_name: Optional[str] = None
):
    """Send via the bot client or a premium proxy copy.

    Returns the final delivered Message (destination chat) or False.
    """
    if uid:
        try:
            if await db.get_upload_location(uid) == "gdrive":
                return await _drive_upload_dispatch(
                    bot_client, dest_chat_id, reply_to, file_path, progress_cb, task_id, uid, user_name
                )
        except Exception as e:
            LOGGER.error(f"Upload location check failed (using Telegram): {e}")
    # Telegram-side filename limit: pre-shape only the uploaded name; the
    # caption and the on-disk file keep the full real name.
    upload_name = tg_safe_upload_name(os.path.basename(file_path))
    try:
        if use_proxy_copy:
            # Need to start user session client
            if not getattr(uploader_client, "is_connected", False):
                await uploader_client.start()
                started = True
            else:
                started = False

            try:
                if is_video:
                    sent = await safe_flood_call(
                        uploader_client.send_video,
                        Config.LOG_CHANNEL,
                        video=file_path,
                        file_name=upload_name,
                        caption=caption,
                        thumb=thumb_path,
                        duration=duration,
                        has_spoiler=has_spoiler,
                        progress=progress_cb
                    )
                else:
                    sent = await safe_flood_call(
                        uploader_client.send_document,
                        Config.LOG_CHANNEL,
                        document=file_path,
                        file_name=upload_name,
                        caption=caption,
                        thumb=thumb_path,
                        progress=progress_cb
                    )

                # A /cancel aborts the upload inside Pyrogram (StopTransmission)
                # which the send wrapper turns into a None return.
                if not sent and task_id and task_manager.is_cancelled(task_id):
                    raise TaskCancelled(task_id)

                # Copy message from log channel to destination
                max_copy_attempts = 5
                copied = None
                for attempt in range(max_copy_attempts):
                    try:
                        await asyncio.sleep(2 * attempt)
                        copied = await safe_flood_call(
                            bot_client.copy_message,
                            chat_id=dest_chat_id,
                            from_chat_id=sent.chat.id,
                            message_id=sent.id,
                            reply_to_message_id=reply_to
                        )
                        if copied:
                            break
                    except Exception as err:
                        LOGGER.warning(f"Copy attempt {attempt+1}/{max_copy_attempts} failed: {err}")

                # Only remove the staging copy in the log channel once the
                # destination delivery actually succeeded - the uploaded copy
                # must survive failed copy attempts so nothing is lost.
                if copied:
                    try:
                        await bot_client.delete_messages(sent.chat.id, sent.id)
                    except Exception:
                        pass

                return copied if copied else False
            finally:
                if started:
                    await uploader_client.stop()
        else:
            # Direct send via bot client
            if is_video:
                sent = await safe_flood_call(
                    bot_client.send_video,
                    dest_chat_id,
                    video=file_path,
                    file_name=upload_name,
                    caption=caption,
                    thumb=thumb_path,
                    duration=duration,
                    has_spoiler=has_spoiler,
                    reply_to_message_id=reply_to,
                    progress=progress_cb
                )
            else:
                sent = await safe_flood_call(
                    bot_client.send_document,
                    dest_chat_id,
                    document=file_path,
                    file_name=upload_name,
                    caption=caption,
                    thumb=thumb_path,
                    reply_to_message_id=reply_to,
                    progress=progress_cb
                )
            if not sent and task_id and task_manager.is_cancelled(task_id):
                raise TaskCancelled(task_id)
            return sent if sent else False

    except TaskCancelled:
        raise
    except Exception as e:
        LOGGER.error(f"Advanced Split: _upload_file_dispatch failed: {e}")
        return False


async def _upload_single_file(
    bot_client,
    uploader_client,
    use_proxy_copy: bool,
    dest_chat_id,
    reply_to,
    file_path: str,
    status_msg,
    caption: str,
    thumb_path: Optional[str],
    duration: Optional[int],
    is_video: bool,
    has_spoiler: bool,
    pref_dest: str,
    notify_missing_channel: bool,
    message,
    uid: int,
    task_id: Optional[str] = None
) -> bool:
    """Helper to upload an unsplit file within Telegram limits."""
    from bot.helper_funcs.display_progress import progress_for_pyrogram

    delivery_mode = "video" if is_video else "document"
    final_caption = enhance_media_caption(file_path, legacy_caption=caption, delivery=delivery_mode)

    upload_start = time.time()

    async def p_cb(current, total):
        if task_id and task_manager.is_cancelled(task_id):
            raise TaskCancelled(task_id)
        if task_id:
            # Shared status only (no per-task message edits).
            try:
                pct = (current * 100) / total if total > 0 else 0
                diff = max(time.time() - upload_start, 0.001)
                speed = current / diff
                eta_ms = round((total - current) / speed) * 1000 if speed > 0 else 0
                await task_manager.update_progress(
                    task_id, pct,
                    f"{humanbytes(speed)}/s", TimeFormatter(milliseconds=eta_ms),
                    done_bytes=current, total_bytes=total,
                )
            except Exception:
                pass
            return
        await progress_for_pyrogram(
            current, total, bot_client, "📤 Uᴘʟᴏᴀᴅɪɴɢ...", status_msg, upload_start
        )

    success = await _upload_file_dispatch(
        bot_client=bot_client,
        uploader_client=uploader_client,
        use_proxy_copy=use_proxy_copy,
        dest_chat_id=dest_chat_id,
        reply_to=reply_to,
        file_path=file_path,
        caption=final_caption,
        thumb_path=thumb_path,
        duration=duration,
        is_video=is_video,
        has_spoiler=has_spoiler,
        progress_cb=p_cb,
        task_id=task_id,
        uid=uid,
        user_name=(message.from_user.first_name if message.from_user else "User")
    )

    if not success:
        await safe_flood_call(status_msg.edit_text, "❌ Upload failed. Please try again.")
        return False

    # Mirror the finished upload into the optional dump channel.
    try:
        await dump_copy(bot_client, success)
    except Exception:
        pass

    if not isinstance(success, DriveUploadResult) and pref_dest == "channel" and notify_missing_channel:
        try:
            await safe_flood_call(
                message.reply,
                "⚠️ You selected Channel as upload destination but haven't set one — files sent here instead."
            )
        except Exception:
            pass

    if not isinstance(success, DriveUploadResult) and pref_dest != "group":
        dest_name = "DM" if pref_dest == "dm" else "Channel"
        first_name = message.from_user.first_name if message.from_user else "User"
        mention = f"<a href='tg://user?id={uid}'>{first_name}</a>"
        text = Localisation.UPLOAD_SENT_TEXT.format(mention=mention, dest=dest_name)
        try:
            await safe_flood_call(bot_client.send_message, chat_id=message.chat.id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            LOGGER.warning(f"Failed to send destination notification: {e}")

    await safe_flood_call(status_msg.delete)
    return True
