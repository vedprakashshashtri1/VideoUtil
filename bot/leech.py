# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, LEECH_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.helper_funcs.leech_helper import *
from bot.response import *
from bot.split_videos import *
from bot.helper_funcs.display_progress import *
from bot.helper_funcs.split_uploader import smart_split_and_upload, is_video_file
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
from pyrogram.errors import FloodWait, RPCError, MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from bot.helper_funcs.media_caption import build_media_caption
import asyncio
import os, shutil
import time
import subprocess
from bot.localisation import Localisation
from asyncio.exceptions import TimeoutError
from bot.premium import *
import aiohttp, aiofiles, zipfile, re, time
from aiofiles.os import mkdir
from contextlib import nullcontext
from bot.task_manager import (
    task_manager,
    build_dedupe_key,
    PHASE_DOWNLOADING,
    PHASE_UPLOADING,
)
from bot.group_status import announce_task, UploadSink
from bot.config import Config
from bot.helper_funcs.flags import (
    parse_leech_flags,
    blocked_flags,
    flags_fingerprint,
    parse_split_size,
    leech_flag_help_messages,
    sanitize_name,
)
from bot.helper_funcs.leech_post import run_leech_pipeline, gather_files
from bot.helper_funcs.thumb_resolver import resolve_thumb_flag, build_tile_thumb
from bot.helper_funcs.gdrive import (
    GDriveError, drive_download, drive_list_folder, leech_drive_uid, parse_drive_url,
)

async def safe_send(func, *args, retries=5, backoff=2, **kwargs):

    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = min(e.value, 60)
            LOGGER.warning(f"FloodWait: sleeping for {wait_time}s...")
            await asyncio.sleep(wait_time)
        except (RPCError, FloodWait, MessageNotModified) as e:
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


# ==================== LEECH COMMAND ====================
LEECH_USAGE = (
    "🎯 <b>Leech usage:</b>\n"
    "• Reply to a link or any file with <code>/leech</code> (or <code>/l</code>)\n"
    "• <code>/leech magnet:?xt=urn:btih:...</code>\n"
    "• <code>/leech https://site.com/file.zip</code> (direct HTTP link)\n"
    "• <code>/leech https://site.com/file.torrent</code>\n"
    "• <code>/leech https://mega.nz/...</code>\n"
    "• <code>/leech https://drive.google.com/file/d/...</code> (file or "
    "<code>/drive/folders/...</code> folder - downloads every file)\n"
    "• Or attach a <code>.torrent</code> / any file with the command\n"
    "• Write flags after the link: "
    "<code>/leech link -e -z -n new name -ss -sv -cv mp4</code>\n"
    "• Full flag list: <code>/leechhelp</code>\n"
    "⚠️ YT/social links are not supported (no yt-dlp)."
)

_BULK_TASKS = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _BULK_TASKS.add(task)
    task.add_done_callback(_BULK_TASKS.discard)
    return task


def _first_line(text):
    return (text or "").strip().split("\n", 1)[0].strip()


def _has_media(msg):
    return bool(msg and (
        msg.document or msg.video or msg.audio or msg.animation
        or msg.video_note or msg.photo or msg.voice
    ))


def _is_torrent_doc(doc):
    if not doc:
        return False
    name = (doc.file_name or "").lower()
    mime = (doc.mime_type or "").lower()
    return name.endswith(".torrent") or mime == "application/x-bittorrent"


def _drive_login_fix(err):
    """End users cannot fix the bot's Drive login - point at the owner instead."""
    text = str(err)
    if "Connect your Google Drive" in text:
        return (
            "The bot's Google Drive login is missing or expired - "
            "the owner must reconnect it (Settings > Google Drive)."
        )
    return text


def _parse_headers(value):
    """NexonBots -h: 'key: value key1: value1' -> dict."""
    headers = {}
    if not isinstance(value, str) or not value.strip():
        return headers
    key = None
    for tok in value.split():
        if tok.endswith(":") and len(tok) > 1:
            key = tok[:-1]
            headers[key] = ""
        elif ":" in tok and key is None:
            k, v = tok.split(":", 1)
            headers[k] = v
        elif key is not None:
            headers[key] = (headers[key] + " " + tok).strip()
    return {k: v for k, v in headers.items() if k}


