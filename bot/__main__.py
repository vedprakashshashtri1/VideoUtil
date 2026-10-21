# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# oof
from datetime import datetime as dt
import os, math, sys
from pyrogram.types import Message
import asyncio, aiohttp
import shutil, time
import subprocess
from pathlib import Path
from bot.helper_funcs.ffmpeg import media_info, take_screen_shot
import mimetypes
from mimetypes import guess_type
#from pyrogram import InputFile
import aiofiles
from bot import (
    APP_ID,
    API_HASH,
    AUTH_USERS,
    DOWNLOAD_LOCATION,
    CROP_LOCATION,
    HSUB_LOCATION,
    MERGE_LOCATION,
    LEECH_LOCATION,
    LOGGER,
    TG_BOT_TOKEN,
    BOT_USERNAME,
    SESSION_NAME,
    
    data,
    app,
    crf,
    resolution,
    audio_b,
    preset,
    codec,
    name,
    size
    

)
from bot.helper_funcs.utils import *
from bot.helper_funcs.display_progress import *
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from database import *
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
from PIL import Image
from bot.plugins.call_back_button_handler import button
crf.append("30")
codec.append("libx264")
resolution.append("854x480")
preset.append("veryfast")
audio_b.append("64k")



uptime = dt.now()

if __name__ == "__main__" :
    # Single-instance guard: two `python -m bot` runs sharing one session file
    # cause AUTH_KEY_UNREGISTERED. Exit when another live instance owns the lock.
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    INSTANCE_LOCK = ".bot_instance.lock"
    lock_pid = 0
    try:
        with open(INSTANCE_LOCK, "r") as _lock_file:
            lock_pid = int(_lock_file.read().strip() or 0)
    except (OSError, ValueError):
        lock_pid = 0
    if lock_pid and lock_pid != os.getpid() and _pid_alive(lock_pid):
        LOGGER.warning(
            f"[Lock] Another bot instance (pid {lock_pid}) is already "
            "running with this session - exiting."
        )
        sys.exit(0)
    try:
        with open(INSTANCE_LOCK, "w") as _lock_file:
            _lock_file.write(str(os.getpid()))
    except OSError:
        pass

    # Ensure working directories exist and clear leftover partial files from previous runs
    for temp_dir in [DOWNLOAD_LOCATION, CROP_LOCATION, HSUB_LOCATION, MERGE_LOCATION, LEECH_LOCATION]:
        if os.path.isdir(temp_dir):
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                except Exception:
                    pass
        else:
            os.makedirs(temp_dir, exist_ok=True)

    from bot.helper_funcs.health_server import start_health_server
    start_health_server(LOGGER)

    @app.on_message(filters.incoming & filters.command(["restart", f"restart@{BOT_USERNAME}"]))
    async def restarter(client, message):
        if message.from_user.id not in AUTH_USERS:
            return

        restart_msg = await message.reply_text("<blockquote>🔄 ʀᴇsᴛᴀʀᴛɪɴɢ ᴛʜᴇ ʙᴏᴛ... Pʟᴇᴀsᴇ ᴡᴀɪᴛ.</blockquote>")
        try:
            with open(".restart_msg", "w") as f:
                f.write(f"{message.chat.id}\n{restart_msg.id}")
        except Exception as e:
            LOGGER.warning(f"Could not save restart state: {e}")

        async def _do_restart():
            await asyncio.sleep(1.5)
            LOGGER.info("Restart command: relaunching bot process...")
            try:
                os.remove(".bot_instance.lock")
            except OSError:
                pass
            if sys.platform == "win32":
                subprocess.Popen([sys.executable, "-m", "bot"], cwd=os.getcwd())
                os._exit(0)
            else:
                os.execl(sys.executable, sys.executable, "-m", "bot")

        asyncio.create_task(_do_restart())
  
        
    @app.on_message(filters.incoming & filters.command(["exec", f"exec@{BOT_USERNAME}"]))
    async def exec_cmd(app, message):
        await exec_message_f(app, message)
        
    @app.on_message(filters.incoming & filters.command(["eval", f"eval@{BOT_USERNAME}"]))
    async def eval_cmd(app, message):
        await eval_message_f(app, message)
        
    @app.on_message(filters.incoming & filters.command(["help", f"help@{BOT_USERNAME}"]))
    async def help_cmd(app, message):
        if Localisation.HELP_MESSAGE:
            await message.reply_text(Localisation.HELP_MESSAGE)
            return
        from bot.command_menu import help_messages
        for part in help_messages():
            await message.reply_text(part)
  
    @app.on_message(filters.incoming & filters.command(["log", f"log@{BOT_USERNAME}"]))
    async def log_cmd(app, message):
        await upload_log_file(app, message)

    @app.on_message(filters.incoming & filters.command(["ping", f"ping@{BOT_USERNAME}"]))
    async def ping_cmd(app, message):
        stt = time.time()
        reply_m = await message.reply_text("🏓 <b>Pinging...</b>")
        ms = round((time.time() - stt) * 1000, 2)
        v = ts(int((dt.now() - uptime).seconds) * 1000)
        u = f"<blockquote> Uptime = {v} </blockquote>"
        p = f"<blockquote>Pɪɴɢ = {ms}ms </blockquote>"
        await reply_m.edit_text(u + "\n" + p)

    from bot.features import *
    from bot.watermark import *
    from bot.split_videos import *
    from bot.merge_video import *
    from bot.subtitles import *
    from bot.thumbnail import *
    from bot.response import *
    from bot.compress import *
    from bot.audio import *
    from bot.leech import *
    from bot.crop import *
    from bot.fsub import *
    from bot.premium import *
    from bot.metadata import *
    from bot.encoding_settings import load_encoding_settings
    from bot.speedtest import *
    from bot.screenshot import *
    from bot.status_commands import *


    async def _notify_restarted():
        restart_meta_path = ".restart_msg"
        if not os.path.exists(restart_meta_path):
            return
        for _ in range(60):
            await asyncio.sleep(1)
            if getattr(app, "is_connected", False):
                break
        try:
            with open(restart_meta_path, "r") as f:
                lines = [l.strip() for l in f.read().split("\n") if l.strip()]
            if len(lines) >= 2:
                chat_id = int(lines[0])
                msg_id = int(lines[1])
                await app.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="<blockquote>✅ <b>ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b></blockquote>"
                )
            if os.path.exists(restart_meta_path):
                os.remove(restart_meta_path)
        except Exception as e:
            LOGGER.warning(f"Failed to notify restart: {e}")

    async def _register_command_menu():
        from bot.command_menu import register_menu
        for _ in range(60):
            if app.is_connected:
                break
            await asyncio.sleep(1)
        if not app.is_connected:
            LOGGER.warning("[Menu] Client not connected - command menu not registered.")
            return
        # is_connected only means the transport is up. Wait until the session
        # is actually authorized, otherwise set_bot_commands() races ahead of
        # the login and fails with AUTH_KEY_UNREGISTERED.
        for _ in range(30):
            try:
                await app.get_me()
                break
            except Exception:
                await asyncio.sleep(1)
        await register_menu(app)

    async def start_tasks():
        await load_encoding_settings()
        asyncio.create_task(expired_user_cleaner())
        from bot.helper_funcs.telegram_transport import wzgram_update_checker_loop
        asyncio.create_task(wzgram_update_checker_loop(app))
        asyncio.create_task(_notify_restarted())
        asyncio.create_task(_register_command_menu())
    main_loop = asyncio.get_event_loop()
    main_loop.run_until_complete(start_tasks())
    app.loop = main_loop

    # Run the bot
    app.run()

    # Relaunch process if restart was triggered
    restart_meta_path = ".restart_msg"
    if os.path.exists(restart_meta_path):
        LOGGER.info("Relaunching bot process now...")
        time.sleep(1.0)
        if sys.platform == "win32":
            subprocess.Popen([sys.executable, "-m", "bot"], cwd=os.getcwd())
            sys.exit(0)
        else:
            os.execl(sys.executable, sys.executable, "-m", "bot")

    



