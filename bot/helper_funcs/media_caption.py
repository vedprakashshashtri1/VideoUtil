# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Consistent, compact captions for processed Telegram media uploads."""

import html
import json
import os
import re
import subprocess
from pathlib import Path

from bot.config import Config


def _probe(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_streams", "-show_format",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def _file_size(path):
    try:
        size = float(os.path.getsize(path))
    except OSError:
        return "Unknown"
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"


def _duration(seconds):
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "Unknown"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return ", ".join(parts)


def _codec_name(codec):
    names = {
        "h264": "H.264", "avc": "H.264", "avc1": "H.264", "x264": "H.264",
        "hevc": "H.265", "h265": "H.265", "x265": "H.265",
        "av1": "AV1", "vp9": "VP9", "vp8": "VP8", "mpeg4": "MPEG-4",
        "aac": "AAC", "mp3": "MP3", "opus": "Opus", "vorbis": "Vorbis",
        "flac": "FLAC", "ac3": "AC-3", "eac3": "E-AC-3",
    }
    value = str(codec or "unknown").lower()
    return names.get(value, value.upper())


def _timing_emoji(label):
    clean = re.sub(r"^[^\w\s]+", "", str(label or "")).strip().lower()
    if "download" in clean:
        return "📥"
    if "compress" in clean:
        return "⚡"
    if "trim" in clean or "cut" in clean:
        return "✂️"
    if "sub" in clean:
        return "💬"
    if "watermark" in clean:
        return "🏷️"
    if "merge" in clean:
        return "🧩"
    if "crop" in clean:
        return "📐"
    if "audio" in clean:
        return "🎵"
    if "process" in clean:
        return "⚙️"
    return "⏱️"


def build_media_caption(file_path, timings=None, delivery="document", file_name=None):
    """Return an HTML caption with media facts, timings and dynamic bot credit."""
    path = Path(file_path)
    data = _probe(path)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    stream = video or audio or {}

    width = video.get("width") if video else None
    height = video.get("height") if video else None
    quality = f"{height}P ({width}×{height})" if width and height else "Audio Only" if audio else "Unknown"
    duration = data.get("format", {}).get("duration") or stream.get("duration")
    extension = path.suffix.lstrip(".").upper() or "Unknown"
    delivery_names = {
        "video": "🎬 Streaming Video",
        "audio": "🎵 Audio",
        "document": "📄 Document",
    }
    delivery_name = delivery_names.get(str(delivery).lower(), str(delivery))
    shown_name = html.escape(file_name or path.name)
    live_username = None
    try:
        from bot import app
        live_username = getattr(getattr(app, "me", None), "username", None)
    except (ImportError, AttributeError):
        pass
    username = html.escape((live_username or Config.BOT_USERNAME or "VideoUtils1Bot").lstrip("@"))
    updates = html.escape((Config.UPDATES_CHANNEL or "NexonBots").lstrip("@"))

    media_lines = [
        "╭── <b>MEDIA DETAILS</b>",
        f"│ 📺 <b>Quality:</b> <code>{quality}</code>",
        f"│ 💿 <b>Codec:</b> <code>{_codec_name(stream.get('codec_name'))}</code>  <b>Ext:</b> <code>{extension}</code>",
        f"│ 📦 <b>File Size:</b> <code>{_file_size(path)}</code>",
        f"│ ⏱️ <b>Duration:</b> <code>{_duration(duration)}</code>",
        f"│ 📤 <b>Delivery:</b> <code>{delivery_name}</code>",
    ]
    if timings:
        for raw_label, raw_value in timings:
            clean_label = re.sub(r"^[^\w\s]+", "", str(raw_label)).strip()
            emoji = _timing_emoji(clean_label)
            val = html.escape(str(raw_value).strip())
            media_lines.append(f"│ {emoji} <b>{html.escape(clean_label)}:</b> <code>{val}</code>")
    media_lines.append("╰────────────────────")

    lines = [
        f"<b>{shown_name}</b>",
        "",
        "\n".join(media_lines),
        "",
        f"<b>ENCODED BY</b> - @{username}",
        f"<b>BOT BY</b> - @{updates}",
    ]
    return "\n".join(lines)


def enhance_media_caption(file_path, legacy_caption="", delivery="document", file_name=None):
    """Upgrade an existing result caption while retaining its timing rows.

    file_name overrides the title (split parts pass their real on-disk name so
    the caption never shows a stale pre-split name).
    """
    timings = []
    legacy_name = None
    blocks = re.findall(r"<blockquote[^>]*>(.*?)</blockquote>", legacy_caption or "", re.I | re.S)
    if blocks:
        candidate = re.sub(r"<[^>]+>", "", blocks[0]).strip()
        if "MEDIA DETAILS" not in candidate and candidate:
            legacy_name = candidate
    elif legacy_caption:
        first_line = re.sub(r"<[^>]+>", "", legacy_caption.splitlines()[0]).strip()
        if first_line and "MEDIA DETAILS" not in first_line:
            legacy_name = first_line

    for block in (blocks[1:] if len(blocks) > 1 else blocks):
        plain = re.sub(r"<[^>]+>", "", block)
        for line in plain.splitlines():
            line = line.strip().lstrip("│").strip()
            if ":" in line:
                label, value = line.split(":", 1)
                clean_label = re.sub(r"^[^\w\s]+", "", label).strip()
                if clean_label.lower() in ("quality", "codec", "ext", "file size", "duration", "delivery"):
                    continue
                if clean_label and value.strip() and not any(t[0].lower() == clean_label.lower() for t in timings):
                    timings.append((clean_label, value.strip()))

    if not timings and legacy_caption:
        for line in legacy_caption.splitlines():
            plain = re.sub(r"<[^>]+>", "", line).strip().lstrip("│").strip()
            if ":" in plain:
                label, value = plain.split(":", 1)
                clean_label = re.sub(r"^[^\w\s]+", "", label).strip()
                for key in ("download", "compress", "trim", "cut", "sub", "watermark", "process", "merge", "crop"):
                    if key in clean_label.lower():
                        if not any(t[0].lower() == clean_label.lower() for t in timings):
                            timings.append((clean_label, value.strip()))
                        break

    return build_media_caption(
        file_path,
        timings=timings,
        delivery=delivery,
        file_name=file_name if file_name is not None else legacy_name,
    )
