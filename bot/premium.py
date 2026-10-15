# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import motor, asyncio
import motor.motor_asyncio
import time, logging
import pymongo, os
import logging
from bot.config import Config
from datetime import datetime, timedelta
from bot import (
    APP_ID, API_HASH, AUTH_USERS, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, app)
from database import db
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, Message
from bot.button_styles import InlineKeyboardButton
from pytz import timezone


DB_URI=Config.DB_URL
DB_NAME=Config.DB_NAME

# Reuse the central Motor database from database.py to prevent connection pool duplication
collection = getattr(db, "database", None)["premium-users"] if getattr(db, "database", None) is not None else motor.motor_asyncio.AsyncIOMotorClient(DB_URI)[DB_NAME]['premium-users']


async def expired_user_cleaner():
    while True:
        try:
            await remove_expired_users()
        except Exception as e:
            print(f"[Expired User Cleaner] Error: {e}")
        await asyncio.sleep(600)  # Check every 10 minutes, avoiding MongoDB request flooding  


# Check if the user is a premium user
async def is_premium_user(user_id):
    """Return True if the user is active premium, False if not"""
    user = await collection.find_one({"user_id": user_id})
    if not user:
        return False

    ist = timezone("Asia/Kolkata")
    # SECURITY: a corrupt or partial timestamp must not crash every premium check
    try:
        expiration_time = datetime.fromisoformat(user["expiration_timestamp"])
    except (KeyError, TypeError, ValueError):
        print(f"[Premium] Unreadable expiration for user {user_id}: {user.get('expiration_timestamp')!r}")
        return False

    # SECURITY: naive timestamps have no offset - assume they are already IST
    if expiration_time.tzinfo is None:
        expiration_time = expiration_time.replace(tzinfo=ist)

    if datetime.now(ist) > expiration_time.astimezone(ist):
        # User expired, remove from DB
        await collection.delete_one({"user_id": user_id})
        return False

    return True


# Remove premium user
async def remove_premium(user_id):
    await collection.delete_one({"user_id": user_id}) 

