# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from datetime import datetime as dt
import os, math, asyncio, aiohttp, shutil, time, subprocess, sys
from pathlib import Path
from pyrogram import Client, filters #InputFile
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
    data, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.localisation import Localisation
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
#from pyrogram.types import InputFile
from bot.plugins.call_back_button_handler import button


@app.on_message(filters.command(["extract_thumb", f"extract_thumb@{BOT_USERNAME}"]))
async def get_file_thumb(client, message: Message):
    # SECURITY: restrict to admin users (mirrors /setthumb below)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    if not message.reply_to_message or not (message.reply_to_message.document or message.reply_to_message.video):
        return await message.reply_text("**Pʟᴇᴀsᴇ Rᴇᴘʟʏ ᴛᴏ ᴀ Dᴏᴄᴜᴍᴇɴᴛ ᴏʀ Vɪᴅᴇᴏ ᴛʜᴀᴛ ʜᴀs ᴀ Tʜᴜᴍʙɴᴀɪʟ.**")

    media = message.reply_to_message.document or message.reply_to_message.video

    thumb = (
        media.thumbs[0] if getattr(media, "thumbs", None)
        else media.thumbnail if getattr(media, "thumbnail", None)
        else None
    )

    if not thumb:
        return await message.reply_text("**Nᴏ Tʜᴜᴍʙɴᴀɪʟ Fᴏᴜɴᴅ ɪɴ ᴛʜᴀᴛ ᴍᴇᴅɪᴀ.**")

    status_msg = await message.reply_text("**Fᴇᴛᴄʜɪɴɢ Tʜᴜᴍʙɴᴀɪʟ... Pʟᴇᴀsᴇ Wᴀɪᴛ.**")

    try:
        downloaded_thumb = await client.download_media(thumb)
        await client.send_photo(chat_id=message.chat.id, photo=downloaded_thumb, caption="**Hᴇʀᴇ ɪs ᴛʜᴇ Tʜᴜᴍʙɴᴀɪʟ.**")
        os.remove(downloaded_thumb)
    except Exception as e:
        await message.reply_text(f"**Eʀʀᴏʀ:** `{e}`")
    finally:
        await status_msg.delete()

# /setthumb command
@app.on_message(filters.command(["setthumb", f"setthumb@{BOT_USERNAME}"]))
async def set_thumb_handler(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    if not message.reply_to_message:
        return await message.reply("⚠️ Reply to an image/photo/document to set as thumbnail.")

    media = None

    # Case 1: Direct photo
    if message.reply_to_message.photo:
        media = message.reply_to_message.photo

    # Case 2: Document but actually image
    elif message.reply_to_message.document:
        mime = message.reply_to_message.document.mime_type or ""
        if mime.startswith("image/"):  # e.g., image/jpeg, image/png
            media = message.reply_to_message.document

    if not media:
        return await message.reply("⚠️ Only images are allowed as thumbnail (photo or image document).")

    # Download the media
    downloaded_path = await client.download_media(media)

    # Upload again to get a consistent file_id (Telegram assigns file_id for photos only)
    sent_msg = await message.reply_photo(
        photo=downloaded_path,
        caption="✅ Thumbnail saved successfully!"
    )

    if sent_msg.photo:
        file_id = sent_msg.photo.file_id
        await db.set_thumbnail(message.from_user.id, file_id)
    else:
        await message.reply("❌ Failed to get file_id from uploaded photo.")

# /delthumb command
#@app.on_message(filters.command("delthumb"))
@app.on_message(filters.command(["delthumb", f"delthumb@{BOT_USERNAME}"]))
async def delete_thumb_handler(client: Client, message: Message):   
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    await db.del_thumbnail(message.from_user.id)
    await message.reply("🗑️ Thumbnail deleted.")

# /getthumb command
#@app.on_message(filters.command("getthumb"))
@app.on_message(filters.command(["getthumb", f"getthumb@{BOT_USERNAME}"]))
async def get_thumb_handler(client: Client, message: Message):
    # SECURITY: authorize the sender's user id or the chat id (AUTH_USERS may list a group)
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    file_id = await db.get_thumbnail(message.from_user.id)
    if file_id:
        await message.reply_photo(photo=file_id, caption="🖼️ Tʜɪs ɪs ʏᴏᴜʀ sᴀᴠᴇᴅ ᴛʜᴜᴍʙɴᴀɪʟ•")
    else:
        await message.reply("⚠️ Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ sᴀᴠᴇᴅ ᴛʜᴜᴍʙɴᴀɪʟ.")

# /addthumb command
#@app.on_message(filters.command("addthumb") & filters.reply)
@app.on_message(filters.command(["addthumb", f"addthumb@{BOT_USERNAME}"]))
async def add_thumbnail(client: Client, message: Message):
    # SECURITY: restrict to admin users (mirrors /setthumb above) + guard anonymous senders
    if not is_authorised(message):
        return await message.reply_text(Localisation.NOT_AUTH)

    print("🔄 /addthumb command triggered")

    reply = message.reply_to_message
    user_id = message.from_user.id

    if not reply:
        print("⚠️ No reply detected.")
        return await message.reply("⚠️ Reply to a video or document.")

    media = reply.video or reply.document
    if not media:
        print("⚠️ Replied message is not a video or document.")
        return await message.reply("⚠️ Reply to a video or document.")

    print(f"👤 User ID: {user_id}")

    # Get the stored thumbnail file_id
    thumb_file_id = await db.get_thumbnail(user_id)
    if not thumb_file_id:
        print("❌ No thumbnail found in DB.")
        return await message.reply("⚠️ You haven’t set a thumbnail. Use /setthumb first.")

    print(f"📎 Thumbnail file_id found: {thumb_file_id}")

    try:
        print("📤 Forwarding video to LOG_CHANNEL to re-cache it...")
        forwarded = await client.send_video(
            chat_id=Config.LOG_CHANNEL,
            video=media.file_id,
            thumb=thumb_file_id,
            caption=reply.caption or "",
            supports_streaming=True
        )

        print(f"✅ Forwarded successfully. New file_id: {forwarded.video.file_id if forwarded.video else forwarded.document.file_id}")

        # Get the new file_id after thumbnail applied
        new_file_id = forwarded.video.file_id if forwarded.video else forwarded.document.file_id

        print("📤 Sending updated video back to user...")
        await message.reply_video(
            video=new_file_id,
            caption=reply.caption or "",
            supports_streaming=True
        )

        print("✅ Video with updated thumbnail sent.")

    except Exception as e:
        print(f"❌ Error during thumbnail update: {e}")
        await message.reply(f"❌ Failed to update thumbnail:\n`{e}`")
