# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME, app)
import os, pytz, random, string, asyncio, subprocess, sys, time
import string as sujoy
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, CallbackQuery
from bot.button_styles import InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from database import *
from bot.localisation import Localisation
from shortzy import Shortzy
from datetime import datetime, timedelta
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatAction, ChatMemberStatus, ChatType, ButtonStyle
from pyrogram.types import Message, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardMarkup, ChatMemberUpdated, ChatPermissions
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant, InviteHashEmpty, ChatAdminRequired, PeerIdInvalid, UserIsBlocked, InputUserDeactivated, UserNotParticipant

FSUB_LINK_EXPIRY = "120"
UPDATES_CHANNEL=Config.UPDATES_CHANNEL

# ✅ Set verified time
@app.on_message(filters.command(["set_vf_time", f"set_vf_time@{BOT_USERNAME}"]))
async def set_vf_time_cmd(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(
            Localisation.NOT_AUTH,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply_text(
            "<b>Usage:</b> /set_vf_time <seconds>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    verified_time = int(args[1])
    success = await db.set_verified_time(verified_time)

    if success:
        pretty_time = get_exp_time(verified_time)
        await message.reply_text(
            f"✅ Vᴇʀɪғɪᴇᴅ ᴛɪᴍᴇ ᴜᴘᴅᴀᴛᴇᴅ ᴛᴏ <b>{pretty_time}</b>.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    else:
        await message.reply_text(
            "❌ Fᴀɪʟᴇᴅ ᴛᴏ ᴜᴘᴅᴀᴛᴇ ᴠᴇʀɪғɪᴇᴅ ᴛɪᴍᴇ. Cʜᴇᴄᴋ ʟᴏɢs.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )


# ✅ Get verified time
@app.on_message(filters.command(["get_vf_time", f"get_vf_time@{BOT_USERNAME}"]))
async def get_vf_time_cmd(client: Client, message: Message):   
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(
            Localisation.NOT_AUTH,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    vf_time = await db.get_verified_time()

    if vf_time is None:
        await message.reply_text(
            "⚠️ Nᴏ ᴠᴇʀɪғɪᴇᴅ ᴛɪᴍᴇ ʜᴀs ʙᴇᴇɴ sᴇᴛ ʏᴇᴛ.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    else:
        pretty_time = get_exp_time(int(vf_time))
        await message.reply_text(
            f"⏳ Cᴜʀʀᴇɴᴛ ᴠᴇʀɪғɪᴇᴅ ᴛɪᴍᴇ: <b>{pretty_time}</b>.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )


# shortner commands
@app.on_message(filters.command(["shortner", f"shortner@{BOT_USERNAME}", "shortner1", f"shortner1@{BOT_USERNAME}", "shortner2", f"shortner2@{BOT_USERNAME}"]))
async def shortener_status(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    await message.reply_chat_action(ChatAction.TYPING)
    try:
        cmd = message.command[0].lower()
        show_all = cmd == "shortner" 

        # Default None
        shortener1_url = shortener1_api = tut_video1 = None
        shortener2_url = shortener2_api = tut_video2 = None

        if show_all:
            shortener1_url = await db.get_shortener_url1()
            shortener1_api = await db.get_shortener_api1()
            tut_video1 = await db.get_tut_video1()

            shortener2_url = await db.get_shortener_url2()
            shortener2_api = await db.get_shortener_api2()
            tut_video2 = await db.get_tut_video2()
        else:
            shortener_num = cmd[-1]
            if shortener_num == "1":
                shortener1_url = await db.get_shortener_url1()
                shortener1_api = await db.get_shortener_api1()
                tut_video1 = await db.get_tut_video1()
            elif shortener_num == "2":
                shortener2_url = await db.get_shortener_url2()
                shortener2_api = await db.get_shortener_api2()
                tut_video2 = await db.get_tut_video2()

        # Build response text
        response_text = "<b>🔗 ᴜʀʟ sʜᴏʀᴛᴇɴᴇʀ sᴇᴛᴛɪɴɢs</b>\n\n"

        if shortener1_url is not None:
            is_active1 = bool(shortener1_url and shortener1_api)
            status1 = "🟢" if is_active1 else "🔴"
            tutorial1 = f'<a href="{tut_video1}">ᴄʟɪᴄᴋ ʜᴇʀᴇ</a>' if tut_video1 else 'ɴᴏᴛ sᴇᴛ'
            response_text += (
                f"<b>📌 sʜᴏʀᴛᴇɴᴇʀ 1</b>\n"
                f"┣ <b>sᴛᴀᴛᴜs:</b> {status1}\n"
                f"┣ <b>ᴜʀʟ:</b> <code>{shortener1_url or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                f"┣ <b>ᴀᴘɪ:</b> <code>{shortener1_api or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                f"┗ <b>ᴛᴜᴛᴏʀɪᴀʟ:</b> {tutorial1}\n\n"
            )

        if shortener2_url is not None:
            is_active2 = bool(shortener2_url and shortener2_api)
            status2 = "🟢" if is_active2 else "🔴"
            tutorial2 = f'<a href="{tut_video2}">ᴄʟɪᴄᴋ ʜᴇʀᴇ</a>' if tut_video2 else 'ɴᴏᴛ sᴇᴛ'
            response_text += (
                f"<b>📌 sʜᴏʀᴛᴇɴᴇʀ 2</b>\n"
                f"┣ <b>sᴛᴀᴛᴜs:</b> {status2}\n"
                f"┣ <b>ᴜʀʟ:</b> <code>{shortener2_url or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                f"┣ <b>ᴀᴘɪ:</b> <code>{shortener2_api or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                f"┗ <b>ᴛᴜᴛᴏʀɪᴀʟ:</b> {tutorial2}\n\n"
            )

        # Buttons
        buttons = []
        if show_all:
            buttons.append([
                InlineKeyboardButton("📎 sʜᴏʀᴛᴇɴᴇʀ ①", callback_data="shortener_settings1"),
                InlineKeyboardButton("📎 sʜᴏʀᴛᴇɴᴇʀ ②", callback_data="shortener_settings2")
            ])
        else:
            shortener_num = cmd[-1]
            if shortener_num == "1":
                is_on = bool(shortener1_url and shortener1_api)
            else:
                is_on = bool(shortener2_url and shortener2_api)

            buttons.append([
                InlineKeyboardButton(
                    "ᴅɪsᴀʙʟᴇ" if is_on else "ᴇɴᴀʙʟᴇ",
                    callback_data=f"toggle_shortener_{shortener_num}",
                    style=ButtonStyle.DANGER if is_on else ButtonStyle.SUCCESS,
                )
            ])
            buttons.append([
                InlineKeyboardButton("⚙️ sᴇᴛᴛɪɴɢs", callback_data=f"set_shortener_{shortener_num}"),
                InlineKeyboardButton("📺 ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"set_tutorial_{shortener_num}")
            ])

        buttons.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")])

        await message.reply(
            text=response_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Error in shortener status: {e}")
        await message.reply_text("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ғᴇᴛᴄʜɪɴɢ sʜᴏʀᴛᴇɴᴇʀ sᴛᴀᴛᴜs")


def close_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])


# /set_shortner1 command
@app.on_message(filters.command(["shortlink1", f"shortlink1@{BOT_USERNAME}"]))
async def set_shortner1_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    if len(message.command) < 3:
        await message.reply(
            "⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ʙᴏᴛʜ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ ᴋᴇʏ:\n"
            "<code>/shortlink1 url api_key</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            "<code>/shortlink1 example.com 123456789</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    url = message.command[1]
    api_key = message.command[2]

    url_success = await db.set_shortener_url1(url)
    api_success = await db.set_shortener_api1(api_key)

    if url_success and api_success:
        # Generate a demo shortened link
        demo_url = "https://t.me/example"
        try:
            demo_short_link = await get_shortlink(api_key, url, demo_url)
            await message.reply(
                "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 1 ᴄᴏɴғɪɢᴜʀᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ᴜʀʟ:</b> <code>{url}</code>\n"
                f"<b>ᴀᴘɪ ᴋᴇʏ:</b> <code>{api_key}</code>\n\n"
                f"<b>ᴅᴇᴍᴏ sʜᴏʀᴛᴇɴᴇᴅ ʟɪɴᴋ:</b>\n"
                f"<code>{demo_short_link}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
        except Exception as e:
            await message.reply(
                "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 1 ᴄᴏɴғɪɢᴜʀᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ᴜʀʟ:</b> <code>{url}</code>\n"
                f"<b>ᴀᴘɪ ᴋᴇʏ:</b> <code>{api_key}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
    else:
        await message.reply(
            "❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ ᴄᴏɴғɪɢᴜʀᴇ sʜᴏʀᴛᴇɴᴇʀ 1</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ᴘʀᴏᴠɪᴅᴇᴅ ᴅᴇᴛᴀɪʟs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )

# /set_shortner2 command
@app.on_message(filters.command(["shortlink2", f"shortlink2@{BOT_USERNAME}"]))
async def set_shortner2_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    if len(message.command) < 3:
        await message.reply(
            "⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ʙᴏᴛʜ ᴜʀʟ ᴀɴᴅ ᴀᴘɪ ᴋᴇʏ:\n"
            "<code>/shortlink2 url api_key</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            "<code>/shortlink2 example.com 123456789</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    url = message.command[1]
    api_key = message.command[2]

    url_success = await db.set_shortener_url2(url)
    api_success = await db.set_shortener_api2(api_key)

    if url_success and api_success:
        # Generate a demo shortened link
        demo_url = "https://t.me/example"
        try:
            demo_short_link = await get_shortlink(api_key, url, demo_url)
            await message.reply(
                "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 2 ᴄᴏɴғɪɢᴜʀᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ᴜʀʟ:</b> <code>{url}</code>\n"
                f"<b>ᴀᴘɪ ᴋᴇʏ:</b> <code>{api_key}</code>\n\n"
                f"<b>ᴅᴇᴍᴏ sʜᴏʀᴛᴇɴᴇᴅ ʟɪɴᴋ:</b>\n"
                f"<code>{demo_short_link}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
        except Exception as e:
            await message.reply(
                "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 2 ᴄᴏɴғɪɢᴜʀᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ᴜʀʟ:</b> <code>{url}</code>\n"
                f"<b>ᴀᴘɪ ᴋᴇʏ:</b> <code>{api_key}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
    else:
        await message.reply(
            "❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ ᴄᴏɴғɪɢᴜʀᴇ sʜᴏʀᴛᴇɴᴇʀ 2</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ᴘʀᴏᴠɪᴅᴇᴅ ᴅᴇᴛᴀɪʟs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )

# /tutorial1 command
@app.on_message(filters.command(["tutorial1", f"tutorial1@{BOT_USERNAME}"]))
async def tutorial1_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    if len(message.command) < 2:
        await message.reply(
            "⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ:\n"
            "<code>/tutorial1 message_link</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            "<code>/tutorial1 https://t.me/How_to_Download_7x/26</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    video_url = message.command[1]
    
    # Validate Telegram message link format
    if not video_url.startswith("https://t.me/"):
        await message.reply(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ʟɪɴᴋ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ\n"
            "ғᴏʀᴍᴀᴛ: <code>https://t.me/username/message_id</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    try:
        # Extract channel username and message ID
        parts = video_url.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid link format")
            
        channel_username = parts[3]
        message_id = int(parts[4])
        
        try:
            await client.get_messages(channel_username, message_id)
        except Exception as e:
            await message.reply(
                "❌ <b>ɪɴᴠᴀʟɪᴅ ᴍᴇssᴀɢᴇ</b>\n\n"
                "ᴛʜᴇ ᴘʀᴏᴠɪᴅᴇᴅ ᴍᴇssᴀɢᴇ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ғᴏᴜɴᴅ.\n"
                "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
            return

        success = await db.set_tut_video1(video_url)

        if success:
            await message.reply(
                "✅ <b>ᴛᴜᴛᴏʀɪᴀʟ ᴠɪᴅᴇᴏ 1 sᴇᴛ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ʟɪɴᴋ:</b> <code>{video_url}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
        else:
            await message.reply(
                "❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ ᴠɪᴅᴇᴏ 1</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
    except Exception as e:
        await message.reply(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ\n"
            "ғᴏʀᴍᴀᴛ: <code>https://t.me/username/message_id</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )

# /tutorial2 command
@app.on_message(filters.command(["tutorial2", f"tutorial2@{BOT_USERNAME}"]))
async def tutorial2_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    if len(message.command) < 2:
        await message.reply(
            "⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ:\n"
            "<code>/tutorial2 message_link</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
            "<code>/tutorial2 https://t.me/How_to_Download_7x/26</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    video_url = message.command[1]
    
    # Validate Telegram message link format
    if not video_url.startswith("https://t.me/"):
        await message.reply(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ʟɪɴᴋ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ\n"
            "ғᴏʀᴍᴀᴛ: <code>https://t.me/username/message_id</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )
        return

    try:
        # Extract channel username and message ID
        parts = video_url.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid link format")
            
        channel_username = parts[3]
        message_id = int(parts[4])
        
        # Try to get the message to verify it exists
        try:
            await client.get_messages(channel_username, message_id)
        except Exception as e:
            await message.reply(
                "❌ <b>ɪɴᴠᴀʟɪᴅ ᴍᴇssᴀɢᴇ</b>\n\n"
                "ᴛʜᴇ ᴘʀᴏᴠɪᴅᴇᴅ ᴍᴇssᴀɢᴇ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ғᴏᴜɴᴅ.\n"
                "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
            return

        success = await db.set_tut_video2(video_url)

        if success:
            await message.reply(
                "✅ <b>ᴛᴜᴛᴏʀɪᴀʟ ᴠɪᴅᴇᴏ 2 sᴇᴛ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>ʟɪɴᴋ:</b> <code>{video_url}</code>",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
        else:
            await message.reply(
                "❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ ᴠɪᴅᴇᴏ 2</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴄʜᴇᴄᴋ ᴛʜᴇ ʟɪɴᴋ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
                reply_markup=close_btn(),
                disable_web_page_preview=True
            )
    except Exception as e:
        await message.reply(
            "❌ <b>ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ ғᴏʀᴍᴀᴛ</b>\n\n"
            "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇssᴀɢᴇ ʟɪɴᴋ\n"
            "ғᴏʀᴍᴀᴛ: <code>https://t.me/username/message_id</code>",
            reply_markup=close_btn(),
            disable_web_page_preview=True
        )


@app.on_message(filters.command(["fsub_mode", f"fsub_mode@{BOT_USERNAME}"]))
async def change_force_sub_mode(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    channels = await db.show_channels()

    if not channels:
        return await temp.edit("<b>❌ No force-sub channels found.</b>")

    buttons = []
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            mode = await db.get_channel_mode(ch_id)
            status = "🟢" if mode == "on" else "🔴"
            title = f"{status} {chat.title}"
            buttons.append([InlineKeyboardButton(title, callback_data=f"rfs_ch_{ch_id}")])
        except:
            buttons.append([InlineKeyboardButton(f"⚠️ {ch_id} (Unavailable)", callback_data=f"rfs_ch_{ch_id}")])

    buttons.append([InlineKeyboardButton("Close ✖️", callback_data="close")])

    await temp.edit(
        "<b>⚡ Select a channel to toggle Force-Sub Mode:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

#Request force sub mode commad,,,,,,


# This handler captures membership updates (like when a user leaves, banned)
@app.on_chat_member_updated()
async def handle_Chatmembers(client, chat_member_updated: ChatMemberUpdated):    
    chat_id = chat_member_updated.chat.id

    if await db.reqChannel_exist(chat_id):
        old_member = chat_member_updated.old_chat_member

        if not old_member:
            return

        if old_member.status == ChatMemberStatus.MEMBER:
            user_id = old_member.user.id

            if await db.req_user_exist(chat_id, user_id):
                await db.del_req_user(chat_id, user_id)


# This handler will capture any join request to the channel/group where the bot is an admin
@app.on_chat_join_request()
async def handle_join_request(client, chat_join_request):
    chat_id = chat_join_request.chat.id
    user_id = chat_join_request.from_user.id

    channel_exists = await db.reqChannel_exist(chat_id)
   
    if channel_exists:
        if not await db.req_user_exist(chat_id, user_id):
            await db.req_user(chat_id, user_id)
            

# Add channel
@app.on_message(filters.command(["addchnl", f"addchnl@{BOT_USERNAME}"]))
async def add_force_sub(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    args = message.text.split(maxsplit=1)

    if len(args) != 2:
        return await temp.edit(
            "<b>Usage:</b> <code>/addchnl -100XXXXXXXXXX</code>\n<b>Add only one chat at a time.</b>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]])
        )

    try:
        chat_id = int(args[1])
    except ValueError:
        return await temp.edit("<b>❌ Invalid Chat ID!</b>")

    all_chats = await db.show_channels()
    chat_ids_only = [cid if isinstance(cid, int) else cid[0] for cid in all_chats]
    if chat_id in chat_ids_only:
        return await temp.edit(f"<b>Already exists:</b> <code>{chat_id}</code>")

    try:
        chat = await client.get_chat(chat_id)

        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            return await temp.edit("<b>❌ Only channels or supergroups are allowed.</b>")

        member = await client.get_chat_member(chat.id, "me")
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await temp.edit("<b>❌ Bot must be admin in that chat.</b>")

        # Try to generate an invite link
        try:
            link = await client.export_chat_invite_link(chat.id)
        except Exception:
            # Fallback for username-based public chats
            link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id)[4:]}"

        await db.add_channel(chat_id)
        return await temp.edit(
            f"<b>✅ Chat added successfully!</b>\n\n"
            f"<b>Name:</b> <a href='{link}'>{chat.title}</a>\n"
            f"<b>ID:</b> <code>{chat_id}</code>",
            disable_web_page_preview=True
        )

    except Exception as e:
        return await temp.edit(
            f"<b>❌ Failed to add chat:</b>\n<code>{chat_id}</code>\n\n<i>{e}</i>"
        )


# Delete channel
@app.on_message(filters.command(["delchnl", f"delchnl@{BOT_USERNAME}"]))
async def del_force_sub(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)

    temp = await message.reply(
        "ᴡᴀɪᴛ ᴀ sᴇᴄ..",
        quote=True,
        parse_mode=ParseMode.MARKDOWN
    )
    args = message.text.split(maxsplit=1)
    all_channels = await db.show_channels()

    if len(args) != 2:
        return await temp.edit(
            "Usage:\n`/delchnl <channel_id | all>`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖ Close", callback_data="close")]]
            )
        )

    if args[1].lower() == "all":
        if not all_channels:
            return await temp.edit(
                "❌ No force-sub channels found.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✖ Close", callback_data="close")]]
                )
            )
        for ch_id in all_channels:
            await db.rem_channel(ch_id)
        return await temp.edit(
            "✅ All force-sub channels have been removed.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖ Close", callback_data="close")]]
            )
        )

    try:
        ch_id = int(args[1])
    except ValueError:
        return await temp.edit(
            "❌ Invalid Channel ID",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖ Close", callback_data="close")]]
            )
        )

    if ch_id in all_channels:
        await db.rem_channel(ch_id)
        return await temp.edit(
            f"✅ Channel removed: `{ch_id}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖ Close", callback_data="close")]]
            )
        )
    else:
        return await temp.edit(
            f"❌ Channel not found in force-sub list: `{ch_id}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖ Close", callback_data="close")]]
            )
        )


# View all channels
@app.on_message(filters.command(["listchnl", f"listchnl@{BOT_USERNAME}"]))
async def list_force_sub_channels(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text(Localisation.NOT_AUTH)
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>", quote=True)
    channels = await db.show_channels()

    if not channels:
        return await temp.edit("<b>❌ No force-sub channels found.</b>")

    result = "<b>⚡ Force-sub Channels:</b>\n\n"
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            link = chat.invite_link or await client.export_chat_invite_link(chat.id)
            result += f"<b>•</b> <a href='{link}'>{chat.title}</a> [<code>{ch_id}</code>]\n"
        except Exception:
            result += f"<b>•</b> <code>{ch_id}</code> — <i>Unavailable</i>\n"

    await temp.edit(result, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Close ✖️", callback_data="close")]]))



async def is_subscribed(client, user_id):
    channel_ids = await db.show_channels()

    if not channel_ids:
        return True

    #if user_id == OWNER_ID:
        #return True

    for cid in channel_ids:
        if not await is_sub(client, user_id, cid):
            # Retry once if join request might be processing
            mode = await db.get_channel_mode(cid)
            if mode == "on":
                await asyncio.sleep(2)
                if await is_sub(client, user_id, cid):
                    continue
            return False

    return True


async def is_sub(client, user_id, channel_id):
    try:
        member = await client.get_chat_member(channel_id, user_id)
        status = member.status
        return status in {
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        }

    except UserNotParticipant:
        mode = await db.get_channel_mode(channel_id)
        if mode == "on":
            exists = await db.req_user_exist(channel_id, user_id)
            return exists
        return False

    except Exception as e:
        print(f"[!] Error in is_sub(): {e}")
        return False


# Create a global dictionary to store chat data
chat_data_cache = {}

async def not_joined(client: Client, message: Message):
    temp = await message.reply("<b><i>Cʜᴇᴄᴋɪɴɢ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ...</i></b>")

    user_id = message.from_user.id
    buttons = []
    count = 0

    # Define Asia/Kolkata timezone
    kolkata_tz = pytz.timezone("Asia/Kolkata")

    try:
        all_channels = await db.show_channels()
        for total, chat_id in enumerate(all_channels, start=1):
            mode = await db.get_channel_mode(chat_id)
            await message.reply_chat_action(ChatAction.TYPING)

            if not await is_sub(client, user_id, chat_id):
                try:
                    # Cache chat info
                    if chat_id in chat_data_cache:
                        data = chat_data_cache[chat_id]
                    else:
                        data = await client.get_chat(chat_id)
                        chat_data_cache[chat_id] = data

                    name = data.title

                    # prepare expiry with Asia/Kolkata timezone
                    expire_date = None
                    expiry_seconds = None
                    if FSUB_LINK_EXPIRY:
                        try:
                            expiry_seconds = int(FSUB_LINK_EXPIRY)
                            if expiry_seconds >= 60:
                                expire_date = datetime.now(kolkata_tz) + timedelta(seconds=expiry_seconds)
                            elif expiry_seconds == 0:
                                expire_date = None
                            else:
                                print(f"FSUB_LINK_EXPIRY too small ({expiry_seconds}), ignoring expiry.")
                                expire_date = None
                        except Exception as ex:
                            print(f"Invalid FSUB_LINK_EXPIRY={FSUB_LINK_EXPIRY}: {ex}")
                            expire_date = None

                    # 🔎 debug print
                    print(f"[DEBUG] Chat={chat_id}, FSUB_LINK_EXPIRY={FSUB_LINK_EXPIRY}, "
                          f"expiry_seconds={expiry_seconds}, expire_date={expire_date}")

                    if mode == "on" and not data.username:
                        invite = await client.create_chat_invite_link(
                            chat_id=chat_id,
                            creates_join_request=True,
                            expire_date=expire_date
                        )
                        link = invite.invite_link
                    else:
                        if data.username:
                            invite = await client.create_chat_invite_link(
                                chat_id=chat_id,
                                expire_date=expire_date
                            )
                            link = invite.invite_link

                        else:
                            
                            link = f"https://t.me/{data.username}"

                    buttons.append([
                        InlineKeyboardButton(text=name, url=link, style=ButtonStyle.SUCCESS)
                    ])
                    count += 1
                    await temp.edit(f"<b>{'! ' * count}</b>")

                except Exception as e:
                    print(f"Error with chat {chat_id}: {e}")
                    return await temp.edit(
                        f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ @Prime_Sujoy</i></b>\n"
                        f"<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>"
                    )

        buttons.append([InlineKeyboardButton(" ᴄʜᴇᴄᴋ ᴀɢᴀɪɴ", callback_data=f"fsub_check_{user_id}")])

        # send the photo with caption
        sent = await message.reply_photo(
            photo=Localisation.FSUB_PIC,
            caption=Localisation.FSUB_TEXT.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        if sent:
            await temp.delete()

    except Exception as e:
        print(f"Final Error: {e}")
        await temp.edit(
            f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ @Prime_Sujoy</i></b>\n"
            f"<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>"
        )

##===================================================================================================================##

async def get_shortlink(api, base_url, long_url):
    """Use Shortzy to shorten a link."""
    shortzy = Shortzy(api_key=api, base_site=base_url)
    return await shortzy.convert(long_url)


async def shorten_url(url):
    """Shortens a given URL using available APIs, with retries."""

    # Fetch shortener details
    SHORT_URL_1 = await db.get_shortener_url1()
    SHORT_API_1 = await db.get_shortener_api1()
    TUTORIAL1 = await db.get_tut_video1()

    SHORT_URL_2 = await db.get_shortener_url2()
    SHORT_API_2 = await db.get_shortener_api2()
    TUTORIAL2 = await db.get_tut_video2()

    # Prepare available shorteners
    available_shorteners = []
    if SHORT_API_1 and SHORT_URL_1:
        available_shorteners.append((SHORT_API_1, SHORT_URL_1, TUTORIAL1))
    if SHORT_API_2 and SHORT_URL_2:
        available_shorteners.append((SHORT_API_2, SHORT_URL_2, TUTORIAL2))

    if not available_shorteners:
        return url, None 

    # Try 3 times with random selection
    for _ in range(3):
        short_api, short_base_url, tutorial = random.choice(available_shorteners)
        try:
            short_link = await get_shortlink(short_api, short_base_url, url)
            return short_link, tutorial
        except Exception as e:
            print(f"[shorten_url] Error: {e}")
            await asyncio.sleep(1)

    return url, None  # fallback if all fail


async def short_url(client, message):
    try:
        wait_message = await message.reply_text(
            "<b>⏳ Pʟᴇᴀsᴇ ᴡᴀɪᴛ...</b>", 
            quote=True
        )

        VERIFY_EXPIRE = await db.get_verified_time()

        bot_username = client.me.username if client.me else (await client.get_me()).username

        token = ''.join(random.choices(sujoy.ascii_letters + sujoy.digits, k=10))
        verify_link = f"https://t.me/{bot_username}?start=verify_{token}"

        # Save token in DB for this user
        await db.update_verify_status(
            message.from_user.id,
            is_verified=False,
            verify_token=token,
            verified_time=0  # not yet verified
        )

        # Get shortener link + tutorial
        short_link, tutorial_link = await shorten_url(verify_link)
        UPDATE_LINK = f"https://t.me/{UPDATES_CHANNEL}"

        # Build button layout
        buttons = [
            [
                InlineKeyboardButton("• ᴏᴘᴇɴ ʟɪɴᴋ", url=short_link),
                InlineKeyboardButton(
                    "ᴛᴜᴛᴏʀɪᴀʟ •", 
                    url=tutorial_link or "https://t.me/YourTutorialFallback"
                )
            ],
            [
                InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇs •", url=UPDATE_LINK)
            ]
        ]

        await message.reply_photo(
            photo=Localisation.FSUB_PIC,
            caption=(
                "𝗬𝗼𝘂𝗿 𝘁𝗼𝗸𝗲𝗻 𝗵𝗮𝘀 𝗲𝘅𝗽𝗶𝗿𝗲𝗱. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗿𝗲𝗳𝗿𝗲𝘀𝗵 𝘆𝗼𝘂𝗿 𝘁𝗼𝗸𝗲𝗻 𝘁𝗼 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗲..\n\n"
                f"<b>Tᴏᴋᴇɴ Tɪᴍᴇᴏᴜᴛ:</b> {get_exp_time(VERIFY_EXPIRE)}\n\n"
                "<b>ᴡʜᴀᴛ ɪs ᴛʜᴇ ᴛᴏᴋᴇɴ??</b>\n\n"
                f"ᴛʜɪs ɪs ᴀɴ ᴀᴅs ᴛᴏᴋᴇɴ. ᴘᴀssɪɴɢ ᴏɴᴇ ᴀᴅ ᴀʟʟᴏᴡs ʏᴏᴜ ᴛᴏ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ ғᴏʀ {get_exp_time(VERIFY_EXPIRE)}</b>"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        await wait_message.delete()

    except Exception as e:
        print(f"[short_url] Error: {e}")
 
##===================================================================================================================##


def get_exp_time(seconds: int) -> str:
    periods = [('ᴅᴀʏs', 86400), ('ʜᴏᴜʀs', 3600), ('ᴍɪɴs', 60), ('sᴇᴄs', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name} '
    return result.strip() if result else "0secs"