def _build_auth(fargs):
    if fargs.get("-au") or fargs.get("-ap"):
        return aiohttp.BasicAuth(
            str(fargs.get("-au") or ""), str(fargs.get("-ap") or "")
        )
    return None


def _transmission_mode(fargs):
    if fargs.get("-ut"):
        return "user"
    if fargs.get("-bt"):
        return "bot"
    if fargs.get("-hl"):
        return "both"
    return None


def _apply_new_name(path, new_name):
    """-n: rename the downloaded file/folder (NexonBots aria2 out equivalent)."""
    try:
        base = sanitize_name(new_name, fallback="")
        if not base or not os.path.exists(path):
            return path
        if os.path.isfile(path) and not os.path.splitext(base)[1]:
            src_ext = os.path.splitext(path)[1]
            if src_ext:
                base += src_ext
        dest = os.path.join(os.path.dirname(path) or ".", base)
        if os.path.abspath(dest) == os.path.abspath(path):
            return path
        if os.path.exists(dest):
            stem, ext = os.path.splitext(base)
            dest = os.path.join(
                os.path.dirname(path) or ".", f"{stem}_{int(time.time())}{ext}"
            )
        os.rename(path, dest)
        LOGGER.info(f"[Leech] -n renamed -> {dest}")
        return dest
    except Exception as e:
        LOGGER.warning(f"[Leech] -n rename failed: {e}")
        return path


def _apply_move_folder(path, download_dir, folder_name):
    """-m: move the download into a folder inside the task dir."""
    try:
        folder = sanitize_name(folder_name, fallback="")
        if not folder:
            return path
        real_dl = os.path.abspath(download_dir)
        real_path = os.path.abspath(path)
        if real_path == real_dl:
            return path
        try:
            if os.path.commonpath([real_path, real_dl]) != real_dl:
                return path
        except ValueError:
            return path
        target_dir = os.path.join(real_dl, folder)
        if os.path.abspath(target_dir) == real_path:
            return path
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, os.path.basename(real_path))
        if os.path.exists(dest):
            stem, ext = os.path.splitext(os.path.basename(real_path))
            dest = os.path.join(target_dir, f"{stem}_{int(time.time())}{ext}")
        shutil.move(real_path, dest)
        LOGGER.info(f"[Leech] -m moved -> {target_dir}")
        return target_dir
    except Exception as e:
        LOGGER.warning(f"[Leech] -m move failed: {e}")
        return path


