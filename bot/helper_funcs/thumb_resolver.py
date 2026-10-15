# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Per-task thumbnail resolution for the -t / -tl flags (NexonBots parity).

Deliberately light on imports: heavy bot helpers are imported lazily inside
the functions so this module can be pulled in by split_uploader without
creating an import cycle.
"""
import os
import re
import time
import asyncio
import logging

import aiohttp
from PIL import Image

LOGGER = logging.getLogger("ThumbFlag")

TG_LINK_RE = re.compile(
    r"(?:https?://)?t\.me/(?:(?P<peer>c/(?P<cpeer>\d+))|(?P<user>[A-Za-z0-9_]+))/(?P<msg>\d+)",
    re.I,
)
TG_OPEN_RE = re.compile(
    r"tg://openmessage\?(?:.*?user_id=(?P<user_id>\d+))?(?:.*?chat_id=(?P<chat_id>-?\d+))?"
    r"(?:.*?message_id=(?P<msg>\d+))",
    re.I,
)
LAYOUT_RE = re.compile(r"(\d+)\D+(\d+)")


async def _resize_thumb(path):
    """320x174 JPEG like utils.process_thumbnail (lazy import, no cycle)."""
    try:
        from bot.helper_funcs.utils import process_thumbnail
        return await process_thumbnail(path)
    except Exception as e:
        LOGGER.warning(f"[ThumbFlag] resize failed: {e}")
        return path if os.path.exists(path) else None


async def resolve_thumb_flag(client, value):
    """
    NexonBots -t: image URL | telegram message link (photo/document) | none | path.
    Returns (thumb_path|None, skip_auto: bool, error: str|None).
    skip_auto=True means "-t none" -> upload without any thumbnail.
    """
    if value in (None, False) or value is True:
        return None, False, None
    v = str(value).strip()
    if not v:
        return None, False, None
    if v.lower() == "none":
        return None, True, None

    stamp = int(time.time())
    tmp = os.path.join(os.getcwd(), f"thumbflag_{stamp}.jpg")

    m = TG_LINK_RE.search(v)
    if not m:
        m2 = TG_OPEN_RE.search(v)
        if m2:
            chat = m2.group("chat_id") or m2.group("user_id")
            msg_id = m2.group("msg")
            m = ("open", chat, msg_id)
    else:
        if m.group("cpeer"):
            chat = "-100" + m.group("cpeer")
        else:
            chat = m.group("user")
        m = ("link", chat, m.group("msg"))

    if m:
        kind, chat, msg_id = m
        try:
            chat_id = int(chat) if str(chat).lstrip("-").isdigit() else chat
            msg = await client.get_messages(chat_id, ids=int(msg_id))
            media = getattr(msg, "photo", None) or getattr(msg, "document", None)
            if not media:
                return None, False, "no photo/document found in the TG link"
            mime = (getattr(media, "mime_type", "") or "").lower()
            if getattr(media, "file_name", None) and not mime.startswith("image/"):
                return None, False, "file in the TG link is not an image"
            path = await client.download_media(media, file_name=tmp)
            if not path:
                return None, False, "thumbnail download fail"
            return (await _resize_thumb(path)) or path, False, None
        except Exception as e:
            return None, False, f"TG thumbnail fail: {e}"

    if v.startswith(("http://", "https://")):
        try:
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=30)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(v, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return None, False, f"thumbnail HTTP {resp.status}"
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    if "image" not in ctype:
                        return None, False, "URL is not an image"
                    data = await resp.read()
            if not data:
                return None, False, "thumbnail empty"
            with open(tmp, "wb") as fh:
                fh.write(data)
            return (await _resize_thumb(tmp)) or tmp, False, None
        except Exception as e:
            return None, False, f"thumbnail download fail: {e}"

    if os.path.isfile(v):
        return (await _resize_thumb(v)) or v, False, None

    return None, False, f"could not understand thumbnail '{v}'"


def _parse_layout(value):
    """'3x3' / '3*3' / '3 3' -> (rows, cols) or None."""
    s = re.sub(r"(\d+)\D+(\d+)", r"\1x\2", str(value or "").strip().lower())
    m = re.fullmatch(r"(\d+)x(\d+)", s)
    if not m:
        return None
    rows, cols = int(m.group(1)), int(m.group(2))
    if rows < 1 or cols < 1 or rows > 6 or cols > 6 or rows * cols > 25:
        return None
    return rows, cols


async def build_tile_thumb(video_path, layout, out_path=None):
    """NexonBots -tl: tile evenly spaced frames into one thumbnail image."""
    dims = _parse_layout(layout)
    if not dims:
        LOGGER.warning(f"[ThumbFlag] bad layout: {layout}")
        return None
    rows, cols = dims
    if not os.path.isfile(video_path):
        return None
    try:
        from bot.helper_funcs.split_uploader import get_video_duration
        from bot.screenshot import equal_timestamps
    except Exception as e:
        LOGGER.warning(f"[ThumbFlag] imports failed: {e}")
        return None

    dur = get_video_duration(video_path)
    if not dur or dur < 1:
        return None
    count = rows * cols
    ts = equal_timestamps(dur, count)
    if not ts:
        return None

    work = os.path.join(os.path.dirname(video_path) or ".", f"tilethumb_{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    frames = []
    try:
        for i, t in enumerate(ts):
            fr = os.path.join(work, f"fr_{i:03d}.jpg")
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{t:.3f}", "-i", video_path,
                "-vframes", "1", "-q:v", "2", fr,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            if proc.returncode == 0 and os.path.exists(fr) and os.path.getsize(fr) > 0:
                frames.append(fr)
        if len(frames) < count:
            LOGGER.warning(f"[ThumbFlag] only {len(frames)}/{count} frames")
            if not frames:
                return None
        out = out_path or os.path.join(
            os.path.dirname(video_path) or ".",
            f"{os.path.splitext(os.path.basename(video_path))[0]}_tile.jpg",
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", "1", "-start_number", "0",
            "-i", os.path.join(work, "fr_%03d.jpg"),
            "-vf", f"tile={cols}x{rows}",
            "-frames:v", "1", "-q:v", "2", out,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        LOGGER.warning(
            f"[ThumbFlag] tile failed: {(stderr or b'').decode(errors='ignore')[-200:]}"
        )
        return None
    except Exception as e:
        LOGGER.warning(f"[ThumbFlag] build_tile_thumb: {e}")
        return None
    finally:
        try:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass
