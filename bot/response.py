# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import os
import re
import html
import json
import time
import asyncio
import aiofiles
import aiohttp
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message

# --- Config (import yours here) ---
# SECURITY: /mediainfo previously had no authorization gate at all.
# NOTE: AUTH_USERS lives on bot/__init__ (bot.AUTH_USERS), NOT bot.config —
# config.py only defines it as a Config class attribute.
from bot import app, LOGGER, AUTH_USERS, is_authorised
from bot.localisation import Localisation
from bot.fsub import is_subscribed, not_joined, short_url
from bot.premium import is_premium_user
from database import db

PASTYX_API_URL = "https://pastyx.pages.dev/api/paste"

# --- Section Emojis (match the APEX-style PastyX layout) ---
section_dict = {
    "General": "🗒",
    "Video": "📊",
    "Audio": "🔊",
    "Text": "📝",
    "Menu": "🗃",
}
SECTION_TITLE = "🚀"

CHUNK_LIMIT = 5  # number of chunks to download
CHUNK_SIZE = 10 * 1024 * 1024  # 10MB each chunk


# --- Utility Functions ---

async def extract_text_info(file_path: str) -> str:
    """Run mediainfo for readable output"""
    cmd = ["mediainfo", file_path]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    return stdout.decode()


def parseinfo_blocks(out: str, size: int):
    """Convert mediainfo output into Telegraph JSON blocks with emojis & sections"""
    blocks = []
    size_line = f"File size : {size / (1024 * 1024):.2f} MiB"

    current_section = None
    section_lines = []

    for line in out.split("\n"):
        # Detect section
        for section, emoji in section_dict.items():
            if line.startswith(section):
                # If switching section, push old one
                if current_section and section_lines:
                    blocks.append({"tag": "h4", "children": [current_section]})
                    blocks.append({"tag": "pre", "children": ["\n".join(section_lines)]})
                # Start new section
                section_lines = []
                current_section = f"{emoji} {line.replace('Text', 'Subtitle')}"
                break
        else:
            # Replace filesize line
            if line.startswith("File size"):
                line = size_line
            if line.strip():
                section_lines.append(line)

    # Push last section
    if current_section and section_lines:
        blocks.append({"tag": "h4", "children": [current_section]})
        blocks.append({"tag": "pre", "children": ["\n".join(section_lines)]})

    return blocks


async def partial_download(media, file_path):
    """Download only first few chunks of the media for fast mediainfo"""
    downloaded = 0
    async for chunk in app.stream_media(media, limit=CHUNK_LIMIT):
        async with aiofiles.open(file_path, "ab") as f:
            await f.write(chunk)
        downloaded += 1
        if downloaded >= CHUNK_LIMIT:
            break


def _escape_md(text: str) -> str:
    """Kept for compatibility (unused by the HTML layout)."""
    return str(text or "")


# PastyX renders raw HTML: these are the exact styles of the reference
# APEX layout (teal title, blue section heads, green-bordered boxes,
# gradient separators). Markdown can never reproduce them.
_H3_TITLE = (
    "<h3 style='font-weight: bold; font-size: 1.3rem; color: #00d4aa;'>"
    "🚀 {name}</h3>"
)
_H4_SECTION = (
    "<h4 style='font-weight: bold; font-size: 1.1rem; color: #00a8ff;'>"
    "{emoji} {sec}</h4>"
)
_PRE_BOX = (
    "<pre style='font-weight: bold; line-height: 1.5; "
    "border-left: 5px solid #00d4aa; padding: 15px; "
    "background-color: rgba(0, 212, 170, 0.05); border-radius: 8px; "
    "overflow-x: auto; box-shadow: inset 0 0 10px rgba(0,0,0,0.05);'>"
    "{body}</pre>"
)
_HR_GRADIENT = (
    "<hr style='height: 4px; border: none; "
    "background: linear-gradient(to right, #00d4aa, #00a8ff); "
    "border-radius: 4px; box-shadow: 0 2px 4px rgba(0, 168, 255, 0.3); "
    "margin: 15px 0;'>"
)


