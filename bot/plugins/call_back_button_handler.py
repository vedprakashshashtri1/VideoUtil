# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
from bot.helper_funcs.utils import *
from bot.plugins.incoming_message_fn import *
from pyrogram import Client, filters #InputFile
from pyrogram.types import Message, InlineKeyboardMarkup, CallbackQuery
from bot.button_styles import InlineKeyboardButton
from pyrogram.errors import FloodWait
from pyrogram.enums import ParseMode, ButtonStyle
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from mimetypes import guess_type
from bot.config import Config
from bot.fsub import *
from bot.audio import *
from PIL import Image
import aiofiles
import mimetypes

from bot import (
    APP_ID, API_HASH, AUTH_USERS, DOWNLOAD_LOCATION, LOGGER,
    TG_BOT_TOKEN, BOT_USERNAME, SESSION_NAME,
    data, data1, data2, data3, data4, data5, data6, data7, app, crf, resolution, audio_b, preset, codec, name, size
)
from bot.localisation import Localisation
from pyrogram.types import CallbackQuery
from database import *
import datetime
import logging
import os, signal
import json
import shutil
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)


# -------------------------------


@app.on_callback_query()
async def button(bot, update: CallbackQuery):
    cb_data = update.data
    user_id = update.from_user.id

    # Only explicitly configured bot admins can operate privileged callbacks.
    is_admin = user_id in AUTH_USERS

    # Single-dispatcher rule: wzgram starves later bare @app.on_callback_query
    # handlers, so vss*/vst* callbacks are delegated here (with ack+logging).
    if cb_data.startswith("vss"):
        from bot.screenshot import handle_ss_callback
        return await handle_ss_callback(bot, update, user_id, is_admin)
    # Status buttons own vst* callbacks (bot/status_commands.py).
    if cb_data.startswith("vst"):
        from bot.status_commands import handle_status_callback
        return await handle_status_callback(bot, update, user_id)

    # CLOSE button
    if cb_data == "close":
        try:
            await update.message.delete()
            await update.answer("❌ Closed", show_alert=False)
        except Exception as e:
            LOGGER.error(f"Error deleting message: {e}")
            try:
                await update.answer("❌ Closed", show_alert=False)
            except Exception:
                pass
        return

    elif cb_data == "about":
        await update.answer()
        await update.message.edit_text(
            text=Localisation.ABS_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("ʜᴏᴍᴇ", callback_data="start"),
                    InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close")
                ]
            ])
        )

    elif cb_data == "start":
        await update.answer()
        await update.message.edit_text(
            text=Localisation.START_TEXT.format(
                first=update.from_user.first_name,
                last=update.from_user.last_name,
                username=None if not update.from_user.username else '@' + update.from_user.username,
                mention=update.from_user.mention,
                id=update.from_user.id
            ),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("ʜᴇʟᴘ", callback_data="help"),
                    InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data="about")
                ]
            ])
        )

    elif cb_data == "help":
        await update.answer()
        await update.message.edit_text(
            text=Localisation.HLP_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("ʜᴏᴍᴇ", callback_data="start"),
                    InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="close")
                ]
            ])
        )

    # CROP button
    elif cb_data.startswith("crop:"):
        try:
            _, ratio, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Crop task added!", show_alert=False)

        # Delete button message
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original video
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found.")

        # Add crop task
        media = reply_msg.video or reply_msg.document
        file_uid = getattr(media, "file_unique_id", "") or str(reply_msg.id)
        title = (getattr(media, "file_name", None) or "video").strip() or "video"
        from bot.task_manager import task_manager, build_dedupe_key
        from bot.group_status import announce_task

        task_id, err = await task_manager.register(
            int(auth_owner_id), reply_msg.chat.id, "crop", title,
            build_dedupe_key(int(auth_owner_id), file_uid, "crop", ratio),
            link=getattr(reply_msg, "link", "") or "",
        )
        if not task_id:
            return await update.message.reply_text(err)

        await announce_task(reply_msg)

        if not any(item[0].id == reply_msg.id for item in crop):
            crop.append((reply_msg, int(auth_owner_id), ratio, task_id))
            if len(crop) == 1:
                item = crop[0]
                await add_crops(item[0], item[1], item[2], item[3])
  
    elif cb_data.startswith("all"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task4)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task4(reply_msg, int(auth_owner_id))  


    elif cb_data.startswith("144p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task5)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task5(reply_msg, int(auth_owner_id))  


    elif cb_data.startswith("240p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task6)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task6(reply_msg, int(auth_owner_id)) 


    elif cb_data.startswith("360p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task7)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task7(reply_msg, int(auth_owner_id)) 

    # 480p or other resolution-based button
    elif cb_data.startswith("480p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task(reply_msg, int(auth_owner_id)) 


    elif cb_data.startswith("720p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task1)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task1(reply_msg, int(auth_owner_id))  


    elif cb_data.startswith("1080p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task2)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task2(reply_msg, int(auth_owner_id)) 


    elif cb_data.startswith("2160p"):
        try:
            resolution, owner_id, original_msg_id = cb_data.split(":")
        except ValueError:
            return await update.answer("❌ Invalid button format.", show_alert=True)

        btn_info = get_pending_button(update.message.chat.id, update.message.id)
        if btn_info:
            auth_owner_id = str(btn_info["owner"])
            auth_src_id = str(btn_info["src"])
        else:
            auth_owner_id = owner_id
            auth_src_id = original_msg_id

        if str(user_id) != auth_owner_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        await update.answer("✅ Compression task added!", show_alert=False)

        # Delete the message with the buttons
        try:
            await update.message.delete()
        except Exception as e:
            LOGGER.warning(f"Couldn't delete button message: {e}")

        # Fetch the original file message
        try:
            reply_msg = await bot.get_messages(update.message.chat.id, int(auth_src_id))
        except Exception as e:
            LOGGER.error(f"Failed to fetch original message: {e}")
            return await update.message.reply_text("⚠️ Original file not found. Please press button under correct message.")

        # Confirm queue
        query = await update.message.reply_text(
            "<blockquote>ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ...\nᴘʟᴇᴀsᴇ ʙᴇ ᴘᴀᴛɪᴇɴᴛ ʏᴏᴜʀ ᴇɴᴄᴏᴅɪɴɢ ᴡɪʟʟ sᴛᴀʀᴛ sᴏᴏɴ</blockquote>",
            reply_to_message_id=reply_msg.id
        )

        # Queue via task manager (register+dedupe+status inside add_task3)
        await asyncio.sleep(0.5)
        try:
            await query.delete()
        except Exception:
            pass
        await add_task3(reply_msg, int(auth_owner_id)) 

    elif cb_data.startswith("setmedia_"):
        try:
        # Extract media_type and allowed_user_id
            data_parts = cb_data.split(":")
            media_type = data_parts[0].split("_", 1)[1].lower()
            allowed_user_id = int(data_parts[1])
        except Exception:
            return await update.answer("❌ Invalid callback format.", show_alert=True)

        if user_id != allowed_user_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        #print(f"🔄 Setting media preference for user {user_id} to {media_type}")
        await db.set_media_preference(user_id, media_type)
        keyboard = build_media_keyboard(media_type, user_id)

        try:
            await update.answer(f"✅ Media type set to {media_type.upper()}", show_alert=False)
            await update.message.edit_text(
                f"**Mᴇᴅɪᴀ ᴘʀᴇғᴇʀᴇɴᴄᴇ ᴜᴘᴅᴀᴛᴇᴅ!**\n"
                f"**Yᴏᴜʀ ғɪʟᴇs ᴡɪʟʟ ɴᴏᴡ ʙᴇ sᴇɴᴛ ᴀs {media_type.upper()} ᴛʏᴘᴇ.**",
                reply_markup=keyboard
            )
        except Exception as e:
            LOGGER.error(f"Media update error: {e}")
            await update.answer("⚠️ Failed to update media preference.", show_alert=True)


    elif cb_data == "fuckoff":
        try:
            await update.answer()
            await update.message.edit_text("Okay! Closed.")
        except Exception:
            pass

    # ✅ FSUB check button
    elif cb_data.startswith("fsub_check_"):
        original_user_id = int(cb_data.split("_")[-1])

        if user_id != original_user_id and not is_admin:
            return await update.answer("⛔ This button is not for you.", show_alert=True)

        # check subscription again
        if await is_subscribed(bot, user_id):
            try:
                await update.message.delete()
            except Exception:
                pass
            await update.answer("✅ Yᴏᴜ ᴄᴀɴ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ ɴᴏᴡ !", show_alert=False)
        else:
            await update.answer("❌ You must join the channel first!", show_alert=True)

  
    elif cb_data.startswith("rfs_ch_"):
        if not is_admin:
            return await update.answer("Admin only.", show_alert=True)
        cid = int(cb_data.split("_")[2])
        try:
            chat = await bot.get_chat(cid)
            mode = await db.get_channel_mode(cid)
            status = "🟢 ᴏɴ" if mode == "on" else "🔴 ᴏғғ"
            new_mode = "ᴏғғ" if mode == "on" else "on"
            buttons = [
                [InlineKeyboardButton(f"ʀᴇǫ ᴍᴏᴅᴇ {'OFF' if mode == 'on' else 'ON'}", callback_data=f"rfs_toggle_{cid}_{new_mode}")],
                [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="fsub_back")],
                [InlineKeyboardButton("✖️ Cʟᴏsᴇ", callback_data="close")]
            ]
            await update.message.edit_text(
                f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception:
            await update.answer("Failed to fetch channel info", show_alert=True)

    elif cb_data.startswith("rfs_toggle_"):
        if not is_admin:
            return await update.answer("Admin only.", show_alert=True)
        cid, action = cb_data.split("_")[2:]
        cid = int(cid)
        mode = "on" if action == "on" else "off"

        await db.set_channel_mode(cid, mode)
        await update.answer(f"Force-Sub set to {'ON' if mode == 'on' else 'OFF'}")

        # Refresh the same channel's mode view
        chat = await bot.get_chat(cid)
        status = "🟢 ON" if mode == "on" else "🔴 OFF"
        new_mode = "off" if mode == "on" else "on"
        buttons = [
            [InlineKeyboardButton(f"ʀᴇǫ ᴍᴏᴅᴇ {'OFF' if mode == 'on' else 'ON'}", callback_data=f"rfs_toggle_{cid}_{new_mode}")],
            [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="fsub_back")],
            [InlineKeyboardButton("✖️ Cʟᴏsᴇ", callback_data="close")]
        ]
        await update.message.edit_text(
            f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif cb_data == "fsub_back":
        if not is_admin:
            return await update.answer("Admin only.", show_alert=True)
        channels = await db.show_channels()
        buttons = []
        for cid in channels:
            try:
                chat = await bot.get_chat(cid)
                mode = await db.get_channel_mode(cid)
                status = "🟢" if mode == "on" else "🔴"
                buttons.append([InlineKeyboardButton(f"{status} {chat.title}", callback_data=f"rfs_ch_{cid}")])
                buttons.append([InlineKeyboardButton("✖️ Cʟᴏsᴇ", callback_data="close")])
            except:
                continue

        await update.message.edit_text(
            "sᴇʟᴇᴄᴛ ᴀ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴛᴏɢɢʟᴇ ɪᴛs ғᴏʀᴄᴇ-sᴜʙ ᴍᴏᴅᴇ:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )


    elif cb_data == "premium":
        await update.answer()
        await update.message.delete()
        await app.send_photo(
            chat_id=update.message.chat.id,
            photo="https://graph.org/file/4d765d3c53783f6ff670d-21029256a9aeab6a6a.jpg",
            caption=(
                #f"👋 {update.from_user.username}\n\n"
                #f"🎖️ Available Plans :\n\n"
                #f"● {PRICE1}  For 0 Days Prime Membership\n\n"
                #f"● {PRICE2}  For 1 Month Prime Membership\n\n"
                #f"● {PRICE3}  For 3 Months Prime Membership\n\n"
                #f"● {PRICE4}  For 6 Months Prime Membership\n\n"
                #f"● {PRICE5}  For 1 Year Prime Membership\n\n\n"
                #f"💵 ASK UPI ID TO ADMIN AND PAY THERE -  <code>{UPI_ID}</code>\n\n\n"
                f"♻️ After Payment You Will Get Instant Membership \n\n\n"
                f"‼️ Must Send Screenshot after payment & If anyone want custom time membrship then ask admin"
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "ADMIN 24/7", url="https://t.me/FILE_SHARINGBOTS"
                        )
                    ],
                    [InlineKeyboardButton("🔒 Close", callback_data="close")],
                ]
            )
        )

    # ---------------- SHORTENER SYSTEM ---------------- #
    elif cb_data.startswith("toggle_shortener_"):
        # SECURITY: Admin-only shortener toggle
        if not is_admin:
            await update.answer("⛔ Admin only", show_alert=True)
            return
        shortener_num = cb_data.split("_")[-1]
        try:
            if shortener_num == "1":
                current_url = await db.get_shortener_url1()
                if current_url:
                    await db.deactivate_shortener1()
                    text = "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 1 ʜᴀs ʙᴇᴇɴ ᴅɪsᴀʙʟᴇᴅ</b>"
                else:
                    text = (
                        "⚠️ <b>sʜᴏʀᴛᴇɴᴇʀ 1 ɪs ɴᴏᴛ ᴄᴏɴғɪɢᴜʀᴇᴅ</b>\n\n"
                        "ᴘʟᴇᴀsᴇ ᴄᴏɴғɪɢᴜʀᴇ ᴜsɪɴɢ:\n"
                        "<code>/shortlink1 url api_key</code>"
                    )
            else:
                current_url = await db.get_shortener_url2()
                if current_url:
                    await db.deactivate_shortener2()
                    text = "✅ <b>sʜᴏʀᴛᴇɴᴇʀ 2 ʜᴀs ʙᴇᴇɴ ᴅɪsᴀʙʟᴇᴅ</b>"
                else:
                    text = (
                        "⚠️ <b>sʜᴏʀᴛᴇɴᴇʀ 2 ɪs ɴᴏᴛ ᴄᴏɴғɪɢᴜʀᴇᴅ</b>\n\n"
                        "ᴘʟᴇᴀsᴇ ᴄᴏɴғɪɢᴜʀᴇ ᴜsɪɴɢ:\n"
                        "<code>/shortlink2 url api_key</code>"
                    )

            buttons = [
                [InlineKeyboardButton("◀️ ʙᴀᴄᴋ", callback_data=f"shortener_settings{shortener_num}")],
                [InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]
            ]
            await update.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
            await update.answer()
        except Exception as e:
            LOGGER.error(f"Error toggling shortener: {e}")
            await update.answer("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

    elif cb_data.startswith("shortener_settings"):
        # SECURITY: Admin-only shortener settings
        if not is_admin:
            await update.answer("⛔ Admin only", show_alert=True)
            return
        shortener_num = cb_data[-1]
        try:
            if shortener_num == "1":
                url = await db.get_shortener_url1()
                api = await db.get_shortener_api1()
                tut_video = await db.get_tut_video1()
            else:
                url = await db.get_shortener_url2()
                api = await db.get_shortener_api2()
                tut_video = await db.get_tut_video2()

            is_active = bool(url)
            status = "🟢 ᴀᴄᴛɪᴠᴇ" if is_active else "🔴 ɪɴᴀᴄᴛɪᴠᴇ"
            tutorial = f'<a href="{tut_video}">ᴠɪᴇᴡ</a>' if tut_video else 'ɴᴏᴛ sᴇᴛ'
            masked_api = (api[:4] + "...") if api else 'ɴᴏᴛ sᴇᴛ'

            response_text = (
                f"<b>⚙️ sʜᴏʀᴛᴇɴᴇʀ {shortener_num} sᴇᴛᴛɪɴɢs</b>\n\n"
                f"┣ <b>sɪᴛᴇ:</b> <code>{url or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                f"┣ <b>ᴀᴘɪ:</b> <code>{masked_api}</code>\n"
                f"┣ <b>sᴛᴀᴛᴜs:</b> {status}\n"
                f"┗ <b>ᴛᴜᴛᴏʀɪᴀʟ:</b> {tutorial}"
            )

            buttons = [
                [InlineKeyboardButton(
                    "ᴇɴᴀʙʟᴇ" if not is_active else "ᴅɪsᴀʙʟᴇ",
                    callback_data=f"toggle_shortener_{shortener_num}",
                    style=ButtonStyle.SUCCESS if not is_active else ButtonStyle.DANGER,
                )],
                [InlineKeyboardButton("🔧 ᴄᴏɴғɪɢᴜʀᴇ", callback_data=f"set_shortener_{shortener_num}"),
                 InlineKeyboardButton("📹 ᴛᴜᴛᴏʀɪᴀʟ", callback_data=f"set_tutorial_{shortener_num}")],
                [InlineKeyboardButton("◀️ ʙᴀᴄᴋ", callback_data="shortner")],
                [InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]
            ]

            await update.message.edit_text(response_text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
            await update.answer()
        except Exception as e:
            LOGGER.error(f"Error in shortener settings: {e}")
            await update.answer("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

    elif cb_data.startswith("set_shortener_") or cb_data.startswith("set_tutorial_"):
        # SECURITY: Admin-only shortener configuration
        if not is_admin:
            await update.answer("⛔ Admin only", show_alert=True)
            return
        parts = cb_data.split("_")
        action, shortener_num = parts[1], parts[2]
        try:
            if action == "shortener":
                text = (
                    f"<b>⚙️ ᴄᴏɴғɪɢᴜʀᴇ sʜᴏʀᴛᴇɴᴇʀ {shortener_num}</b>\n\n"
                    f"ᴜsᴇ ᴛʜᴇ ғᴏʟʟᴏᴡɪɴɢ ᴄᴏᴍᴍᴀɴᴅ:\n"
                    f"<code>/shortlink{shortener_num} url api_key</code>\n\n"
                    f"<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                    f"<code>/shortlink{shortener_num} example.com 123456789</code>"
                )
            else:
                text = (
                    f"<b>📹 sᴇᴛ ᴛᴜᴛᴏʀɪᴀʟ {shortener_num}</b>\n\n"
                    f"ᴜsᴇ ᴛʜᴇ ғᴏʟʟᴏᴡɪɴɢ ᴄᴏᴍᴍᴀɴᴅ:\n"
                    f"<code>/tutorial{shortener_num} url</code>\n\n"
                    f"<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                    f"<code>/tutorial{shortener_num} https://example.com/tutorial.mp4</code>"
                )

            buttons = [
                [InlineKeyboardButton("◀️ ʙᴀᴄᴋ", callback_data=f"shortener_settings{shortener_num}")],
                [InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]
            ]

            await update.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
            await update.answer()
        except Exception as e:
            LOGGER.error(f"Error in set {action} callback: {e}")
            await update.answer("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ", show_alert=True)

    # SHORTENER MAIN MENU
    elif cb_data == "shortner" or cb_data == "shortener":
        # SECURITY: Admin-only shortener menu
        if not is_admin:
            await update.answer("⛔ Admin only", show_alert=True)
            return
        try:
            # Fetch both shorteners
            shortener1_url = await db.get_shortener_url1()
            shortener1_api = await db.get_shortener_api1()
            tut_video1 = await db.get_tut_video1()

            shortener2_url = await db.get_shortener_url2()
            shortener2_api = await db.get_shortener_api2()
            tut_video2 = await db.get_tut_video2()

            masked_api1 = (shortener1_api[:4] + "...") if shortener1_api else 'ɴᴏᴛ sᴇᴛ'
            masked_api2 = (shortener2_api[:4] + "...") if shortener2_api else 'ɴᴏᴛ sᴇᴛ'

            response_text = "<b>🔗 ᴜʀʟ sʜᴏʀᴛᴇɴᴇʀ sᴇᴛᴛɪɴɢs</b>\n\n"

            # Shortener 1
            if shortener1_url is not None:
                is_active1 = bool(shortener1_url and shortener1_api)
                status1 = "🟢" if is_active1 else "🔴"
                tutorial1 = f'<a href="{tut_video1}">ᴄʟɪᴄᴋ ʜᴇʀᴇ</a>' if tut_video1 else 'ɴᴏᴛ sᴇᴛ'
                response_text += (
                    f"<b>📌 sʜᴏʀᴛᴇɴᴇʀ 1</b>\n"
                    f"┣ <b>sᴛᴀᴛᴜs:</b> {status1}\n"
                    f"┣ <b>ᴜʀʟ:</b> <code>{shortener1_url or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                    f"┣ <b>ᴀᴘɪ:</b> <code>{masked_api1}</code>\n"
                    f"┗ <b>ᴛᴜᴛᴏʀɪᴀʟ:</b> {tutorial1}\n\n"
                )

            # Shortener 2
            if shortener2_url is not None:
                is_active2 = bool(shortener2_url and shortener2_api)
                status2 = "🟢" if is_active2 else "🔴"
                tutorial2 = f'<a href="{tut_video2}">ᴄʟɪᴄᴋ ʜᴇʀᴇ</a>' if tut_video2 else 'ɴᴏᴛ sᴇᴛ'
                response_text += (
                    f"<b>📌 sʜᴏʀᴛᴇɴᴇʀ 2</b>\n"
                    f"┣ <b>sᴛᴀᴛᴜs:</b> {status2}\n"
                    f"┣ <b>ᴜʀʟ:</b> <code>{shortener2_url or 'ɴᴏᴛ sᴇᴛ'}</code>\n"
                    f"┣ <b>ᴀᴘɪ:</b> <code>{masked_api2}</code>\n"
                    f"┗ <b>ᴛᴜᴛᴏʀɪᴀʟ:</b> {tutorial2}\n\n"
                )

            # Buttons
            buttons = [
                [InlineKeyboardButton("📎 sʜᴏʀᴛᴇɴᴇʀ ①", callback_data="shortener_settings_1"),
                 InlineKeyboardButton("📎 sʜᴏʀᴛᴇɴᴇʀ ②", callback_data="shortener_settings_2")],
                [InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close")]
            ]

            await update.message.edit_text(
                text=response_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=True
            )
            await update.answer()

        except Exception as e:
            LOGGER.error(f"Error loading shortener menu: {e}")
            await update.answer("⚠️ Failed to load shortener status", show_alert=True)


    # Audio selection buttons
    elif cb_data.startswith("audio_"):
        from bot.audio import audio_choices
        parts = cb_data.split("_")
        original_user_id = int(parts[-1])

        if user_id != original_user_id:
            return await update.answer("❌ ᴛʜᴏᴅɪ ɢᴀɴᴅ ʜᴀᴍsᴇ ʙʜɪ ᴍᴀʀᴡᴀ ʟᴏ ᴠɪᴋᴀs ᴊɪ", show_alert=True)

        audio_choices[user_id] = cb_data  

        try:
            await update.message.delete()
        except Exception:
            pass
        await update.answer("✅ Audio selected", show_alert=False)

    elif cb_data.startswith("spoiler_"):
        try:
            data_parts = cb_data.split(":")
            spoiler_value_str = data_parts[0].split("_", 1)[1].lower()
            allowed_user_id = int(data_parts[1])

            spoiler_value = True if spoiler_value_str == "true" else False
        except Exception:
            return await update.answer("❌ Invalid callback format.", show_alert=True)

        if user_id != allowed_user_id:
            return await update.answer("❌ ᴛʜᴏᴅɪ ɢᴀɴᴅ ʜᴀᴍsᴇ ʙʜɪ ᴍᴀʀᴡᴀ ʟᴏ ᴠɪᴋᴀs ᴊɪ", show_alert=True)

        await db.set_user_spoiler(user_id, spoiler_value)

        keyboard = build_spoiler_keyboard(spoiler_value, user_id)

        try:
            await update.answer(f"✅ Spoiler mode set to {'ON' if spoiler_value else 'OFF'}", show_alert=False)
            await update.message.edit_text(
                f"**Sᴘᴏɪʟᴇʀ Mᴏᴅᴇ Uᴘᴅᴀᴛᴇᴅ!**\n"
                f"Yᴏᴜʀ ғɪʟᴇs ᴡɪʟʟ ɴᴏᴡ ʙᴇ sᴇɴᴛ ᴡɪᴛʜ sᴘᴏɪʟᴇʀ: {'ON' if spoiler_value else 'OFF'}\n\n"
                f"<blockquote> Nᴏᴛᴇ: ᴛᴏ ɢᴇᴛ sᴘᴏɪʟᴇʀ ᴜsᴇ /setmedia ᴀɴᴅ ᴄʜᴀɴɢᴇ ᴛᴏ ᴠɪᴅᴇᴏ </blockquote>",
                reply_markup=keyboard
            )
        except Exception as e:
            LOGGER.error(f"Spoiler update error: {e}")
            await update.answer("⚠️ Failed to update spoiler preference.", show_alert=True)


    elif cb_data.startswith("addaudio_done:"):
        allowed_id = int(cb_data.split(":")[1])
        if allowed_id != user_id:
            return await update.answer("❌ ᴛʜᴏᴅɪ ɢᴀɴᴅ ʜᴀᴍsᴇ ʙʜɪ ᴍᴀʀᴡᴀ ʟᴏ ᴠɪᴋᴀs ᴊɪ", show_alert=True)

        if user_id in addaudio_timers:
            addaudio_timers[user_id].cancel()
            del addaudio_timers[user_id]

        if user_id in addaudio_button_msgs:
            await asyncio.sleep(0.5)
            try:
                await addaudio_button_msgs[user_id].delete()
            except:
                pass
            del addaudio_button_msgs[user_id]

        if user_id not in addaudio_queue:
            addaudio_queue.append(user_id)
            await process_addaudio_task(app, user_id)

        return await update.answer("✅ Sᴛᴀʀᴛɪɴɢ ᴍᴇʀɢᴇ ɴᴏᴡ...")

    elif cb_data.startswith("addaudio_more:"):
        allowed_id = int(cb_data.split(":")[1])
        if allowed_id != user_id:
            return await update.answer("❌ ᴛʜᴏᴅɪ ɢᴀɴᴅ ʜᴀᴍsᴇ ʙʜɪ ᴍᴀʀᴡᴀ ʟᴏ ᴠɪᴋᴀs ᴊɪ", show_alert=True)

        if user_id in addaudio_timers:
            addaudio_timers[user_id].cancel()

        if user_id in addaudio_button_msgs:
            await asyncio.sleep(0.5)
            try:
                await addaudio_button_msgs[user_id].delete()
            except:
                pass
            del addaudio_button_msgs[user_id]

        audio_count = len(addaudio_requests[user_id]["audio_msgs"])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Sᴛᴀʀᴛ ᴀᴅᴅɪɴɢ", callback_data=f"addaudio_done:{user_id}")],
            [InlineKeyboardButton("🫷ᴡᴀɪᴛ, sᴇɴᴅɪɴɢ ᴍᴏʀᴇ🫸", callback_data=f"addaudio_more:{user_id}")]
        ])
        button_msg = await update.message.reply(
            f"🎧 {audio_count} ᴀᴜᴅɪᴏ ᴛʀᴀᴄᴋs {'s' if audio_count > 1 else ''} ʀᴇᴄᴇɪᴠᴇᴅ.\n\n"
            "Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇɴᴅ ᴍᴏʀᴇ ᴀᴜᴅɪᴏ ғɪʟᴇs ᴏʀ sᴛᴀʀᴛ ᴍᴇʀɢɪɴɢ ɴᴏᴡ?",
            reply_markup=keyboard
        )

        addaudio_button_msgs[user_id] = button_msg
        addaudio_timers[user_id] = asyncio.create_task(
            start_addaudio_timer(app, user_id, 30, button_msg)
        )

        await update.answer("⏳ ʏᴏᴜ ʜᴀᴠᴇ 𝟹𝟶 sᴇᴄᴏɴᴅs ᴛᴏ Sᴇɴᴅ ᴍᴏʀᴇ ᴀᴜᴅɪᴏs.")

    # Upload preference selection
    elif cb_data.startswith("upload_"):
        try:
            if cb_data == "upload_nochannel":
                return await update.answer(
                    "⚠️ 𝗬𝗼𝘂 𝗵𝗮𝘃𝗲 𝗻𝗼𝘁 𝘀𝗲𝘁 𝗮 𝗰𝗵𝗮𝗻𝗻𝗲𝗹!\nUse /setchannel 𝘁𝗼 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗲 𝗼𝗻𝗲.",
                    show_alert=True
                )

            data_parts = cb_data.split(":")
            upload_type = data_parts[0].split("_", 1)[1].lower()
            allowed_user_id = int(data_parts[1])
        except Exception:
            return await update.answer("❌ Invalid callback format.", show_alert=True)

        if user_id != allowed_user_id:
            return await update.answer("❌ ᴛʜᴏᴅɪ ɢᴀɴᴅ ʜᴀᴍsᴇ ʙʜɪ ᴍᴀʀᴡᴀ ʟᴏ ᴠɪᴋᴀs ᴊɪ", show_alert=True)

        # Save preference
        await db.set_upload_preference(user_id, upload_type)

        # Rebuild keyboard with updated state
        channel_id = await db.get_user_channel(user_id)
        keyboard = build_upload_keyboard(upload_type, user_id, channel_id)

        try:
            await update.answer(f"✅ Upload preference set to {upload_type.upper()}", show_alert=False)
            await update.message.edit_text(
                f"**Uᴘʟᴏᴀᴅ ᴘʀᴇғᴇʀᴇɴᴄᴇ ᴜᴘᴅᴀᴛᴇᴅ!**\n"
                f"Fɪʟᴇs ᴡɪʟʟ ɴᴏᴡ ʙᴇ sᴇɴᴛ ᴛᴏ → {upload_type.upper()}",
                reply_markup=keyboard
            )
        except Exception as e:
            LOGGER.error(f"Upload update error: {e}")
            await update.answer("⚠️ Failed to update upload preference.", show_alert=True)

# ==============================
    # 🧾 METADATA HANDLER (spoiler-style)
    # ==============================
    elif cb_data.startswith("metadata_"):
        try:
            data_parts = cb_data.split(":")
            action = data_parts[0].split("_", 1)[1].lower()
            allowed_user_id = int(data_parts[1])
        except Exception:
            return await update.answer("❌ Invalid metadata callback.", show_alert=True)

        if user_id != allowed_user_id:
            return await update.answer("🚫 This metadata menu isn’t yours.", show_alert=True)

        # Handle actions
        if action == "on":
            await db.set_metadata(user_id, "On")
        elif action == "off":
            await db.set_metadata(user_id, "Off")
        elif action == "info":
            return await update.message.edit_text(
                text=Localisation.META_TXT,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Hᴏᴍᴇ", callback_data="start"),
                        InlineKeyboardButton("Bᴀᴄᴋ", callback_data=f"metadata_back:{user_id}")
                    ]
                ])
            )
        elif action == "back":
            pass  # Rebuild main metadata panel

        # Fetch all metadata details
        current = await db.get_metadata(user_id)
        title = await db.get_title(user_id)
        author = await db.get_author(user_id)
        artist = await db.get_artist(user_id)
        video = await db.get_video(user_id)
        audio = await db.get_audio(user_id)
        subtitle = await db.get_subtitle(user_id)
        encoded_by = await db.get_encoded_by(user_id)
        custom_tag = await db.get_custom_tag(user_id)
        commentz = await db.get_commentz(user_id)

        text = f"""
**㊋ Yᴏᴜʀ Mᴇᴛᴀᴅᴀᴛᴀ ɪꜱ ᴄᴜʀʀᴇɴᴛʟʏ: {current}**

**◈ Tɪᴛʟᴇ ▹** `{title or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Aᴜᴛʜᴏʀ ▹** `{author or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Aʀᴛɪꜱᴛ ▹** `{artist or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Aᴜᴅɪᴏ ▹** `{audio or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Sᴜʙᴛɪᴛʟᴇ ▹** `{subtitle or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Vɪᴅᴇᴏ ▹** `{video or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Eɴᴄᴏᴅᴇᴅ Bʏ ▹** `{encoded_by or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Cᴜsᴛᴏᴍ Tᴀɢ ▹** `{custom_tag or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
**◈ Cᴏᴍᴍᴇɴᴛ ▹** `{commentz or 'Nᴏᴛ ꜰᴏᴜɴᴅ'}`
        """

        keyboard = build_metadata_keyboard(current, user_id)

        try:
            await update.message.edit_text(
                text=text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except Exception as e:
            LOGGER.error(f"Metadata update error: {e}")
            await update.answer("⚠️ Failed to update metadata.", show_alert=True)
        return

    # Unknown callback fallback
    else:
        await update.answer("⚙️ Unknown action.", show_alert=False)
