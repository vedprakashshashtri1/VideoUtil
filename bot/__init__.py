# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import logging
from logging.handlers import RotatingFileHandler
import os
import time
import asyncio
try:
    import wzgram
    from wzgram import Client
    from wzgram.handlers import MessageHandler
    from wzgram import filters as pyro_filters
except ImportError:
    from pyrogram import Client
    from pyrogram.handlers import MessageHandler
    from pyrogram import filters as pyro_filters

# Provide safe subscription fallback on ListenerRegistry if any legacy/cached plugin accesses listeners[type]
try:
    from wzgram.types.listeners.registry import ListenerRegistry
    if not hasattr(ListenerRegistry, "__getitem__"):
        ListenerRegistry.__getitem__ = lambda self, key: list(getattr(self, "_live", {}).values())
except Exception:
    pass

try:
    from pyrogram.types.listeners.registry import ListenerRegistry as PyroListenerRegistry
    if not hasattr(PyroListenerRegistry, "__getitem__"):
        PyroListenerRegistry.__getitem__ = lambda self, key: list(getattr(self, "_live", {}).values())
except Exception:
    pass

if not hasattr(Client, "listen"):
    async def _fallback_listen(self, chat_id=None, filters=None, timeout=None, user_id=None, *args, **kwargs):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async def _listener_callback(c, message):
            if not future.done():
                future.set_result(message)

        flt = pyro_filters.chat(chat_id) if chat_id else pyro_filters.all
        if user_id:
            flt = flt & pyro_filters.user(user_id)
        if filters:
            flt = flt & filters

        handler = MessageHandler(_listener_callback, flt)
        self.add_handler(handler, group=-999)
        try:
            if timeout:
                return await asyncio.wait_for(future, timeout=timeout)
            return await future
        finally:
            self.remove_handler(handler, group=-999)

    Client.listen = _fallback_listen
else:
    _orig_listen = Client.listen

    async def _safe_listen(self, *args, **kwargs):
        if args:
            first = args[0]
            try:
                from wzgram.filters import Filter
            except ImportError:
                from pyrogram.filters import Filter
            if isinstance(first, (int, str)) or not isinstance(first, Filter):
                if "chat_id" not in kwargs:
                    kwargs["chat_id"] = first
                args = args[1:]
        return await _orig_listen(self, *args, **kwargs)

    Client.listen = _safe_listen
from bot.config import Config

# Constants and Auth Users
AUTH_USERS = set(Config.AUTH_USERS)
if Config.OWNER_ID:
    AUTH_USERS.add(Config.OWNER_ID)
AUTH_USERS = list(AUTH_USERS)


def is_authorised(message) -> bool:
    if message.chat is not None and message.chat.id in AUTH_USERS:
        return True
    return bool(message.from_user) and message.from_user.id in AUTH_USERS

# Bot Config
SESSION_NAME = Config.SESSION_NAME
TG_BOT_TOKEN = Config.TG_BOT_TOKEN
APP_ID = Config.APP_ID
API_HASH = Config.API_HASH
LOG_CHANNEL = Config.LOG_CHANNEL
DOWNLOAD_LOCATION = Config.DOWNLOAD_LOCATION
DOWNLOAD_LOCATION1 = Config.DOWNLOAD_LOCATION1
DOWNLOAD_LOCATION2 = Config.DOWNLOAD_LOCATION2
DOWNLOAD_LOCATION3 = Config.DOWNLOAD_LOCATION3
DOWNLOAD_LOCATION4 = Config.DOWNLOAD_LOCATION4
DOWNLOAD_LOCATION5 = Config.DOWNLOAD_LOCATION5
DOWNLOAD_LOCATION6 = Config.DOWNLOAD_LOCATION6
DOWNLOAD_LOCATION7 = Config.DOWNLOAD_LOCATION7
CROP_LOCATION = Config.CROP_LOCATION
HSUB_LOCATION = Config.HSUB_LOCATION
MERGE_LOCATION = Config.MERGE_LOCATION
LEECH_LOCATION = Config.LEECH_LOCATION
FINISHED_PROGRESS_STR = "█"
UN_FINISHED_PROGRESS_STR = "░"
BOT_START_TIME = time.time()
LOG_FILE_ZZGEVC = "Log.txt"
MAX_MESSAGE_LENGTH = 4096
BOT_USERNAME = Config.BOT_USERNAME
UPDATES_CHANNEL = Config.UPDATES_CHANNEL
OWNER_ID = Config.OWNER_ID

# Encoding Metadata Lists
data = []
data1 = []
data2 = []
data3 = []
data4 = []
data5 = []
data6 = []
data7 = []
crop = []
crf = []
size = []
name = []
resolution = []
audio_b = []
preset = []
codec = []
pid_list = []

# Create Downloads Directory
if not os.path.exists(DOWNLOAD_LOCATION):
    os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION1):
    os.makedirs(DOWNLOAD_LOCATION1, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION2):
    os.makedirs(DOWNLOAD_LOCATION2, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION3):
    os.makedirs(DOWNLOAD_LOCATION3, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION4):
    os.makedirs(DOWNLOAD_LOCATION4, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION5):
    os.makedirs(DOWNLOAD_LOCATION5, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION6):
    os.makedirs(DOWNLOAD_LOCATION6, exist_ok=True)

if not os.path.exists(DOWNLOAD_LOCATION7):
    os.makedirs(DOWNLOAD_LOCATION7, exist_ok=True)

if not os.path.exists(CROP_LOCATION):
    os.makedirs(CROP_LOCATION, exist_ok=True)

if not os.path.exists(HSUB_LOCATION):
    os.makedirs(HSUB_LOCATION, exist_ok=True)

if not os.path.exists(MERGE_LOCATION):
    os.makedirs(MERGE_LOCATION, exist_ok=True)

if not os.path.exists(LEECH_LOCATION):
    os.makedirs(LEECH_LOCATION, exist_ok=True)


# Clear Previous Logs
if os.path.exists(LOG_FILE_ZZGEVC):
    with open(LOG_FILE_ZZGEVC, "r+") as f_d:
        f_d.truncate(0)

# Logging Setup
logging.basicConfig(
    level=logging.WARNING,  # Changed from DEBUG to WARNING
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler(
            LOG_FILE_ZZGEVC,
            maxBytes=5 * 1024 * 1024,
            backupCount=2
        ),
        logging.StreamHandler()
    ]
)

# Silence noisy loggers
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

# Initialize Client
# A stale session file (old bot token / api id kept from a previous boot)
# would silently shadow the current Config credentials - drop it so every
# start signs in fresh with the values from .env. Retry a few times because
# a still-running bot instance can hold the file for a moment.
try:
    import glob as _glob
    import time as _time

    for _attempt in range(3):
        _left = _glob.glob(f"{SESSION_NAME}.session*")
        if not _left:
            break
        for _stale in _left:
            try:
                os.remove(_stale)
            except OSError as _err:
                LOGGER.warning(f"[Boot] Could not delete stale session {_stale}: {_err}")
        if _attempt < 2:
            _time.sleep(0.5)
    _still = _glob.glob(f"{SESSION_NAME}.session*")
    if _still:
        LOGGER.warning(
            f"[Boot] Stale session still present ({', '.join(_still)}) - "
            "another bot instance may be running with this session."
        )
except Exception:
    pass

app = Client(
    SESSION_NAME,
    bot_token=TG_BOT_TOKEN,
    api_id=APP_ID,
    api_hash=API_HASH,
    workers=32
)
