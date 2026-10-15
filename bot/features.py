# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys
import psutil
#import datetime as dt
from datetime import datetime, timedelta 
from pathlib import Path
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, CallbackQuery
from bot.button_styles import InlineKeyboardButton
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from mimetypes import guess_type
from bot.config import Config
from PIL import Image
import aiofiles
import mimetypes

from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, data1, data2, data3, data4, data5, data6, data7, crop, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.localisation import Localisation
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.helper_funcs.display_progress import *
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
from bot.commands import Command
from bot.plugins.call_back_button_handler import *
from bot.watermark import *
from bot.split_videos import *
from bot.merge_video import *
from bot.subtitles import *
from bot.thumbnail import *
from bot.compress import *
from bot.audio import *
from bot.fsub import *

@app.on_message(filters.incoming & filters.command(["start", f"start@{BOT_USERNAME}"]))
async def incoming_start_message_f(bot: Client, update: Message):
    """/start command handler"""

    user_id = update.from_user.id
    if not await db.present_user(user_id):
        try:
            await db.add_user(user_id)
        except Exception as e:
            logging.error(f"Error adding user: {e}")
            return

    VERIFY_EXPIRE = await db.get_verified_time()
    verify_status = await db.get_verify_status(user_id)
    SHORT_URL_1 = await db.get_shortener_url1()
    SHORT_API_1 = await db.get_shortener_api1()
    TUTORIAL1 = await db.get_tut_video1()

    SHORT_URL_2 = await db.get_shortener_url2()
    SHORT_API_2 = await db.get_shortener_api2()
    TUTORIAL2 = await db.get_tut_video2()

    # ✅ Token verification
    if (SHORT_URL_1 and SHORT_API_1) or (SHORT_URL_2 and SHORT_API_2):
        # If already verified but expired → reset
        if verify_status and verify_status.get("is_verified"):
            if VERIFY_EXPIRE < (time.time() - verify_status.get("verified_time", 0)):
                await db.update_verify_status(user_id, is_verified=False)

        # Check if user came with a verify token
        if "verify_" in update.text:
            _, token = update.text.split("_", 1)
            if not verify_status or verify_status.get("verify_token") != token:
                return await update.reply("⚠️ 𝖨𝗇𝗏𝖺𝗅𝗂𝖽 𝗍𝗈𝗄𝖾𝗇. 𝖯𝗅𝖾𝖺𝗌𝖾 /start 𝖺𝗀𝖺𝗂𝗇.")

            await db.update_verify_status(user_id, is_verified=True, verified_time=time.time())
            #current = await db.get_verify_count(user_id) or 0
            #await db.set_verify_count(user_id, current + 1)
        
            return await update.reply(
                f"✅ 𝗧𝗼𝗸𝗲𝗻 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝘃𝗲𝗿𝗶𝗳𝗶𝗲𝗱!\n\n"
                f"Vᴀʟɪᴅ ғᴏʀ {get_exp_time(VERIFY_EXPIRE)}",
                reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ᴜsᴇ ʜᴇʀᴇ 🤝", url="https://t.me/Video_Compressor_Free")]
                ])
            )


    # 🟢 Default /start message
    await bot.send_photo(
        chat_id=update.chat.id,
        photo=random.choice(Config.PICS),
        caption=Localisation.START_TEXT.format(
            first=update.from_user.first_name,
            last=update.from_user.last_name,
            username=None if not update.from_user.username else '@' + update.from_user.username,
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



@app.on_message(filters.command(["clear", f"clear@{BOT_USERNAME}"]))
async def clear_all_queues(client: Client, message: Message):
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text("<blockquote><b>Admin Only</b> 💀</blockquote>")

    # Clear all queues
    extractaudio_queue.clear(); extractaudio_requests.clear()
    remaudio_queue.clear(); remaudio_requests.clear()
    audio_requests.clear(); audio_queue.clear()
    addaudio_requests.clear(); addaudio_queue.clear()
    merge_queue.clear(); user_merge_sessions.clear()
    cut_queue.clear(); rsub_queue.clear(); rsub_requests.clear()
    subtitle_requests.clear(); subtitle_queue.clear()
    hardsub_requests.clear(); hardsub_queue.clear()
    extractsub_queue.clear(); extractsub_requests.clear()
    watermark_queue.clear()
    crop.clear()
    data.clear(); data1.clear(); data2.clear(); data3.clear()
    data4.clear(); data5.clear(); data6.clear(); data7.clear()

    await message.reply("🧹 All queues have been cleared successfully.")


@app.on_message(filters.command(["update", f"update@{BOT_USERNAME}"]))
async def update_bot(client, message: Message):
    if not (message.from_user and message.from_user.id in AUTH_USERS):
        return await message.reply_text(
            "<blockquote><b>Aᴅᴍɪɴ Oɴʟʏ</b> 💀</blockquote>", parse_mode=ParseMode.HTML
        )

    sent = await message.reply("🔄 Pᴜʟʟɪɴɢ ʟᴀᴛᴇsᴛ ᴜᴘᴅᴀᴛᴇs ғʀᴏᴍ Gɪᴛ...")

    token = (Config.GIT_TOKEN or os.environ.get("GIT_TOKEN", "")).strip()
    upstream = (Config.UPSTREAM_REPO or os.environ.get("UPSTREAM_REPO", "")).strip()
    force = "force" in [a.lower() for a in (message.text or "").split()[1:]]

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Resolve source: UPSTREAM_REPO secret wins, else current origin remote.
    rc, cur_url, _ = await _run_git(["remote", "get-url", "origin"], env)
    source = upstream or (cur_url.splitlines()[0].strip() if rc == 0 and cur_url else "")
    if not source:
        return await sent.edit("❌ No git remote found and UPSTREAM_REPO secret is empty.")
    target = _normalize_repo_url(source, token)
    if not target:
        return await sent.edit("❌ Could not resolve repository URL.")

    old_sha, _ = await _git_rev(env)
    old_ver = _read_version()

    # Default branch: current branch, else remote HEAD, else main.
    rc_b, branch, _ = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], env)
    if rc_b != 0 or not branch or branch == "HEAD":
        rc_l, ls, _ = await _run_git(["ls-remote", "--symref", target, "HEAD"], env)
        branch = "main"
        if rc_l == 0:
            for line in ls.splitlines():
                if line.startswith("ref:") and "refs/heads/" in line:
                    branch = line.split("refs/heads/", 1)[1].split("\t")[0].split()[0]
                    break

    rc, out, err = await _run_git(["fetch", "--prune", "--tags", target, branch], env)
    if rc != 0:
        return await sent.edit(
            f"❌ Git fetch failed:\n<code>{_scrub(_err(out, err), token)}</code>"
        )

    if force:
        rc, out, err = await _run_git(["reset", "--hard", "FETCH_HEAD"], env)
    else:
        rc, out, err = await _run_git(["merge", "--ff-only", "FETCH_HEAD"], env)
    if rc != 0:
        return await sent.edit(
            "❌ Git pull failed:\n<code>"
            f"{_scrub(_err(out, err), token)}</code>\n\n"
            "💡 Local changes are blocking the update. Send <code>/update force</code> "
            "to discard them and reset to upstream."
        )

    new_sha, _ = await _git_rev(env)
    new_ver = _read_version()

    if old_sha == new_sha:
        return await sent.edit(
            f"✅ Already up to date — <code>{old_ver or old_sha}</code>"
        )

    await sent.edit(
        f"🚀 <b>{new_ver or 'Update'} released!</b>\n"
        f"<code>{old_ver or old_sha}</code> → <code>{new_ver or new_sha}</code>\n\n"
        f"<blockquote>{_scrub(out or 'Updated.', token)}</blockquote>\n\n"
        "♻️ Rᴇsᴛᴀʀᴛɪɴɢ ʙᴏᴛ..."
    )
    await asyncio.sleep(2)
    os.execvp(sys.executable, [sys.executable, "-m", "bot"])


