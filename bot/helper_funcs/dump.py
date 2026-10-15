# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Optional dump channel: copy every finished upload into DUMP_CHANNEL.

Videos and files of any extension are copied (server side, no re-upload).
Photos / screenshots / thumbnails are intentionally skipped.
Failures are logged only - the user task never breaks because of the dump.
"""
import asyncio

from bot import LOGGER
from bot.config import Config
from pyrogram.errors import FloodWait


def dump_chat():
    """Dump chat id (int/@username) or None when DUMP_CHANNEL is empty."""
    raw = str(Config.DUMP_CHANNEL or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def is_dumpable(message) -> bool:
    """True for videos, audio and documents - never photos/thumbnails."""
    if message is None:
        return False
    return bool(
        getattr(message, "video", None)
        or getattr(message, "audio", None)
        or getattr(message, "document", None)
    )


async def dump_copy(client, sent) -> bool:
    """Copy an already-uploaded message into the dump channel. Never raises."""
    chat = dump_chat()
    if not chat or not is_dumpable(sent):
        return False
    src = getattr(sent, "chat", None)
    if src is None:
        return False
    for attempt in (1, 2):
        try:
            await client.copy_message(
                chat_id=chat,
                from_chat_id=src.id,
                message_id=sent.id,
            )
            return True
        except FloodWait as fw:
            if attempt == 2 or fw.value > 10:
                LOGGER.warning(f"[Dump] FloodWait {fw.value}s - copy skipped")
                return False
            await asyncio.sleep(fw.value + 1)
        except Exception as e:
            LOGGER.warning(f"[Dump] copy to {chat} failed: {e}")
            return False
    return False
