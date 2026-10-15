# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Single source of truth for the bot command menu (Telegram) and the /help text.

Every entry is (section, command, description). The same list is pushed to
Telegram via set_bot_commands() on startup and rendered by help_messages().
"""
import logging
import os
import subprocess
import sys
import time
from glob import glob
from typing import List, Tuple

from pyrogram.types import BotCommand

LOGGER = logging.getLogger("CommandMenu")

TELEGRAM_MENU_LIMIT = 100

REAUTH_MARKER = ".session_reauth"
INSTANCE_LOCK = ".bot_instance.lock"

COMMANDS: List[Tuple[str, str, str]] = [
    # --- Main ---
    ("Main", "start", "Check I'm Alive ⚡️"),
    ("Main", "help", "Show All Available Commands 💠"),
    ("Main", "ping", "Ping Bot 🏓"),
    ("Main", "stats", "Server Performance Overview 📈"),
    ("Main", "restart", "Bot Restart 🔄"),
    ("Main", "update", "Git Pull Latest Updates ⬆️🔧"),
    ("Main", "log", "Get Bot Logs 📑"),
    ("Main", "exec", "Run Python Code (Admin Only) 🐍"),
    ("Main", "eval", "Evaluate Python (Admin Only) 🧪"),
    ("Main", "encsettings", "Admin Encoding Settings Panel ⚙️"),
    ("Main", "resetsettings", "Reset Encoding Defaults (Admin Only) ↺"),
    ("Main", "speedtest", "Test Network Speed (Admin Only) 🌐"),

    # --- Leech ---
    ("Leech", "leech", "Leech Files Or Links ⚙️⚡️"),
    ("Leech", "l", "Same As /leech ⚡️"),
    ("Leech", "leechhelp", "All /leech Flags Reference 🚩"),

    # --- Encode ---
    ("Encode", "compress", "Compress Media 📦"),
    ("Encode", "all", "Encode In All Qualities At Once 🌐"),
    ("Encode", "144p", "Convert To 144p 🔹"),
    ("Encode", "240p", "Convert To 240p 🔹"),
    ("Encode", "360p", "Convert To 360p 🔹"),
    ("Encode", "480p", "Convert To 480p 🔹"),
    ("Encode", "720p", "Convert To 720p 🔷"),
    ("Encode", "1080p", "Convert To 1080p 🔷"),
    ("Encode", "2160p", "Convert To 2160p (4K) 🟣"),
    ("Encode", "4k", "Convert To 4K (Same As 2160p) 🟣"),
    ("Encode", "settings", "Configure File Settings ⚙️"),
    ("Encode", "preset", "Set Encoding Preset ⚙️"),
    ("Encode", "crf", "Set CRF 🎚"),
    ("Encode", "audio", "Set Audio Bitrate 🎚"),
    ("Encode", "codec", "Set Video Codec 🎞"),
    ("Encode", "setmedia", "Set Preferred Media Type 🎚"),

    # --- Subtitles ---
    ("Subtitles", "sub", "Add Soft Subtitles 💬"),
    ("Subtitles", "hsub", "Add Hard Subtitles 🔥"),
    ("Subtitles", "rsub", "Remove All Subtitles 🚫💬"),
    ("Subtitles", "extract_sub", "Extract Subtitles From Video ⏏️💬"),

    # --- Audio ---
    ("Audio", "addaudio", "Add Audio To Video 🎧➕"),
    ("Audio", "remaudio", "Remove Audio From Video 🎧❌"),
    ("Audio", "extract_audio", "Extract Audio From Video 🎵⏏️"),

    # --- Video tools ---
    ("Video Tools", "cut", "Trim Video By Time ✂️"),
    ("Video Tools", "crop", "Change Video Aspect Ratio 🖼"),
    ("Video Tools", "merge", "Merge Multiple Videos 🎬➕"),
    ("Video Tools", "ss", "Take Screenshot From Video 📸"),
    ("Video Tools", "addwatermark", "Add Logo Watermark To Video 🎞"),
    ("Video Tools", "setwatermark", "Set Default Watermark 💧"),
    ("Video Tools", "getwatermark", "Get Current Watermark 🏷"),
    ("Video Tools", "delwatermark", "Delete Default Watermark 💧❌"),

    # --- Metadata ---
    ("Metadata", "metadata", "To Set Metadata Code ⚡️"),
    ("Metadata", "settitle", "Set Video Title 🏷"),
    ("Metadata", "setauthor", "Set Author Name ✍️"),
    ("Metadata", "setartist", "Set Artist Name 🎤"),
    ("Metadata", "setaudio", "Set Audio Tag 🎵"),
    ("Metadata", "setsubtitle", "Set Subtitle Tag 💬"),
    ("Metadata", "setvideo", "Set Video Tag 🎞"),
    ("Metadata", "setencoded_by", "Set Encoded By Tag 🏷"),
    ("Metadata", "setcustom_tag", "Set Custom Tag 🏷"),
    ("Metadata", "setcomment", "Set Comment 💬"),
    ("Metadata", "setallmeta", "Apply All Metadata Tags 🏷"),

    # --- Thumbnails ---
    ("Thumbnails", "setthumb", "Set A Custom Thumbnail 🖼"),
    ("Thumbnails", "getthumb", "Get Saved Thumbnail 👁"),
    ("Thumbnails", "delthumb", "Delete Saved Thumbnail ❕"),
    ("Thumbnails", "addthumb", "Add Custom Thumbnail 🖼➕"),
    ("Thumbnails", "extract_thumb", "Extract Thumbnail From Video 🖼⏏️"),

    # --- Info & destination ---
    ("Info", "mediainfo", "Get Detailed Media Info ℹ️🎥"),
    ("Info", "mi", "Get Detailed Media Info ℹ️🎥"),
    ("Info", "spoiler", "Enable Or Disable Spoiler 🙈"),
    ("Info", "upload", "Set Upload Destination ☁️📤"),
    ("Info", "setchannel", "Set Upload Channel 📺"),
    ("Info", "getchannel", "Get Upload Channel 📺"),
    ("Info", "delchannel", "Delete Upload Channel 📺❌"),

    # --- Queue ---
    ("Queue", "status", "View Queue 📊"),
    ("Queue", "queue", "View Queue 📊"),
    ("Queue", "clear", "Clear Queue 🧹"),
    ("Queue", "cancelall", "Cancel All Running Tasks 🛑"),

    # --- Shortlink & Premium ---
    ("Shortlink & Premium", "shortlink1", "Set Shortlink 1 🔗1️⃣"),
    ("Shortlink & Premium", "shortlink2", "Set Shortlink 2 🔗2️⃣"),
    ("Shortlink & Premium", "tutorial1", "Tutorial Link 1 🎓1️⃣"),
    ("Shortlink & Premium", "tutorial2", "Tutorial Link 2 🎓2️⃣"),
    ("Shortlink & Premium", "shortner", "View Shortener 🔗"),
    ("Shortlink & Premium", "shortner1", "Shortener 1 Info 🛠1️⃣"),
    ("Shortlink & Premium", "shortner2", "Shortener 2 Info 🛠2️⃣"),
    ("Shortlink & Premium", "addpaid", "Add Premium ⭐️"),
    ("Shortlink & Premium", "listpaid", "List Premiums 📃⭐️"),
    ("Shortlink & Premium", "rempaid", "Remove Premium ❌⭐️"),
    ("Shortlink & Premium", "myplan", "Check My Premium Plan ⭐️"),

    # --- Force sub ---
    ("Force Sub", "addchnl", "Add FSub Channel 📢"),
    ("Force Sub", "delchnl", "Delete FSub Channel ❌"),
    ("Force Sub", "listchnl", "List FSub Channels 📜"),
    ("Force Sub", "fsub_mode", "FSub Mode Check 🔍"),
    ("Force Sub", "set_vf_time", "Set Verified Time ⏱"),
    ("Force Sub", "get_vf_time", "Get Verified Time ⏱"),
]


def all_commands() -> List[Tuple[str, str]]:
    """Flatten the registry as (command, description) pairs."""
    return [(cmd, desc) for _, cmd, desc in COMMANDS]


def menu_commands() -> List[BotCommand]:
    """Commands in the exact shape Telegram's set_bot_commands() wants."""
    cmds = []
    for cmd, desc in all_commands():
        # Telegram: command <= 32 chars, description <= 256 chars, 100 max
        cmds.append(BotCommand(str(cmd)[:32], str(desc)[:256]))
    if len(cmds) > TELEGRAM_MENU_LIMIT:
        LOGGER.warning(
            f"Command menu has {len(cmds)} entries (Telegram allows "
            f"{TELEGRAM_MENU_LIMIT}) - extras will be rejected."
        )
    return cmds