def _read_version() -> str:
    try:
        with open("VERSION", "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _normalize_repo_url(url: str, token: str = "") -> str:
    """HTTPS-fy SSH/shorthand URLs and inject GIT_TOKEN.

    Fixes 'Host key verification failed' (SSH remotes) and lets private
    upstream repos work via a personal access token.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("ssh://"):
        url = url[len("ssh://"):]
    if url.startswith("git@"):
        url = "https://" + url[4:].replace(":", "/", 1)
    elif "://" not in url and url.count("/") == 1 and " " not in url:
        url = f"https://github.com/{url}.git"
    if token and url.startswith("https://"):
        rest = url[len("https://"):]
        if "@" not in rest.split("/", 1)[0]:
            url = f"https://x-access-token:{token}@{rest}"
    return url


async def _run_git(args, env):
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180.0)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 124, "", "git command timed out after 180s"
    except FileNotFoundError:
        return 127, "", "git executable not found"
    return (
        proc.returncode or 0,
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
    )


async def _git_rev(env):
    rc, out, _ = await _run_git(["rev-parse", "--short", "HEAD"], env)
    return (out.strip() if rc == 0 else ""), rc


def _err(out: str, err: str) -> str:
    return (err or out or "unknown git error").strip()


def _scrub(text: str, token: str) -> str:
    """Never echo the git token back into chat/logs."""
    if token and token in text:
        text = text.replace(token, "***")
    return text


@app.on_message(filters.command(["setmedia", f"setmedia@{BOT_USERNAME}"]))
async def set_media_command(app, message: Message):
    # SECURITY: authorize on the sender's user id, not the chat id (chat ids never match AUTH_USERS)
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)
    user_id = message.from_user.id
    current = await db.get_media_preference(user_id)
    if not current:
        current = "video"
        await db.set_media_preference(user_id, current)

    keyboard = build_media_keyboard(current, user_id)
    await message.reply_text(
        "**Sᴇʟᴇᴄᴛ ʏᴏᴜʀ ᴘʀᴇғᴇʀʀᴇᴅ ᴍᴇᴅɪᴀ ᴛʏᴘᴇ:**\n"
        "**Tʜɪs ᴡɪʟʟ ᴅᴇᴛᴇʀᴍɪɴᴇ ʜᴏᴡ ʏᴏᴜʀ ғɪʟᴇs ᴀʀᴇ ʜᴀɴᴅʟᴇᴅ ʙʏ ᴛʜᴇ ʙᴏᴛ.**",
        reply_markup=keyboard, quote=True
    )


@app.on_message(filters.command(["stats", f"stats@{BOT_USERNAME}"]))
async def system_info(client: Client, message: Message):
    try:
        # SECURITY: /stats exposes host resource info, restrict to admins
        if not is_authorised(message):
            return await message.reply_text("<blockquote><b>Admin Only</b> 💀</blockquote>")

        # measure ping
        start_time = time.time()
        sent = await message.reply_text("⏳ Calculating ping...")
        end_time = time.time()
        ping = (end_time - start_time) * 1000

        # system stats
        # interval=None is non-blocking (value since last call) - interval=1 stalls the bot
        cpu_usage = psutil.cpu_percent(interval=None)
        cpu_cores = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # uptime calculation
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_delta = timedelta(seconds=int(uptime_seconds))
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours:02d}h{minutes:02d}m{seconds:02d}s"

        # helpers
        def format_size(size_bytes):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return "0 B"

        def create_progress_bar(percentage, length=10):
            filled = int(percentage / 100 * length)
            return f"[{'■'*filled}{'□'*(length-filled)}]"

        # build status text
        status_text = (
            f"<b>⌬ SERVER INFO :</b>\n\n"
            f"<b>┎ Uptime :</b> {uptime_str}\n"
            f"<b>┖ Ping :</b> {ping:.3f} ms\n\n"
            f"<b>┎ CPU :</b>\n"
            f"<b>┃ Usage :</b> {create_progress_bar(cpu_usage)} {cpu_usage}%\n"
            f"<b>┖ Cores :</b> {cpu_cores}\n\n"
            f"<b>┎ RAM :</b>\n"
            f"<b>┃ Usage :</b> {create_progress_bar(mem.percent)} {mem.percent}%\n"
            f"<b>┃ Used :</b> {format_size(mem.used)}\n"
            f"<b>┃ Free :</b> {format_size(mem.available)}\n"
            f"<b>┖ Total :</b> {format_size(mem.total)}\n\n"
            f"<b>┎ DISK :</b>\n"
            f"<b>┃ Usage :</b> {create_progress_bar(disk.percent)} {disk.percent}%\n"
            f"<b>┃ Used :</b> {format_size(disk.used)}\n"
            f"<b>┃ Free :</b> {format_size(disk.free)}\n"
            f"<b>┖ Total :</b> {format_size(disk.total)}\n"
        )

        try:
            await sent.edit_text(status_text, parse_mode=ParseMode.HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await sent.edit_text(status_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        LOGGER.error(f"Error in system_info: {e}", exc_info=True)
        try:
            await message.reply_text("❌ Error while fetching system info.", parse_mode=ParseMode.HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_text("❌ Error while fetching system info.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command(["spoiler", f"spoiler@{BOT_USERNAME}"]))
async def spoiler_command(app, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id
    current = await db.get_user_spoiler(user_id)
    if current is None:
        current = "off"
        await db.set_user_spoiler(user_id, current)

    keyboard = build_spoiler_keyboard(current, user_id)

    text = (
        "**🎎 Sᴇʟᴇᴄᴛ Sᴘᴏɪʟᴇʀ Mᴏᴅᴇ:**\n\n"
        "Tʜɪs ᴅᴇᴛᴇʀᴍɪɴᴇs ɪғ ʏᴏᴜʀ ғɪʟᴇs ᴡɪʟʟ ʙᴇ sᴇɴᴛ ᴡɪᴛʜ sᴘᴏɪʟᴇʀ.\n\n"
        "<blockquote> Nᴏᴛᴇ: ᴛᴏ ɢᴇᴛ sᴘᴏɪʟᴇʀ ᴜsᴇ /setmedia ᴀɴᴅ ᴄʜᴀɴɢᴇ ᴛᴏ ᴠɪᴅᴇᴏ </blockquote>"
    )

    await message.reply_text(
        text,
        reply_markup=keyboard,
        quote=True
    )

# ===== /upload command ===== #
@app.on_message(filters.command(["upload", f"upload@{BOT_USERNAME}"]))
async def upload_command(app, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id
    current = await db.get_upload_preference(user_id)
    if not current:
        current = "group"  # default fallback
        await db.set_upload_preference(user_id, current)

    # Get saved channel (if any)
    channel_id = await db.get_user_channel(user_id)

    keyboard = build_upload_keyboard(current, user_id, channel_id)

    await message.reply_text(
        "**Sᴇʟᴇᴄᴛ ʏᴏᴜʀ ᴜᴘʟᴏᴀᴅ ᴘʀᴇғᴇʀᴇɴᴄᴇ:**\n"
        "- Dᴍ → Fɪʟᴇs ᴡɪʟʟ ᴄᴏᴍᴇ ᴅɪʀᴇᴄᴛʟʏ ᴛᴏ ʏᴏᴜʀ ᴘᴍ.\n"
        "- Cʜᴀɴɴᴇʟ → Fɪʟᴇs ᴡɪʟʟ ɢᴏ ᴛᴏ ʏᴏᴜʀ sᴇᴛ ᴄʜᴀɴɴᴇʟ.\n"
        "- Tʜɪs Gʀᴏᴜᴘ → Fɪʟᴇs ᴡɪʟʟ sᴛᴀʏ ʜᴇʀᴇ.",
        reply_markup=keyboard,
        quote=True
    )


# ===== SET CHANNEL ===== #
@app.on_message(filters.command(["setchannel", f"setchannel@{BOT_USERNAME}"]))
async def set_channel_cmd(app, message: Message):
    # SECURITY: authorize on the sender's user id, not the chat id (chat ids never match AUTH_USERS)
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id

    # Extract channel ID/username from message
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(
            "⚠️ Usage:\n\n"
            "`/setchannel <channel_id or @username>`\n\n"
            "📌 Examples:\n"
            "`/setchannel @my_channel`\n"
            "`/setchannel -1001234567890`\n\n"
            "👉 The bot **must be an Admin** in that channel with permission to post messages.",
            quote=True
        )

    channel = parts[1].strip()

    try:
        # Check bot is admin in channel
        chat = await app.get_chat(channel)
        member = await app.get_chat_member(chat.id, "me")
        if not member.privileges or not member.privileges.can_post_messages:
            return await message.reply_text(
                "❌ I must be an **admin with posting rights** in that channel.",
                quote=True
            )

        # Save to DB
        await db.set_user_channel(user_id, chat.id)

        return await message.reply_text(
            f"✅ Cʜᴀɴɴᴇʟ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ ᴛᴏ: **{chat.title}** (`{chat.id}`)",
            quote=True
        )

    except Exception as e:
        LOGGER.error(f"SetChannel error: {e}")
        return await message.reply_text(
            f"❌ Failed to set channel.\nError: `{e}`",
            quote=True
        )


# ===== GET CHANNEL ===== #
@app.on_message(filters.command(["getchannel", f"getchannel@{BOT_USERNAME}"]))
async def get_channel_cmd(app, message: Message):
    # SECURITY: authorize on the sender's user id, not the chat id (chat ids never match AUTH_USERS)
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id
    channel_id = await db.get_user_channel(user_id)

    if not channel_id:
        return await message.reply_text("⚠️ No channel is set for you.", quote=True)

    try:
        chat = await app.get_chat(channel_id)
        return await message.reply_text(
            f"📢 Cᴜʀʀᴇɴᴛ ᴄʜᴀɴɴᴇʟ: **{chat.title}** (`{chat.id}`)",
            quote=True
        )
    except Exception as e:
        LOGGER.warning(f"GetChannel error: {e}")
        return await message.reply_text(
            f"⚠️ Cʜᴀɴɴᴇʟ ID ɪɴ DB: `{channel_id}`\n(But I may not have access to it anymore!)",
            quote=True
        )


# ===== DELETE CHANNEL ===== #
@app.on_message(filters.command(["delchannel", f"delchannel@{BOT_USERNAME}"]))
async def del_channel_cmd(app, message: Message):
    # SECURITY: authorize on the sender's user id, not the chat id (chat ids never match AUTH_USERS)
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    user_id = message.from_user.id
    channel_id = await db.get_user_channel(user_id)

    if not channel_id:
        return await message.reply_text("⚠️ 𝗬𝗼𝘂 𝗱𝗼𝗻’𝘁 𝗵𝗮𝘃𝗲 𝗮𝗻𝘆 𝗰𝗵𝗮𝗻𝗻𝗲𝗹 𝘀𝗲𝘁.", quote=True)

    try:
        await db.del_user_channel(user_id)
        return await message.reply_text("🗑️ Yᴏᴜʀ ᴄʜᴀɴɴᴇʟ ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ sᴇᴛᴛɪɴɢs.", quote=True)
    except Exception as e:
        LOGGER.error(f"DelChannel error: {e}")
        return await message.reply_text(f"❌ Failed to delete channel.\nError: `{e}`", quote=True)
