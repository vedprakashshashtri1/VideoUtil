#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# (c) Sujoy | @NexonBots

# the logging things
import logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import math
import os
import time
import json

from bot import DOWNLOAD_LOCATION


FINISHED_PROGRESS_STR = "⬢"
UN_FINISHED_PROGRESS_STR = "⬡"

_last_progress_edit = {}

async def progress_for_pyrogram(current, total, bot, ud_type, message, start):
    if total == 0:
        return  # Prevent division by zero

    now = time.time()
    diff = max(now - start, 0.001)

    msg_id = getattr(message, "id", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    key = (chat_id, msg_id)

    last_edit = _last_progress_edit.get(key, 0.0)
    # Strictly throttle edits to every 4.0s to avoid Telegram EditMessage FloodWait
    if current != total and (now - last_edit < 4.0):
        return
    if len(_last_progress_edit) > 500:
        _last_progress_edit.clear()
    _last_progress_edit[key] = now

    try:
        percentage = current * 100 / total
    except ZeroDivisionError:
        percentage = 0

    # Optional: check if user stopped via status.json
    status_path = os.path.join(DOWNLOAD_LOCATION, "status.json")
    if os.path.exists(status_path):
        try:
            with open(status_path) as f:
                status = json.load(f)
            if not status.get("running", True):
                return
        except Exception:
            pass  # fail silently

    speed = current / diff
    eta = round((total - current) / speed) * 1000 if speed > 0 else 0
    eta_str = TimeFormatter(milliseconds=eta)

    progress_bar = "<blockquote><code>[{0}{1}]</code>\n<b>ᴘʀᴏᴄᴇssɪɴɢ:</b> {2:.2f}%</blockquote>".format(
        FINISHED_PROGRESS_STR * math.floor(percentage / 10),
        UN_FINISHED_PROGRESS_STR * (10 - math.floor(percentage / 10)),
        percentage
    )

    details = "<blockquote>{} of {}\nSpeed: {}/s\nETA: {}</blockquote>".format(
        humanbytes(current),
        humanbytes(total),
        humanbytes(speed),
        eta_str
    )

    text = "{}\n {}".format(ud_type, progress_bar + details)

    try:
        if not getattr(message, "photo", False):
            await message.edit_text(text=text)
        else:
            await message.edit_caption(caption=text)
    except Exception:
        pass


_last_msg_edit_time = {}

async def safe_progress_edit(message, text, min_interval=4.5):
    """
    Safely edits a progress message, strictly throttling to at least min_interval seconds
    and catching FloodWait so video encoding/download/upload is NEVER stalled or frozen.
    """
    if not message or not text:
        return
    now = time.time()
    msg_id = getattr(message, "id", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    key = (chat_id, msg_id)

    if now - _last_msg_edit_time.get(key, 0.0) < min_interval:
        return
    if len(_last_msg_edit_time) > 500:
        _last_msg_edit_time.clear()
    _last_msg_edit_time[key] = now
    try:
        if not getattr(message, "photo", False):
            await message.edit_text(text)
        else:
            await message.edit_caption(caption=text)
    except Exception:
        pass


def humanbytes(size):
    # https://stackoverflow.com/a/49361727/4723940
    # 2**10 = 1024
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size >= power and n < 4:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "")
    return tmp[:-2] if tmp else "0s"