def help_messages() -> List[str]:
    """Render the registry as /help chunks (Telegram allows 4096 chars).

    Sections are packed greedily so /help sends as few messages as possible.
    """
    sections: List[Tuple[str, List[str]]] = []
    for section, cmd, desc in COMMANDS:
        if not sections or sections[-1][0] != section:
            sections.append((section, []))
        sections[-1][1].append(f"/{cmd} - {desc}")

    chunks: List[List[str]] = []
    buf: List[str] = []
    buf_len = 0

    def flush():
        nonlocal buf_len
        if buf:
            chunks.append(list(buf))
            buf.clear()
            buf_len = 0

    for section, entries in sections:
        block = [f"<b>» {section}:</b>"] + entries
        block_len = sum(len(line) + 1 for line in block) + (1 if buf else 0)
        if buf and buf_len + block_len > 3900:
            flush()
        for i, line in enumerate(block):
            if buf:
                buf.append("")
            buf.append(line)
            buf_len += len(line) + 1
    flush()

    return [
        "<blockquote expandable>" + "\n".join(chunk) + "</blockquote>"
        for chunk in chunks
    ]


def _force_delete_session() -> bool:
    """Best-effort removal of the local session so the next boot signs in fresh."""
    try:
        from bot import SESSION_NAME

        pattern = f"{SESSION_NAME}.session*"
    except Exception:
        return False
    for _ in range(5):
        left = glob(pattern)
        if not left:
            return True
        for path in left:
            try:
                os.remove(path)
            except OSError:
                pass
        time.sleep(0.2)
    return not glob(pattern)


