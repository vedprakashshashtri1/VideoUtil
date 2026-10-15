# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import logging
import asyncio
import os
import time
import re
import json, shutil
import subprocess
import math
from PIL import Image, ImageOps
import aiofiles
import mimetypes
from pathlib import Path
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton
from bot.helper_funcs.display_progress import TimeFormatter
#from bot.helper_funcs.utils import convert_to_mkv
from bot.localisation import Localisation
from bot import (
    FINISHED_PROGRESS_STR,
    UN_FINISHED_PROGRESS_STR,
    DOWNLOAD_LOCATION,
    crf,
    resolution,
    audio_b,
    preset,
    codec,
    pid_list
)

logging.basicConfig(
    level=logging.WARNING, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)

#--------------------HELPER---------------------#

async def convert_to_mkv(input_path, output_path):
    """Convert video file to MKV format (exclude unsupported streams)"""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found in PATH")

    cmd = [
        ffmpeg,
        '-hide_banner',
        '-i', input_path,
        '-map', '0:v?',  # video
        '-map', '0:a?',  # audio
        '-map', '0:s?',  # subtitles 
        '-c', 'copy',
        '-f', 'matroska',
        '-y',
        output_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        raise RuntimeError(f"MKV conversion failed: {error_msg}")

    return output_path


# --- Sanitize Filename ---
def sanitize_filename(filename):
    filename = re.sub(r'^https?://\S+\s*', '', filename)
    filename = re.sub(r'[<>:"/\\|?\'’]', '', filename)
    filename = re.sub(r'[.+]', ' ', filename)  # Normalize dots and plus signs
    filename = re.sub(r'\s+', ' ', filename)
    filename = re.sub(r'[-]{2,}', '_', filename)
    filename = re.sub(r'\s-\s*', ' - ', filename)
    filename = re.sub(r'\s{2,}', ' ', filename)
    return filename.strip(' .-_')

# --- Fix Metadata and Remux ---
async def fix_metadata_and_remux(input_path):
    dirname = os.path.dirname(input_path)
    raw_name = os.path.basename(input_path)
    safe_name = sanitize_filename(raw_name)
    safe_path = os.path.join(dirname, safe_name)

    if input_path != safe_path:
        os.rename(input_path, safe_path)
        input_path = safe_path

    cleaned_path = os.path.splitext(input_path)[0] + "_cleaned.mkv"
    # SECURITY: argv list instead of a shell string (filename/shell metacharacter injection)
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-i', input_path,
        '-map', '0', '-c', 'copy',
        cleaned_path, '-y',
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"Metadata remux failed: {stderr.decode(errors='replace').strip()}")

    # SECURITY: only consume the input once the cleaned output actually exists
    os.remove(input_path)
    final_path = cleaned_path.replace("_cleaned", "")
    os.rename(cleaned_path, final_path)
    return final_path

async def media_info(saved_file_path):
    process = await asyncio.create_subprocess_exec(
        'ffmpeg', 
        "-hide_banner", 
        '-i', 
        saved_file_path,
        stdout=asyncio.subprocess.PIPE, 
        stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await process.communicate()
    output = stdout.decode().strip()
    duration = re.search("Duration:\s*(\d*):(\d*):(\d+\.?\d*)[\s\w*$]", output)
    bitrates = re.search("bitrate:\s*(\d+)[\s\w*$]", output)

    if duration is not None:
        hours = int(duration.group(1))
        minutes = int(duration.group(2))
        seconds = math.floor(float(duration.group(3)))
        total_seconds = (hours * 60 * 60) + (minutes * 60) + seconds
    else:
        total_seconds = None

    if bitrates is not None:
        bitrate = bitrates.group(1)
    else:
        bitrate = None

    return total_seconds, bitrate

#--------------------HELPER---------------------#

async def take_screen_shot(video_file, output_directory, ttl):
    out_put_file_name = os.path.join(
        output_directory,
        str(time.time()) + ".jpg"
    )
    if video_file.upper().endswith(("MKV", "MP4", "WEBM")):
        file_genertor_command = [
            "ffmpeg",
            "-ss",
            str(ttl),
            "-i",
            video_file,
            "-vframes",
            "1",
            out_put_file_name
        ]

        process = await asyncio.create_subprocess_exec(
            *file_genertor_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        e_response = stderr.decode().strip()
        t_response = stdout.decode().strip()

    if os.path.lexists(out_put_file_name):
        return out_put_file_name
    else:
        return None

def get_width_height(video_file):
    metadata = extractMetadata(createParser(video_file))
    if metadata.has("width") and metadata.has("height"):
        return metadata.get("width"), metadata.get("height")
    else:
        return 1280, 720

#------------------------------------------#