async def _bulk_lines(client, message):
    """Lines for -b / -i (reply text or a replied text file)."""
    reply = message.reply_to_message
    if not reply:
        return []
    text = None
    if reply.document:
        try:
            path = await reply.download(file_name=f"bulk_{message.id}.txt")
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            try:
                os.remove(path)
            except OSError:
                pass
        except Exception as e:
            LOGGER.warning(f"[Bulk] text file read failed: {e}")
            return []
    elif reply.text:
        text = reply.text
    if not text:
        return []
    return [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


@app.on_message(filters.command(["leechhelp", f"leechhelp@{BOT_USERNAME}"]))
async def leech_help_command(client: Client, message: Message):
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    for chunk in leech_flag_help_messages():
        await message.reply(chunk)
        await asyncio.sleep(0.4)


@app.on_message(filters.command(["leech", "l", f"leech@{BOT_USERNAME}", f"l@{BOT_USERNAME}"]))
async def torrent_command(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    LOGGER.info(f"[Leech] command received: chat={message.chat.id} user={message.from_user.id}")

    user_id = message.from_user.id
    chat_id = message.chat.id
    is_owner = bool(message.from_user and message.from_user.id in AUTH_USERS)

    try:
        # Force subscription
        if not await is_subscribed(app, user_id):
            return await not_joined(app, message)

        # Premium / verification check (shortener-gated like /compress)
        is_premium = await is_premium_user(user_id)
        verify_status = await db.get_verify_status(user_id)
        VERIFY_EXPIRE = await db.get_verified_time()

        SHORT_URL_1 = await db.get_shortener_url1()
        SHORT_API_1 = await db.get_shortener_api1()
        SHORT_URL_2 = await db.get_shortener_url2()
        SHORT_API_2 = await db.get_shortener_api2()

        if (SHORT_API_1 and SHORT_URL_1) or (SHORT_API_2 and SHORT_URL_2):
            v_time = float(verify_status.get('verified_time', 0) or 0)
            if VERIFY_EXPIRE is not None and VERIFY_EXPIRE < (time.time() - v_time):
                await db.update_verify_status(user_id, is_verified=False)
                verify_status = await db.get_verify_status(user_id)
            if not is_premium and not verify_status.get('is_verified', False):
                return await short_url(app, message)

        # --- Flags (NexonBots arg_parser parity) ---
        tokens = list(message.command[1:]) if len(message.command) > 1 else []
        fargs, flink, unknown, set_keys = parse_leech_flags(tokens)

        if unknown:
            shown = " ".join(unknown[:6])
            return await message.reply(
                f"⚠️ Unknown flag(s): <code>{shown}</code>\n"
                f"Use <code>/leechhelp</code>."
            )
        blocked = blocked_flags(set_keys)
        if blocked:
            flag, reason = blocked[0]
            return await message.reply(f"⛔ Flag <code>{flag}</code> is not enabled yet:\n{reason}")
        if "-ff" in set_keys and not is_owner:
            return await message.reply("⛔ <code>-ff</code> (custom ffmpeg cmds) is for the owner only.")
        if "-ut" in set_keys and not Config.USER_SESSION_STRING:
            return await message.reply(
                "⛔ <code>-ut</code> needs USER_SESSION_STRING to be set."
            )

        # --- Bulk / multi (reply to text or .txt with one link per line) ---
        if fargs.get("-b") or fargs.get("-i"):
            return await _start_bulk(client, message, fargs, set_keys, is_owner)

        # --- Input resolution (NexonBots style: inline link > reply > attached file) ---
        torrent_input = flink or None
        torrent_doc = None
        media_msg = None

        if torrent_input:
            LOGGER.info(f"[Leech] Inline input: {torrent_input}")
        elif message.reply_to_message:
            reply = message.reply_to_message
            if reply.document and _is_torrent_doc(reply.document):
                torrent_doc = reply
            elif _has_media(reply):
                media_msg = reply
            elif reply.text:
                torrent_input = _first_line(reply.text)
                LOGGER.info(f"[Leech] Text input (reply): {torrent_input}")
        elif message.document and _is_torrent_doc(message.document):
            torrent_doc = message
        elif _has_media(message):
            media_msg = message

        if not torrent_input and torrent_doc is None and media_msg is None:
            return await message.reply(LEECH_USAGE)

        await _run_leech_task(
            client, message, torrent_input, fargs, set_keys,
            media_msg=media_msg, torrent_doc=torrent_doc,
        )
    except Exception as e:
        LOGGER.error(f"[Leech] Command failure: {e}")
        try:
            return await message.reply(f"❌ Leech failed:\n`{e}`")
        except Exception:
            return


async def _start_bulk(client, message, fargs, set_keys, is_owner):
    lines = await _bulk_lines(client, message)
    if not lines:
        return await message.reply(
            "⚠️ For bulk, reply with a text message or a <code>.txt</code> file "
            "(one link per line).\n"
            "Example: <code>/leech -b</code> (as a reply)\n"
            "Range: <code>/leech -b 2:5</code> or <code>/leech -i 3</code>"
        )

    start, end = 0, len(lines)
    bval = fargs.get("-b")
    if isinstance(bval, str) and bval.strip():
        bits = bval.split(":")
        try:
            start = int(bits[0]) if bits[0] else 0
        except ValueError:
            start = 0
        try:
            end = int(bits[1]) if len(bits) > 1 and bits[1] else len(lines)
        except ValueError:
            end = len(lines)
    elif not fargs.get("-b") and fargs.get("-i"):
        try:
            end = min(len(lines), int(fargs.get("-i")))
        except (TypeError, ValueError):
            end = len(lines)
    start = max(0, start)
    end = max(start, min(end, len(lines)))
    selected = lines[start:end]

    parent_flags = {k: v for k, v in fargs.items() if k not in ("-b", "-i", "link")}
    parent_set = [k for k in set_keys if k not in ("-b", "-i")]

    spawned, skipped = 0, 0
    for line in selected:
        cargs, clink, cunk, cset = parse_leech_flags(line.split())
        if cunk or not clink:
            skipped += 1
            continue
        merged = dict(parent_flags)
        for k in cset:
            if k != "link":
                merged[k] = cargs[k]
        merged_set = list(dict.fromkeys(parent_set + [k for k in cset if k != "link"]))
        if blocked_flags(merged_set):
            skipped += 1
            continue
        if "-ff" in merged_set and not is_owner:
            skipped += 1
            continue
        if "-ut" in merged_set and not Config.USER_SESSION_STRING:
            skipped += 1
            continue
        _spawn(_run_leech_task(client, message, clink, merged, merged_set))
        spawned += 1

    if not spawned:
        return await message.reply(
            f"❌ No link was started ({skipped} skipped). Check the format: "
            f"<code>/leechhelp</code>"
        )
    extra = f", {skipped} skipped" if skipped else ""
    return await message.reply(f"📦 Bulk leech started: {spawned} link(s){extra}.")


async def _run_leech_task(
    client: Client,
    message: Message,
    torrent_input,
    fargs,
    set_keys,
    media_msg=None,
    torrent_doc=None,
):
    user_id = message.from_user.id
    chat_id = message.chat.id
    task_id = None
    download_dir = None
    perrors = []

    try:
        # --- classify ---
        if media_msg is not None:
            kind = "media"
        elif torrent_doc is not None:
            kind = "torrent_file"
        else:
            kind = classify_leech_input(torrent_input)
            if kind == "invalid":
                return await message.reply(f"⚠️ Could not understand the input.\n\n{LEECH_USAGE}")
            if kind == "streaming":
                return await message.reply(
                    "⚠️ This is a social/streaming link (YouTube/Instagram/etc) - "
                    "direct download is not possible, yt-dlp support is not available yet."
                )
            if kind == "ftp":
                return await message.reply(
                    "⚠️ FTP direct links are not supported yet - only HTTP/HTTPS, "
                    "Google Drive, magnet, .torrent and mega links work."
                )

        # --- Task title + dedupe key (flags included so -e vs plain differ) ---
        task_title = "Leech"
        dedupe_src = str(torrent_input or "")
        try:
            if media_msg is not None:
                _media = (
                    media_msg.video or media_msg.document or media_msg.animation
                    or media_msg.audio or media_msg.video_note or media_msg.photo
                    or media_msg.voice
                )
                task_title = (getattr(_media, "file_name", None) or "Telegram file")[:70]
                dedupe_src = f"tgfile:{getattr(_media, 'file_unique_id', '') or media_msg.id}"
            elif torrent_doc is not None:
                task_title = (torrent_doc.document.file_name or "torrent")[:70]
                dedupe_src = f"tgfile:{torrent_doc.document.file_unique_id or torrent_doc.id}"
            elif kind == "magnet":
                task_title = (extract_title_from_magnet(torrent_input) or "Magnet")[:70]
            elif kind in ("http", "torrent_url", "mega"):
                task_title = (torrent_input.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "Download")[:70]
            elif kind == "gdrive":
                gd_kind, _gd_id = parse_drive_url(torrent_input)
                task_title = "Google Drive folder" if gd_kind == "folder" else "Google Drive file"
            elif os.path.exists(str(torrent_input)):
                task_title = os.path.basename(torrent_input)[:70]
        except Exception:
            task_title = "Leech"

        fingerprint = flags_fingerprint(fargs, set_keys)
        task_id, err = await task_manager.register(
            user_id, chat_id, "leech", task_title,
            build_dedupe_key(user_id, dedupe_src, "leech", fingerprint),
            link=torrent_input if str(torrent_input or "").startswith("http") else "",
        )
        if not task_id:
            return await message.reply(err)
        await announce_task(message)

        # --- Prepare directory (unique per task) ---
        download_dir = os.path.abspath(
            f"{LEECH_LOCATION}/{user_id}/torrent_{os.urandom(4).hex()}"
        )
        os.makedirs(download_dir, exist_ok=True)
        LOGGER.info(f"[Leech] Download directory created: {download_dir}")

        if kind == "mega":
            await task_manager.update_progress(task_id, engine="megatools")
        elif kind in ("magnet", "torrent_url", "torrent_file"):
            try:
                import torrentp as _tp
                _ver = str(getattr(_tp, "__version__", "") or "")
                await task_manager.update_progress(
                    task_id, engine=f"torrentp v{_ver}".rstrip(), mode_extra="Torrent"
                )
            except Exception:
                await task_manager.update_progress(task_id, engine="torrentp", mode_extra="Torrent")
        elif kind == "http":
            await task_manager.update_progress(task_id, engine="HTTP Direct")
        elif kind == "gdrive":
            await task_manager.update_progress(task_id, engine="Google Drive")

        # --- per-task thumbnail (-t) ---
        thumb_override = None
        thumb_skip = False
        if fargs.get("-t"):
            thumb_override, thumb_skip, thumb_err = await resolve_thumb_flag(
                client, fargs.get("-t")
            )
            if thumb_err:
                await message.reply(f"⚠️ -t: {thumb_err} (default thumbnail will be used)")
                thumb_override, thumb_skip = None, False

        # --- download ---
        if task_id and task_manager.is_cancelled(task_id):
            return
        if task_id:
            await task_manager.set_phase(task_id, PHASE_DOWNLOADING)

        force_dl = bool(fargs.get("-f") or fargs.get("-fd"))
        dl_ctx = (
            task_manager.download_slot(task_id)
            if (task_id and not force_dl) else nullcontext()
        )
        async with dl_ctx:
            if task_id and task_manager.is_cancelled(task_id):
                return
            dl_path = None
            title = "Unknown_File"
            folder_entries = None
            folder_skipped = 0
            folder_name = ""

            # ==================== TELEGRAM FILE ====================
            if media_msg is not None:
                _media = (
                    media_msg.video or media_msg.document or media_msg.animation
                    or media_msg.audio or media_msg.video_note or media_msg.photo
                    or media_msg.voice
                )
                # SECURITY: filename comes from Telegram metadata - strip any path component
                title = safe_media_name(getattr(_media, "file_name", None) or f"file_{media_msg.id}")
                _tg_start = time.time()
                _tg_last = {"t": 0.0}

                async def _tg_progress(current, total):
                    _now = time.time()
                    _done_flag = bool(total) and current >= total
                    if not _done_flag and (_now - _tg_last["t"]) < 1.0:
                        return
                    _tg_last["t"] = _now
                    _elapsed = max(_now - _tg_start, 0.001)
                    _speed = current / _elapsed
                    _pct = (current * 100.0 / total) if total else 0.0
                    _eta = "N/A"
                    if _speed > 0 and total and total > current:
                        _eta = TimeFormatter(int((total - current) / _speed) * 1000)
                    await task_manager.update_progress(
                        task_id,
                        _pct,
                        f"{humanbytes(_speed)}/s",
                        _eta,
                        done_bytes=current,
                        total_bytes=total or 0,
                    )

                dl_path = await media_msg.download(
                    file_name=os.path.join(download_dir, title),
                    progress=_tg_progress,
                )
                if not dl_path:
                    return await message.reply("❌ Telegram file download failed.")
                LOGGER.info(f"[Leech] Telegram file downloaded: {dl_path}")

            # ==================== MEGA LINK ====================
            elif kind == "mega":
                title = "MEGA_File"
                try:
                    stderr, dl_dir = await mega_coroutine(torrent_input, dir=download_dir)
                except Exception as e:
                    return await message.reply(f"❌ MEGA download failed:\n`{e}`")

                if not dl_dir or not os.path.exists(dl_dir):
                    return await message.reply(f"❌ Invalid MEGA directory: `{dl_dir}`")

                files = get_file_list(dl_dir)
                if not files:
                    return await message.reply("❌ No file found in MEGA folder.")
                dl_path = dl_dir if len(files) > 1 else files[0]

            # ==================== MAGNET / .TORRENT ====================
            elif kind in ("magnet", "torrent_url", "torrent_file"):
                if torrent_doc is not None:
                    # SECURITY: filename comes from Telegram metadata - strip any path component
                    tor_name = safe_media_name(torrent_doc.document.file_name or "download.torrent")
                    torrent_input = await torrent_doc.download(
                        file_name=os.path.join(download_dir, tor_name)
                    )
                    if not torrent_input:
                        return await message.reply("❌ .torrent file download failed.")
                    LOGGER.info(f"[Leech] Torrent file downloaded (reply): {torrent_input}")

                tor_downloader = TorDownloader(path=download_dir)

                if kind == "magnet":
                    title = extract_title_from_magnet(torrent_input)
                elif kind == "torrent_url":
                    title = await extract_title_from_torrent(torrent_input)
                else:
                    title = os.path.basename(torrent_input)

                async def _tor_progress(pct, done, total, speed, seeders, peers):
                    eta = "N/A"
                    if speed > 0 and total > done > 0:
                        eta = TimeFormatter(int((total - done) / speed) * 1000)
                    await task_manager.update_progress(
                        task_id,
                        pct,
                        f"{humanbytes(speed)}/s",
                        eta,
                        detail=(
                            f"Seeders » {seeders} | Leechers » {peers}"
                            if total > 0
                            else "Fetching torrent metadata..."
                        ),
                        done_bytes=done,
                        total_bytes=total,
                    )

                dl_path = await tor_downloader.download(
                    torrent_input,
                    name=title,
                    progress_cb=_tor_progress,
                    should_stop=lambda: task_manager.is_cancelled(task_id),
                )
                if not dl_path and tor_downloader.last_error:
                    return await message.reply(
                        f"❌ Download failed for `{title}`.\n<i>{tor_downloader.last_error}</i>"
                    )

            # ==================== DIRECT HTTP LINK ====================
            elif kind == "http":
                title = (torrent_input.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "Download")[:70]

                async def _http_progress(pct, done, total, speed):
                    eta = "N/A"
                    if speed > 0 and total > done > 0:
                        eta = TimeFormatter(int((total - done) / speed) * 1000)
                    await task_manager.update_progress(
                        task_id,
                        pct,
                        f"{humanbytes(speed)}/s",
                        eta,
                        detail="Direct Link",
                        done_bytes=done,
                        total_bytes=total,
                    )

                dl_path = await http_download(
                    torrent_input,
                    download_dir,
                    progress_cb=_http_progress,
                    should_stop=lambda: task_manager.is_cancelled(task_id),
                    headers=_parse_headers(fargs.get("-h")),
                    auth=_build_auth(fargs),
                )
                if dl_path:
                    title = os.path.basename(dl_path)[:70]

            # ==================== GOOGLE DRIVE LINK ====================
            elif kind == "gdrive":
                gd_kind, file_id = parse_drive_url(torrent_input)
                if not file_id:
                    return await message.reply(
                        "⚠️ Could not read that Google Drive link - send a "
                        "standard file link (<code>.../file/d/ID/view</code>)."
                    )
                gd_uid = await leech_drive_uid(user_id)
                if gd_kind == "folder":
                    if not gd_uid:
                        return await message.reply(
                            "⚠️ Google Drive folder leech needs a Drive login on the "
                            "bot - the owner must connect once "
                            "(Settings > Google Drive)."
                        )
                    try:
                        folder_entries, folder_skipped, folder_name = await drive_list_folder(
                            file_id, gd_uid
                        )
                    except GDriveError as gd_err:
                        return await message.reply(
                            f"❌ Google Drive folder failed:\n`{_drive_login_fix(gd_err)}`"
                        )
                    if not folder_entries:
                        return await message.reply(
                            "⚠️ That folder has no downloadable files."
                        )

                if gd_kind != "folder":
                    async def _gd_progress(pct, done, total, speed):
                        eta = "N/A"
                        if speed > 0 and total > done > 0:
                            eta = TimeFormatter(int((total - done) / speed) * 1000)
                        await task_manager.update_progress(
                            task_id,
                            pct,
                            f"{humanbytes(speed)}/s",
                            eta,
                            detail="Google Drive",
                            done_bytes=done,
                            total_bytes=total,
                        )

                    try:
                        dl_path = await drive_download(
                            file_id,
                            download_dir,
                            user_id=gd_uid or None,
                            progress_cb=_gd_progress,
                            should_stop=lambda: task_manager.is_cancelled(task_id),
                        )
                    except GDriveError as gd_err:
                        return await message.reply(
                            f"❌ Google Drive download failed:\n`{_drive_login_fix(gd_err)}`"
                        )
                    if dl_path:
                        title = os.path.basename(dl_path)[:70]

            # ==================== LOCAL FILE PATH ====================
            elif kind == "local":
                dl_path = torrent_input
                title = os.path.basename(torrent_input)

            else:
                return await message.reply(LEECH_USAGE)

        if task_id and task_manager.is_cancelled(task_id):
            return

        # --- one file: -n/-m rename -> pipeline (join/extract/ff/meta) ->
        #     gather -> -tl tile -> upload; shared by single files and folder
        #     entries (folder mode passes apply_flags=False / report=False)
        async def process_one(path, apply_flags=True, report=True, detail_label=None):
            nonlocal perrors, thumb_override
            if apply_flags and kind != "local":
                if fargs.get("-n") and isinstance(fargs.get("-n"), str) and fargs.get("-n").strip():
                    path = _apply_new_name(path, fargs["-n"])
                if fargs.get("-m") and isinstance(fargs.get("-m"), str) and fargs.get("-m").strip():
                    path = _apply_move_folder(path, download_dir, fargs["-m"])

            if task_id and task_manager.is_cancelled(task_id):
                return False

            # --- NexonBots post-download pipeline: join -> extract -> ff -> meta ->
            #     ns -> ss -> ca/cv -> sv -> zip ---
            should_stop = (lambda: task_id and task_manager.is_cancelled(task_id))

            async def set_phase(phase):
                if task_id:
                    await task_manager.set_phase(task_id, phase)

            async def set_detail(text):
                if task_id:
                    await task_manager.update_progress(task_id, detail=text)

            path, pipe_errors, upload_files = await run_leech_pipeline(
                path,
                fargs,
                download_dir=download_dir,
                task_id=task_id,
                user_id=user_id,
                should_stop=should_stop,
                set_phase=set_phase,
                set_detail=set_detail,
                force=bool(fargs.get("-f")),
            )
            perrors = list(perrors) + list(pipe_errors or [])

            if task_id and task_manager.is_cancelled(task_id):
                return False

            # --- Gather every file for upload (NexonBots style) ---
            if upload_files:
                files_to_upload = [
                    f for f in upload_files
                    if os.path.exists(f) and not f.lower().endswith(".torrent")
                ]
            else:
                files_to_upload = [
                    f for f in gather_files(path)
                    if not f.lower().endswith(".torrent")
                ]

            LOGGER.info(f"[Leech] Found {len(files_to_upload)} file(s) in: {path}")

            if not files_to_upload:
                if report:
                    await message.reply(f"❌ No file found:\n`{path}`")
                return False

            # --- -tl grid thumbnail (built from the first video after processing) ---
            if not thumb_override and not thumb_skip and fargs.get("-tl"):
                try:
                    for cand in files_to_upload:
                        if is_video_file(cand):
                            tile = await build_tile_thumb(cand, str(fargs.get("-tl")))
                            if tile:
                                thumb_override = tile
                            break
                except Exception as e:
                    LOGGER.warning(f"[Leech] -tl failed: {e}")

            # Download is done - drop the torrent-specific seeders/peers line
            if task_id:
                await task_manager.update_progress(task_id, detail=detail_label or "")

            # --- Upload every file ---
            transmission = _transmission_mode(fargs)
            custom_split = (
                parse_split_size(fargs.get("-sp"))
                if "-sp" in set_keys else None
            )
            if fargs.get("-doc"):
                flag_media = "document"
            elif fargs.get("-med"):
                flag_media = "video"
            else:
                flag_media = None
            force_up = bool(fargs.get("-f") or fargs.get("-fu"))

            for file_path in files_to_upload:
                if task_id and task_manager.is_cancelled(task_id):
                    break
                try:
                    file_name = os.path.basename(file_path)
                    spoiler = await db.get_user_spoiler(user_id)
                    if flag_media:
                        media_pref = flag_media
                    else:
                        media_pref = await db.get_media_preference(user_id) or "video"
                    caption = build_media_caption(file_path, delivery=media_pref)

                    is_video = bool(media_pref == "video" and is_video_file(file_path))
                    duration = get_video_duration(file_path) if is_video else None
                    file_size = os.path.getsize(file_path)

                    if thumb_skip:
                        thumb_path = None
                    elif thumb_override:
                        thumb_path = thumb_override
                    else:
                        thumb = await db.get_thumbnail(user_id)
                        if thumb:
                            thumb_path = await client.download_media(thumb)
                        elif is_video:
                            thumb_path = await process_thumbnail(None, video_path=file_path)
                        else:
                            thumb_path = await process_thumbnail_doc(None, video_path=file_path)
                    LOGGER.info(f"[Leech] Uploading: {file_name} ({humanbytes(file_size)})")

                    if task_id:
                        await task_manager.set_phase(task_id, PHASE_UPLOADING)
                    ul_ctx = (
                        task_manager.upload_slot(task_id)
                        if (task_id and not force_up) else nullcontext()
                    )
                    async with ul_ctx:
                        if task_id and task_manager.is_cancelled(task_id):
                            break
                        await smart_split_and_upload(
                            client=client,
                            message=message,
                            file_path=file_path,
                            status_msg=UploadSink(task_id),
                            caption=caption,
                            thumb_path=thumb_path,
                            duration=int(duration) if duration else None,
                            user_id=user_id,
                            reply_to_id=message.id,
                            task_id=task_id,
                            split_size=custom_split,
                            media_pref=media_pref,
                            transmission=transmission,
                            use_msg_flags=False,
                        )
                except Exception as up_err:
                    LOGGER.error(f"[Leech] Upload failed for {file_path}: {up_err}")
                    perrors.append(f"{os.path.basename(file_path)}: {up_err}")

            LOGGER.info(f"[Leech] ✅ All uploads finished for user {user_id}.")
            return True

        if folder_entries is not None:
            # ==================== GOOGLE DRIVE FOLDER LEECH ====================
            total = len(folder_entries)
            folder_count = total
            done_count = 0
            failed_count = 0
            for idx, (fid, fname, _fsize) in enumerate(folder_entries, 1):
                if task_id and task_manager.is_cancelled(task_id):
                    break
                fdir = os.path.join(download_dir, f"gfold_{idx:04d}")
                os.makedirs(fdir, exist_ok=True)

                async def _gf_progress(pct, done, total, speed, _i=idx, _t=folder_count):
                    eta = "N/A"
                    if speed > 0 and total > done > 0:
                        eta = TimeFormatter(int((total - done) / speed) * 1000)
                    overall = (
                        ((_i - 1) + max(0.0, min(float(pct), 100.0)) / 100.0) * 100.0 / _t
                    )
                    await task_manager.update_progress(
                        task_id,
                        overall,
                        f"{humanbytes(speed)}/s",
                        eta,
                        detail=f"Google Drive {_i}/{_t}",
                        done_bytes=done,
                        total_bytes=total,
                    )

                try:
                    one_dl_ctx = (
                        task_manager.download_slot(task_id)
                        if (task_id and not force_dl) else nullcontext()
                    )
                    async with one_dl_ctx:
                        if task_id and task_manager.is_cancelled(task_id):
                            break
                        fpath = await drive_download(
                            fid,
                            fdir,
                            user_id=gd_uid or None,
                            progress_cb=_gf_progress,
                            should_stop=lambda: task_manager.is_cancelled(task_id),
                        )
                except GDriveError as gd_err:
                    failed_count += 1
                    perrors.append(f"{fname}: {gd_err}")
                    continue

                if not fpath:
                    break

                try:
                    ok = await process_one(
                        fpath,
                        apply_flags=False,
                        report=False,
                        detail_label=f"Google Drive {idx}/{total}",
                    )
                    if ok:
                        done_count += 1
                    else:
                        failed_count += 1
                finally:
                    shutil.rmtree(fdir, ignore_errors=True)
                if task_id and task_manager.is_cancelled(task_id):
                    break

            label = folder_name or "Folder"
            summary = f"✅ {label} - {done_count}/{total} uploaded"
            if folder_skipped:
                summary += f", {folder_skipped} skipped (Google Docs/shortcuts)"
            if failed_count:
                summary += f", {failed_count} failed"
            if task_id and task_manager.is_cancelled(task_id):
                summary = f"⚠️ Cancelled - {summary}"
            await safe_send(message.reply, summary)
        else:
            # ==================== SINGLE FILE ====================
            if not dl_path or not os.path.exists(dl_path):
                return await message.reply(f"❌ Download failed for `{title}`.")
            if not await process_one(dl_path, apply_flags=True, report=True):
                return

        if perrors:
            shown = "\n".join(f"• `{e}`" for e in perrors[:8])
            more = f"\n… and {len(perrors) - 8} more" if len(perrors) > 8 else ""
            await safe_send(message.reply, f"⚠️ Some steps/uploads failed:\n{shown}{more}")

    except Exception as e:
        await safe_send(message.reply, f"❌ Leech failed:\n`{e}`")
        LOGGER.error(f"[Leech] Error: {e}")

    finally:
        if task_id:
            try:
                await task_manager.complete(task_id)
            except Exception:
                pass
        if download_dir:
            try:
                shutil.rmtree(download_dir, ignore_errors=True)
                LOGGER.info(f"[Leech] Cleaned up: {download_dir}")
            except Exception as cleanup_err:
                LOGGER.warning(f"[Leech] Cleanup error: {cleanup_err}")