def _relaunch_bot() -> None:
    """Drop the instance lock and start a clean bot process."""
    try:
        os.remove(INSTANCE_LOCK)
    except OSError:
        pass
    if sys.platform == "win32":
        subprocess.Popen([sys.executable, "-m", "bot"], cwd=os.getcwd())
        os._exit(0)
    os.execl(sys.executable, sys.executable, "-m", "bot")


async def register_menu(app) -> bool:
    """Push the command list to Telegram's bot menu (auto on startup)."""
    import asyncio

    last_err = None
    for attempt in range(3):
        try:
            cmds = menu_commands()
            await app.set_bot_commands(cmds)
            LOGGER.info(f"[Menu] Registered {len(cmds)} bot commands with Telegram.")
            if os.path.exists(REAUTH_MARKER):
                try:
                    os.remove(REAUTH_MARKER)
                except OSError:
                    pass
            return True
        except Exception as e:
            last_err = e
            if "AUTH_KEY" in str(e).upper():
                break
            if attempt < 2:
                await asyncio.sleep(5)
    LOGGER.warning(f"[Menu] set_bot_commands failed: {last_err}")
    if "AUTH_KEY" in str(last_err).upper():
        LOGGER.warning(
            "[Menu] Session auth key is not registered with Telegram - "
            "deleting the session file and restarting for a fresh login."
        )
        _force_delete_session()
        if os.path.exists(REAUTH_MARKER):
            LOGGER.warning(
                "[Menu] Fresh login failed again. Check TG_BOT_TOKEN, APP_ID and "
                "API_HASH in secrets, delete .session_reauth, then restart the bot."
            )
            return False
        try:
            with open(REAUTH_MARKER, "w") as fh:
                fh.write("1")
        except OSError:
            pass
        _relaunch_bot()
        return False
    return False
