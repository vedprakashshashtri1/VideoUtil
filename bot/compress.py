# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot import (
    APP_ID, API_HASH, AUTH_USERS, is_authorised, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, data1, data2, data3, data4, data5, data6, data7, app, crf, resolution, audio_b, preset, codec, name, size
)
from database import db
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
from bot.helper_funcs.utils import *
from bot.response import *
from bot.helper_funcs.display_progress import *
from bot.plugins.status_message_fn import (
    eval_message_f,
    exec_message_f,
    upload_log_file
)
from bot.commands import Command
from bot.localisation import Localisation
from bot.fsub import *
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.button_styles import InlineKeyboardButton
from pyrogram.enums import ParseMode
import asyncio, os, time, subprocess
from bot.premium import *


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

CURRENT_PROCESSES = {}
CHAT_FLOOD = {}



@app.on_message(filters.command(["compress", f"compress@{BOT_USERNAME}"]))
async def compress_handler(app: Client, message: Message):
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
            "<blockquote>Rᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴡɪᴛʜ /ᴄᴏᴍᴘʀᴇss ᴛᴏ sᴛᴀʀᴛ ᴄᴏᴍᴘʀᴇssɪɴɢ.</blockquote>"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("𝟭𝟰𝟰𝗽", callback_data=f"144p:{message.from_user.id}:{message.reply_to_message.id}"),
            InlineKeyboardButton("𝟮𝟰𝟬𝗽", callback_data=f"240p:{message.from_user.id}:{message.reply_to_message.id}")
        ],
        [
            InlineKeyboardButton("𝟯𝟲𝟬𝗽", callback_data=f"360p:{message.from_user.id}:{message.reply_to_message.id}"),
            InlineKeyboardButton("𝟰𝟴𝟬𝗽", callback_data=f"480p:{message.from_user.id}:{message.reply_to_message.id}")
        ],
        [
            InlineKeyboardButton("𝗔𝗹𝗹", callback_data=f"all:{message.from_user.id}:{message.reply_to_message.id}")
        ],
        [
            InlineKeyboardButton("𝟳𝟮𝟬𝗽", callback_data=f"720p:{message.from_user.id}:{message.reply_to_message.id}"),
            InlineKeyboardButton("𝟭𝟬𝟴𝟬𝗽", callback_data=f"1080p:{message.from_user.id}:{message.reply_to_message.id}")
        ],
        [
            InlineKeyboardButton("𝟮𝟭𝟲𝟬𝗽", callback_data=f"2160p:{message.from_user.id}:{message.reply_to_message.id}"),
            InlineKeyboardButton("❌", callback_data="close")
        ]
    ])

    sent_btn = await message.reply_to_message.reply_text(
        "<b>Cʜᴏᴏsᴇ ᴀ ʀᴇsᴏʟᴜᴛɪᴏɴ ᴛᴏ ᴄᴏᴍᴘʀᴇss:</b>",
        reply_markup=keyboard
    )
    if sent_btn and message.from_user and message.reply_to_message:
        register_pending_button(sent_btn.chat.id, sent_btn.id, message.from_user.id, message.reply_to_message.id)


@app.on_message(filters.command(["all", f"all@{BOT_USERNAME}"]))
async def chum_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task4)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task4(reply_to_message, user_id)



@app.on_message(filters.command(["144p", f"144p@{BOT_USERNAME}"]))
async def chu_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task5)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task5(reply_to_message, user_id)


@app.on_message(filters.command(["240p", f"240p@{BOT_USERNAME}"]))
async def gan_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task6)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task6(reply_to_message, user_id)


@app.on_message(filters.command(["360p", f"360p@{BOT_USERNAME}"]))
async def ran_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task7)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task7(reply_to_message, user_id)


@app.on_message(filters.command(["480p", f"480p@{BOT_USERNAME}"]))
async def lowda_direct(app, message):
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
       
    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task(reply_to_message, user_id)
  

@app.on_message(filters.command(["720p", f"720p@{BOT_USERNAME}"]))
async def chut_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task1)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task1(reply_to_message, user_id)


@app.on_message(filters.command(["1080p", f"1080p@{BOT_USERNAME}"]))
async def gand_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task2)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task2(reply_to_message, user_id)


@app.on_message(filters.command(["2160p", "4k", f"4k@{BOT_USERNAME}", f"2160p@{BOT_USERNAME}"]))
async def rand_direct(app, message):
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

    reply_to_message = message.reply_to_message
    if not reply_to_message:
        return await message.reply("Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ ᴛᴏ ᴇɴᴄᴏᴅᴇ.")

    user_id = message.from_user.id

    query = await message.reply_text(
        "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
        quote=True
    )

    # Queue via task manager (register+dedupe+status inside add_task3)
    await asyncio.sleep(0.5)
    try:
        await query.delete()
    except Exception:
        pass
    await add_task3(reply_to_message, user_id)

       
