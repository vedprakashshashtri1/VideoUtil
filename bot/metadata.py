# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from database import *
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from bot.button_styles import InlineKeyboardButton
from functools import wraps
from bot.config import Config
from bot.helper_funcs.utils import *
from bot import app, AUTH_USERS, is_authorised
from bot.localisation import Localisation


BOT_USERNAME=Config.BOT_USERNAME
UPDATES_CHANNEL=Config.UPDATES_CHANNEL


def admin_only(func):
    # SECURITY: every /setmeta command was unauthenticated and crashed on anonymous senders
    @wraps(func)
    async def wrapper(client, message):
        if not is_authorised(message):
            return await message.reply_text(Localisation.NOT_AUTH)
        return await func(client, message)
    return wrapper


@app.on_message(filters.command(["metadata", f"metadata@{BOT_USERNAME}"]))
@admin_only
async def metadata(client, message):
    user_id = message.from_user.id

    # Ensure metadata doc exists
    existing = await db.metadata.find_one({"_id": user_id})
    if not existing:
        defaults = {
            "_id": user_id,
            "metadata": "Off",
            "title": "Nexon Bots [t.me/NexonBots]",
            "author": "[Nexon Bots]",
            "artist": "[Nexon Bots]",
            "audio": "[Nexon Bots]",
            "subtitle": "[Nexon Bots]",
            "video": "[Nexon Bots]",
            "encoded_by": "Nexon Bots [Sujoy]",
            "custom_tag": "[Nexon Bots]",
            "commentz": "[Nexon Bots]"
        }
        await db.metadata.insert_one(defaults)
        existing = defaults

    # Fetch data directly from document (1 query instead of 11 sequential queries)
    current = existing.get("metadata", "Off")
    title = existing.get("title")
    author = existing.get("author")
    artist = existing.get("artist")
    video = existing.get("video")
    audio = existing.get("audio")
    subtitle = existing.get("subtitle")
    encoded_by = existing.get("encoded_by")
    custom_tag = existing.get("custom_tag")
    commentz = existing.get("commentz")

    # Spoiler formatting
    text = f"""
**㊋ Yᴏᴜʀ Mᴇᴛᴀᴅᴀᴛᴀ ɪꜱ ᴄᴜʀʀᴇɴᴛʟʏ:** `{current}`

**◈ Tɪᴛʟᴇ ▹** ||{title or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Aᴜᴛʜᴏʀ ▹** ||{author or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Aʀᴛɪꜱᴛ ▹** ||{artist or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Aᴜᴅɪᴏ ▹** ||{audio or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Sᴜʙᴛɪᴛʟᴇ ▹** ||{subtitle or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Vɪᴅᴇᴏ ▹** ||{video or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Eɴᴄᴏᴅᴇᴅ Bʏ ▹** ||{encoded_by or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Cᴜsᴛᴏᴍ Tᴀɢ ▹** ||{custom_tag or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
**◈ Cᴏᴍᴍᴇɴᴛ ▹** ||{commentz or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}||
"""

    keyboard = build_metadata_keyboard(current, user_id)

    await message.reply_text(
        text=text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_message(filters.command(["settitle", f"settitle@{BOT_USERNAME}"]))
@admin_only
async def title(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /settitle Encoded By {UPDATES_CHANNEL}**")
    title = message.text.split(" ", 1)[1]
    await db.set_title(message.from_user.id, title=title)
    await message.reply_text("**✅ Tɪᴛʟᴇ Sᴀᴠᴇᴅ**")


@app.on_message(filters.command(["setauthor", f"setauthor@{BOT_USERNAME}"]))
@admin_only
async def author(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Aᴜᴛʜᴏʀ\n\nExᴀᴍᴩʟᴇ:- /setauthor {UPDATES_CHANNEL}**")
    author = message.text.split(" ", 1)[1]
    await db.set_author(message.from_user.id, author=author)
    await message.reply_text("**✅ Aᴜᴛʜᴏʀ Sᴀᴠᴇᴅ**")


@app.on_message(filters.command(["setartist", f"setartist@{BOT_USERNAME}"]))
@admin_only
async def artist(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Aʀᴛɪꜱᴛ\n\nExᴀᴍᴩʟᴇ:- /setartist {UPDATES_CHANNEL}**")
    artist = message.text.split(" ", 1)[1]
    await db.set_artist(message.from_user.id, artist=artist)
    await message.reply_text("**✅ Aʀᴛɪꜱᴛ Sᴀᴠᴇᴅ**")


@app.on_message(filters.command(["setaudio", f"setaudio@{BOT_USERNAME}"]))
@admin_only
async def audio(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Aᴜᴅɪᴏ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setaudio {UPDATES_CHANNEL}**")
    audio = message.text.split(" ", 1)[1]
    await db.set_audio(message.from_user.id, audio=audio)
    await message.reply_text("**✅ Aᴜᴅɪᴏ Sᴀᴠᴇᴅ**")

@app.on_message(filters.command(["setsubtitle", f"setsubtitle@{BOT_USERNAME}"]))
@admin_only
async def subtitle(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Sᴜʙᴛɪᴛʟᴇ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setsubtitle {UPDATES_CHANNEL}**")
    subtitle = message.text.split(" ", 1)[1]
    await db.set_subtitle(message.from_user.id, subtitle=subtitle)
    await message.reply_text("**✅ Sᴜʙᴛɪᴛʟᴇ Sᴀᴠᴇᴅ**")

@app.on_message(filters.command(["setvideo", f"setvideo@{BOT_USERNAME}"]))
@admin_only
async def video(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Vɪᴅᴇᴏ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setvideo Encoded by {UPDATES_CHANNEL}**")
    video = message.text.split(" ", 1)[1]
    await db.set_video(message.from_user.id, video=video)
    await message.reply_text("**✅ Vɪᴅᴇᴏ Sᴀᴠᴇᴅ**")


@app.on_message(filters.command(["setencoded_by", f"setencoded_by@{BOT_USERNAME}"]))
@admin_only
async def encoded_by(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Eɴᴄᴏᴅᴇᴅ Bʏ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setencoded_by {UPDATES_CHANNEL}**")
    encoded_by = message.text.split(" ", 1)[1]
    await db.set_encoded_by(message.from_user.id, encoded_by=encoded_by)
    await message.reply_text("**✅ Eɴᴄᴏᴅᴇᴅ Bʏ Sᴀᴠᴇᴅ**")
    

@app.on_message(filters.command(["setcustom_tag", f"setcustom_tag@{BOT_USERNAME}"]))
@admin_only
async def custom_tag(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Cᴜsᴛᴏᴍ Tᴀɢ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setcustom_tag {UPDATES_CHANNEL}**")
    custom_tag = message.text.split(" ", 1)[1]
    await db.set_custom_tag(message.from_user.id, custom_tag=custom_tag)
    await message.reply_text("**✅ Eɴᴄᴏᴅᴇᴅ Bʏ Sᴀᴠᴇᴅ**")

@app.on_message(filters.command(["setcomment", f"setcomment@{BOT_USERNAME}"]))
@admin_only
async def set_comment(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ Tʜᴇ Cᴏᴍᴍᴇɴᴛ Tɪᴛʟᴇ\n\nExᴀᴍᴩʟᴇ:- /setcomment {UPDATES_CHANNEL}**")
    commentz = message.text.split(" ", 1)[1]
    await db.set_commentz(message.from_user.id, commentz=commentz)
    await message.reply_text("**✅ Cᴏᴍᴍᴇɴᴛ Sᴀᴠᴇᴅ**")

@app.on_message(filters.command(["setallmeta", f"setallmeta@{BOT_USERNAME}"]))
@admin_only
async def set_all_metadata(client, message):
    if len(message.command) == 1:
        return await message.reply_text(
            f"**Gɪᴠᴇ ᴛʜᴇ ᴍᴇᴛᴀᴅᴀᴛᴀ ᴛᴇxᴛ\n\nExᴀᴍᴩʟᴇ:- /setallmeta {UPDATES_CHANNEL}**")
    
    metadata_text = message.text.split(" ", 1)[1]
    user_id = message.from_user.id
    
    try:
        # Set all metadata fields to the same value
        await db.set_title(user_id, metadata_text)
        await db.set_author(user_id, metadata_text)
        await db.set_artist(user_id, metadata_text)
        await db.set_audio(user_id, metadata_text)
        await db.set_subtitle(user_id, metadata_text)
        await db.set_video(user_id, metadata_text)
        await db.set_encoded_by(user_id, metadata_text)
        
        await message.reply_text("**✅ Aʟʟ ᴍᴇᴛᴀᴅᴀᴛᴀ ғɪᴇʟᴅs ʜᴀᴠᴇ ʙᴇᴇɴ ᴜᴘᴅᴀᴛᴇᴅ**")
    except Exception as e:
        await message.reply_text(f"**❌ Eʀʀᴏʀ ᴜᴘᴅᴀᴛɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ: {str(e)}**")