def build_mediainfo_markdown(raw_info: str, file_name: str, file_size: int = 0) -> str:
    """APEX-style PastyX report (HTML layout, colored like the reference).

    Pure function (headless-testable). Falls back to a single raw box when
    the mediainfo text has no recognizable sections.
    """
    clean_name = html.escape((file_name or "media").replace("`", ""))
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None

    for line in (raw_info or "").split("\n"):
        stripped = line.strip()
        if stripped in section_dict:
            if current and current[1]:
                sections.append(current)
            pretty = "Subtitle" if stripped == "Text" else stripped
            current = (f"{section_dict[stripped]} {pretty}", [])
            continue
        if not stripped:
            continue
        if stripped.startswith("File size") and file_size:
            line = f"File size                                : {file_size / (1024 * 1024):.2f} MiB"
        if current is None:
            current = ("🗒 General", [])
        # HTML needs no markdown escaping; only neutralize HTML itself.
        current[1].append(html.escape(line.rstrip()))
    if current and current[1]:
        sections.append(current)

    if not sections:
        safe = html.escape(raw_info or "")
        return f"{_H3_TITLE.format(name=clean_name)}\n<br><br>\n{_PRE_BOX.format(body=safe)}\n<br>\n"

    parts = [_H3_TITLE.format(name=clean_name), "<br><br>"]
    for idx, (heading, lines) in enumerate(sections):
        emoji, _, sec = heading.partition(" ")
        parts.append(_H4_SECTION.format(emoji=emoji, sec=html.escape(sec)))
        parts.append("<br>")
        parts.append(_PRE_BOX.format(body="\n".join(lines)))
        parts.append("<br>")
        if idx < len(sections) - 1:
            parts.append(_HR_GRADIENT)
            parts.append("<br>")
    return "\n".join(parts) + "\n"


async def create_pastyx_page(raw_info: str, file_name: str, file_size: int = 0) -> str:
    """Publish a MediaInfo report to PastyX and return its public URL."""
    markdown = build_mediainfo_markdown(raw_info, file_name, file_size)
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            PASTYX_API_URL,
            json={
                "content": markdown,
                "title": f"MediaInfo - {file_name}"[:120],
                "author": "@NexonBots",
                "expiry": "1week",
            },
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            page_url = payload.get("url")
            if not page_url:
                raise RuntimeError("PastyX response did not include a URL")
            return page_url


# --- Telegram Handler ---

@app.on_message(filters.command(["mediainfo", "mi"]))
async def mediainfo_handler(_, message: Message):
    # SECURITY: this command had no AUTH/FSub/verify gate - same gates as /compress
    if not is_authorised(message):
        return await message.reply(Localisation.NOT_AUTH)

    if not await is_subscribed(app, message.from_user.id):
        return await not_joined(app, message)

    is_premium = await is_premium_user(message.from_user.id)
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

    file_path = None
    try:
        reply = message.reply_to_message
        if not reply:
            return await message.reply("⚠️ Please reply to a valid media file.")

        media = reply.video or reply.document
        if not media or not media.file_name:
            return await message.reply("⚠️ Please reply to a valid media file.")

        # Create download folder
        Path("./downloads").mkdir(parents=True, exist_ok=True)
        safe_name = os.path.basename(media.file_name)
        file_path = os.path.join(
            "./downloads", f"{message.chat.id}_{message.id}_{safe_name}"
        )

        wait_msg = await message.reply("⏳ Pʟᴇᴀsᴇ ᴡᴀɪᴛ... Dᴏᴡɴʟᴏᴀᴅɪɴɢ ғᴏʀ MᴇᴅɪᴀIɴғᴏ.")

        # Try partial download
        await partial_download(media, file_path)
        await wait_msg.edit("🔍 Exᴛʀᴀᴄᴛɪɴɢ MᴇᴅɪᴀIɴғᴏ...")

        raw_info = await extract_text_info(file_path)

        # Fallback: if mediainfo failed (empty output), do full download
        if not raw_info.strip():
            #await wait_msg.edit("⚠️ Partial download failed. Downloading full file...")
            await message.reply_to_message.download(file_path)
            raw_info = await extract_text_info(file_path)

        file_size = media.file_size or os.path.getsize(file_path)

        # The PastyX link IS the response for /mi and /mediainfo alike - no .txt
        # attachment is sent. If the paste service is down the report is inlined
        # instead so nothing has to be downloaded.
        page_url = None
        try:
            page_url = await create_pastyx_page(raw_info, safe_name, file_size)
        except Exception as paste_error:
            LOGGER.warning("PastyX unavailable; sending MediaInfo inline: %s", paste_error)

        if not page_url:
            await wait_msg.delete()
            for start in range(0, len(raw_info), 4000):
                chunk = raw_info[start:start + 4000]
                if not chunk.strip():
                    continue
                await message.reply(f"<pre>{html.escape(chunk)}</pre>")
            return

        caption = (
            f"🧾 <b>𝙈𝙚𝙙𝙞𝙖 𝙄𝙣𝙛𝙤: ʙʏ @NexonBots</b>\n\n"
            f"📄 <b>𝙁𝙞𝙡𝙚𝙣𝙖𝙢𝙚:</b> <code>{html.escape(safe_name)}</code>\n"
            f"📎 <a href='{page_url}'>Cʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴠɪᴇᴡ ғᴜʟʟ MᴇᴅɪᴀIɴғᴏ</a>\n\n"
        )

        await message.reply(caption, disable_web_page_preview=False)
        await wait_msg.delete()

    except Exception as e:
        await message.reply(f"❌ Error:\n<code>{html.escape(str(e))}</code>")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
