# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import os
import tempfile

from bot.get_cfg import get_config


class Config(object):
    SESSION_NAME = get_config("SESSION_NAME", "AHCompressorBot")

    USER_SESSION_STRING = get_config(
        "USER_SESSION_STRING",
        ""
    )

    APP_ID = int(get_config("APP_ID", "0"))
    API_HASH = get_config("API_HASH", "")

    STRING_API_ID = int(get_config("STRING_API_ID", str(APP_ID)))
    STRING_API_HASH = get_config("STRING_API_HASH", API_HASH)
    SESSION_USER_ID = int(get_config("SESSION_USER_ID", "0"))

    LOG_CHANNEL = get_config("LOG_CHANNEL", "")
    # Optional: every finished upload (video/files) is copied here too.
    DUMP_CHANNEL = get_config("DUMP_CHANNEL", "")
    UPDATES_CHANNEL = get_config("UPDATES_CHANNEL", "NexonBots")  # Without @

    # Get these values from my.telegram.org
    AUTH_USERS = set(
        int(x)
        for x in get_config(
            "AUTH_USERS", ""
        ).split()
    )

    # Bot owner - auto-added to AUTH_USERS and used for owner-only Drive controls
    OWNER_ID = int(get_config("OWNER_ID", "0"))

    # Google Drive OAuth (Desktop app client). Set real values in .env only.
    GDRIVE_CLIENT_ID = get_config("GDRIVE_CLIENT_ID", "")
    GDRIVE_CLIENT_SECRET = get_config("GDRIVE_CLIENT_SECRET", "")
    GDRIVE_PROJECT_ID = get_config("GDRIVE_PROJECT_ID", "")

    # Loopback OAuth callback - the bot listens here so no code pasting is needed
    GDRIVE_REDIRECT_URI = get_config(
        "GDRIVE_REDIRECT_URI", "http://localhost:8080/oauth2callback"
    )

    # Public index page in front of the owner's Drive folder (mirror links)
    INDEX_URL = get_config("INDEX_URL", "")

    # Milestone 2: folder that receives Drive uploads + its path inside the index
    GDRIVE_UPLOAD_FOLDER = get_config("GDRIVE_UPLOAD_FOLDER", "")
    GDRIVE_INDEX_PREFIX = get_config("GDRIVE_INDEX_PREFIX", "")

    # Auto-delete non-owner Drive uploads after N days (0 = keep forever).
    # Owner uploads are never tagged, so they are never touched.
    GDRIVE_UPLOAD_TTL_DAYS = int(get_config("GDRIVE_UPLOAD_TTL_DAYS", "3"))

    DB_NAME = get_config("DB_NAME", "enc")

    DB_URL = get_config("DB_URL", "")

    # Git auto-update for /update command.
    # UPSTREAM_REPO: repo to pull from (falls back to origin when empty).
    # GIT_TOKEN:     PAT — needed for private repos (avoids SSH host-key errors).
    UPSTREAM_REPO = get_config("UPSTREAM_REPO", "")
    GIT_TOKEN = get_config("GIT_TOKEN", "")


    TG_BOT_TOKEN = get_config(
        "TG_BOT_TOKEN",
        ""
    )
    BOT_USERNAME = get_config("BOT_USERNAME", "").lstrip("@")

    PICS = get_config(
        "PICS",
        """
https://i.ibb.co/wrdKRrzs/x.jpg
https://i.ibb.co/chmRfd5b/x.jpg
"""
    ).split()

    # OUT OF YOUR LEAGUE | DON'T TOUCH THIS PART
    WORK_DIR = get_config(
        "WORK_DIR", os.path.join(tempfile.gettempdir(), "video-util")
    )
    DOWNLOAD_LOCATION = get_config("DOWNLOAD_LOCATION", os.path.join(WORK_DIR, "downloads"))
    DOWNLOAD_LOCATION1 = get_config("DOWNLOAD_LOCATION1", os.path.join(WORK_DIR, "1"))
    DOWNLOAD_LOCATION2 = get_config("DOWNLOAD_LOCATION2", os.path.join(WORK_DIR, "2"))
    DOWNLOAD_LOCATION3 = get_config("DOWNLOAD_LOCATION3", os.path.join(WORK_DIR, "3"))
    DOWNLOAD_LOCATION4 = get_config("DOWNLOAD_LOCATION4", os.path.join(WORK_DIR, "4"))
    DOWNLOAD_LOCATION5 = get_config("DOWNLOAD_LOCATION5", os.path.join(WORK_DIR, "5"))
    DOWNLOAD_LOCATION6 = get_config("DOWNLOAD_LOCATION6", os.path.join(WORK_DIR, "6"))
    DOWNLOAD_LOCATION7 = get_config("DOWNLOAD_LOCATION7", os.path.join(WORK_DIR, "7"))
    CROP_LOCATION = get_config("CROP_LOCATION", os.path.join(WORK_DIR, "crop"))
    HSUB_LOCATION = get_config("HSUB_LOCATION", os.path.join(WORK_DIR, "hsub"))
    MERGE_LOCATION = get_config("MERGE_LOCATION", os.path.join(WORK_DIR, "merge"))
    LEECH_LOCATION = get_config("LEECH_LOCATION", os.path.join(WORK_DIR, "leech"))


