# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Native Telegram inline-button styling with project-wide semantic defaults."""

import re
import unicodedata

from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton as _InlineKeyboardButton


_DANGER = (
    "cancel", "delete", "close", "stop", "remove", "reject", "clear",
    "disable", "reset", "fuckoff", "fuckingdo",
)
_SUCCESS = (
    "confirm", "apply", "done", "save", "enable", "join", "check",
    "addaudio_done", "audio_", "set_", "toggle_",
)
_PRIMARY = (
    "download", "next", "continue", "start", "home", "open", "use",
    "compress", "crop", "merge", "split", "trim", "cut", "watermark",
    "144p", "240p", "360p", "480p", "720p", "1080p", "2160p",
)
_NEUTRAL = (
    "info", "about", "help", "back", "format", "codec", "settings",
    "tutorial", "creator", "support", "updates", "metadata", "shortener",
    "addaudio_more",
)


def _semantic_style(text, callback_data=None, url=None):
    """Choose a native style without altering the button payload or action."""
    value = " ".join(str(x or "") for x in (text, callback_data)).lower()
    value = unicodedata.normalize("NFKC", value)
    compact = re.sub(r"[^a-z0-9_]+", " ", value)
    words = set(compact.split())

    if any(word in compact for word in _DANGER) or any(mark in value for mark in ("❌", "✖", "⛔", "🚫")):
        return ButtonStyle.DANGER
    if "off" in words:
        return ButtonStyle.DANGER
    if any(word in compact for word in _NEUTRAL):
        return ButtonStyle.DEFAULT
    if any(word in compact for word in _SUCCESS):
        return ButtonStyle.SUCCESS
    if "on" in words:
        return ButtonStyle.SUCCESS
    if any(word in compact for word in _PRIMARY) or re.search(r"\b(?:all|yes)\b", compact):
        return ButtonStyle.PRIMARY
    # Plain URLs and utility selections remain client-native neutral.
    return ButtonStyle.DEFAULT


class InlineKeyboardButton(_InlineKeyboardButton):
    """Drop-in Pyrogram button that applies Telegram's native style field."""

    def __init__(self, text, *args, style=None, **kwargs):
        if style is None:
            style = _semantic_style(
                text,
                callback_data=kwargs.get("callback_data"),
                url=kwargs.get("url"),
            )
        super().__init__(text, *args, style=style, **kwargs)