# Remove expired users
async def remove_expired_users():
    # SECURITY: Mongo compares these ISO strings lexicographically. datetime.now() is
    # naive (host-local, no offset) while stored values carry a +05:30 offset, so the
    # two are not on the same scale - on a host clock ahead of IST this deletes users
    # whose premium is still active. Compare in Python instead, with aware datetimes.
    ist = timezone("Asia/Kolkata")
    now = datetime.now(ist)

    expired_ids = []
    async for user in collection.find({}, {"user_id": 1, "expiration_timestamp": 1}):
        try:
            expires = datetime.fromisoformat(user["expiration_timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=ist)
        if expires.astimezone(ist) <= now:
            expired_ids.append(user["user_id"])

    for uid in expired_ids:
        await collection.delete_one({"user_id": uid})


# List active premium users
async def list_premium_users():
    # Define IST timezone
    ist = timezone("Asia/Kolkata")
    premium_users = collection.find({})
    premium_user_list = []

    async for user in premium_users:
        user_id = user["user_id"]
        # SECURITY: one unreadable row must not break the whole listing
        try:
            expiration_time = datetime.fromisoformat(user["expiration_timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if expiration_time.tzinfo is None:
            expiration_time = expiration_time.replace(tzinfo=ist)
        expiration_time = expiration_time.astimezone(ist)
        remaining_time = expiration_time - datetime.now(ist)

        if remaining_time.total_seconds() > 0: 
            days, hours, minutes, seconds = (
                remaining_time.days,
                remaining_time.seconds // 3600,
                (remaining_time.seconds // 60) % 60,
                remaining_time.seconds % 60,
            )

            expiry_info = f"{days}d {hours}h {minutes}m {seconds}s left"
            formatted_expiry_time = expiration_time.strftime('%Y-%m-%d %H:%M:%S %p IST')

            premium_user_list.append(f"UserID: {user_id} - Expiry: {expiry_info} (Expires at {formatted_expiry_time})")

    return premium_user_list



# Add premium user
async def add_premium(user_id, time_value, time_unit):
    ist = timezone("Asia/Kolkata")

    # SECURITY: reject non-positive durations instead of silently granting a
    # zero-length or already-expired plan
    if not isinstance(time_value, int) or time_value <= 0:
        raise ValueError("time_value must be a positive integer")

    if time_unit == 'm':
        delta = timedelta(minutes=time_value)
    elif time_unit == 'd':
        delta = timedelta(days=time_value)
    else:
        raise ValueError("Invalid time unit. Use 'm' for minutes or 'd' for days.")

    now = datetime.now(ist)

    # SECURITY: an already-active plan is EXTENDED from its current expiry, not
    # truncated back to now+delta (the old $set threw the remaining time away)
    existing = await collection.find_one({"user_id": user_id})
    start = now
    if existing:
        try:
            base = datetime.fromisoformat(existing["expiration_timestamp"])
        except (KeyError, TypeError, ValueError):
            base = None
        if base is not None:
            if base.tzinfo is None:
                base = base.replace(tzinfo=ist)
            base = base.astimezone(ist)
            if base > now:
                start = base

    expiration_time = start + delta

    # Prepare premium data
    premium_data = {
        "user_id": user_id,
        "expiration_timestamp": expiration_time.isoformat(),  # Store in ISO format
    }

    await collection.update_one(
        {"user_id": user_id},
        {"$set": premium_data},
        upsert=True
    )  

    formatted_expiration_time = expiration_time.strftime('%Y-%m-%d %H:%M:%S %p IST')

    print(f"User {user_id} premium access expires on {formatted_expiration_time}")

    return formatted_expiration_time

# Check if a user has an active premium plan
async def check_user_plan(user_id):
    user = await collection.find_one({"user_id": user_id})  
    if user:
        # SECURITY: same defensive parse as is_premium_user - one bad row must not 500
        try:
            expiration_time = datetime.fromisoformat(user["expiration_timestamp"])
        except (KeyError, TypeError, ValueError):
            return "⚠️ Yᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ʀᴇᴄᴏʀᴅ ɪs ɪɴᴠᴀʟɪᴅ. Cᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ."
        ist = timezone("Asia/Kolkata")
        if expiration_time.tzinfo is None:
            expiration_time = expiration_time.replace(tzinfo=ist)
        expiration_time = expiration_time.astimezone(ist)
        remaining_time = expiration_time - datetime.now(ist)
        
        if remaining_time.total_seconds() > 0:  # If the user is still active
            # Format the remaining time
            days, hours, minutes, seconds = (
                remaining_time.days,
                remaining_time.seconds // 3600,
                (remaining_time.seconds // 60) % 60,
                remaining_time.seconds % 60,
            )
            validity_info = f"𝗬𝗼𝘂𝗿 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻 𝗶𝘀 𝗮𝗰𝘁𝗶𝘃𝗲. {days}d {hours}h {minutes}m {seconds}s left."
            return validity_info
        else:
            return "Yᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ ʜᴀs ᴇxᴘɪʀᴇᴅ."
    else:
        return "Yᴏᴜ ᴅᴏ ɴᴏᴛ ʜᴀᴠᴇ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ."


# Command to add premium user
@app.on_message(filters.command(["addpaid", f"addpaid@{BOT_USERNAME}"]))
async def add_premium_user_command(client, msg):
    if not msg.from_user or msg.from_user.id not in AUTH_USERS:
        return await msg.reply_text(
            "<blockquote><b>Admin Only</b> 💀</blockquote>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    if len(msg.command) != 4:
        await msg.reply_text(
            "Usage: /addpaid (user_id) (time_value)  (m/d)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
        return

    try:
        user_id = int(msg.command[1])
        time_value = int(msg.command[2])
        time_unit = msg.command[3].lower()  # 'm' or 'd'

        expiration_time = await add_premium(user_id, time_value, time_unit)

        await msg.reply_text(
            f"𝐔𝐬𝐞𝐫 {user_id} ᴀᴅᴅᴇᴅ ᴀs ᴀ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀ ғᴏʀ {time_value} {time_unit}.\n"
            f"Exᴘɪʀᴀᴛɪᴏɴ Tɪᴍᴇ: {expiration_time}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

        await client.send_message(
            chat_id=user_id,
            text=(
                f"🎉 Cᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴs! Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴜᴘɢʀᴀᴅᴇᴅ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ғᴏʀ {time_value} {time_unit}.\n\n"
                f"Exᴘɪʀᴀᴛɪᴏɴ Tɪᴍᴇ: {expiration_time}"
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    except ValueError:
        await msg.reply_text(
            "Invalid input. Please check the user_id, time_value, and time_unit.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    except Exception as e:
        await msg.reply_text(
            f"An error occurred: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )


# Command to remove premium user
@app.on_message(filters.command(["rempaid", f"rempaid@{BOT_USERNAME}"]))
async def pre_remove_user(client, msg):
    if not msg.from_user or msg.from_user.id not in AUTH_USERS:
        return await msg.reply_text(
            "<blockquote><b>Admin Only</b> 💀</blockquote>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    if len(msg.command) != 2:
        await msg.reply_text(
            "useage: /rempaid user_id",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
        return
    try:
        user_id = int(msg.command[1])
        await remove_premium(user_id)
        await msg.reply_text(
            f"User {user_id} has been removed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    except ValueError:
        await msg.reply_text(
            "user_id must be an integer or not available in database.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )


# Command to list active premium users
@app.on_message(filters.command(["listpaid", f"listpaid@{BOT_USERNAME}"]))
async def list_premium_users_command(client, message):
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        return await message.reply_text(
            "<blockquote><b>Admin Only</b> 💀</blockquote>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

    ist = timezone("Asia/Kolkata")
    premium_users_cursor = collection.find({})
    premium_user_list = ['𝙰𝚌𝚝𝚒𝚟𝚎 𝙿𝚛𝚎𝚖𝚒𝚞𝚖 𝚄𝚜𝚎𝚛𝚜 𝚒𝚗 𝚍𝚊𝚝𝚊𝚋𝚊𝚜𝚎👇:']
    current_time = datetime.now(ist)

    total_active_users = 0 

    async for user in premium_users_cursor:
        user_id = user["user_id"]
        expiration_timestamp = user["expiration_timestamp"]

        try:
            expiration_time = datetime.fromisoformat(expiration_timestamp).astimezone(ist)
            remaining_time = expiration_time - current_time

            if remaining_time.total_seconds() <= 0:
                await collection.delete_one({"user_id": user_id})
                continue  

            total_active_users += 1  # Count this user as active

            user_info = await client.get_users(user_id)
            username = user_info.username if user_info.username else "No Username"
            first_name = user_info.first_name

            days, hours, minutes, seconds = (
                remaining_time.days,
                remaining_time.seconds // 3600,
                (remaining_time.seconds // 60) % 60,
                remaining_time.seconds % 60,
            )
            expiry_info = f"{days}d {hours}h {minutes}m {seconds}s left"

            premium_user_list.append(
                f"𝐔𝐬𝐞𝐫𝐈𝐃: <code>{user_id}</code>\n"
                f"Usᴇʀ: @{username}\n"
                f"Nᴀᴍᴇ: <code>{first_name}</code>\n"
                f"Exᴘɪʀʏ: {expiry_info}"
            )
        except Exception as e:
            premium_user_list.append(
                f"UserID: <code>{user_id}</code>\n"
                f"Error: Unable to fetch user details ({str(e)})"
            )

    # Insert total users line after the first line
    premium_user_list.insert(1, f"𝖳𝗈𝗍𝖺𝗅 𝖠𝖼𝗍𝗂𝗏𝖾 𝖴𝗌𝖾𝗋𝗌: {total_active_users}\n")

    if total_active_users == 0:  
        await message.reply_text(
            "𝐈 𝐟𝐨𝐮𝐧𝐝 𝟎 𝐚𝐜𝐭𝐢𝐯𝐞 𝐩𝐫𝐞𝐦ɪᴜᴍ 𝐮𝐬𝐞𝐫𝐬 𝐢𝐧 𝐦𝐲 𝐃𝐁",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )
    else:
        await message.reply_text(
            "\n\n".join(premium_user_list),
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
        )

# Command to check user's plan
@app.on_message(filters.command(["myplan", f"myplan@{BOT_USERNAME}"]))
async def check_plan(client, message):
    # SECURITY: from_user is None for anonymous/group senders
    if not message.from_user:
        return await message.reply("⚠️ Tʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ʙᴇ ᴜsᴇᴅ ᴏɴʟʏ ɪɴ ᴘʀɪᴠᴀᴛᴇ.")
    user_id = message.from_user.id  
    status_message = await check_user_plan(user_id)
    await message.reply(
        status_message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]])
    )
