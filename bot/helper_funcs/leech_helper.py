# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import asyncio
import os
import math
import time
import shutil
import re
import logging
import aiohttp
import bencodepy
from bot.helper_funcs.utils import safe_media_name
from urllib.parse import unquote, urlparse, parse_qs
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, mkdir
from aiohttp import ClientSession
from torrentp import TorrentDownloader
from json import loads as jloads
from feedparser import parse as feedparse
from datetime import datetime
from PIL import Image
from traceback import format_exc
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton




# ==============================
# LOGGER SETUP
# ==============================
LOGS = logging.getLogger("Torrent")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def _patch_torrentp_blocking_status():
    """torrentp's Downloader.status() waits for magnet metadata inside a
    sleeping while-loop. Called from async code that freezes the whole event
    loop - the bot stops answering any command until metadata arrives, which
    never happens for a dead magnet. Replace it with a non-blocking version;
    torrentp's async download loop keeps polling instead."""
    try:
        from torrentp.downloader import Downloader as _TpDownloader
    except Exception:
        return
    if getattr(_TpDownloader, "_vutil_nonblock", False):
        return

    def status(self):
        if self._file is None:
            self._file = self._session.add_torrent(self._build_add_torrent_params())
            if not self._is_magnet:
                LOGS.info(f"Torrent added: {self._file.status().name}")
            else:
                LOGS.info("Magnet added - waiting for metadata in background.")
        self._status = self._file.status()
        return self._status

    _TpDownloader.status = status
    _TpDownloader._vutil_nonblock = True


_patch_torrentp_blocking_status()

# ==================== MEGA DOWNLOADER ====================
async def mega_coroutine(url, dir="Downloads"):
    e = "h"
    try:
        if not os.path.exists(dir):
            os.makedirs(dir)
        
        cmds = (
            "megatools", "dl",
            "--path", dir,
            url,
            "--limit-speed", "0",
            "--no-progress",
            "--no-ask-password"
        )
        
        process = await asyncio.create_subprocess_exec(
            *cmds,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        e = stderr.decode() or stdout.decode()
    except Exception as err:
        e = str(err)
    return e, dir


def get_file_list(dir):
    files = []
    if os.path.exists(dir):
        for root, _, filenames in os.walk(dir):
            for filename in filenames:
                files.append(os.path.join(root, filename))
    return files

# ==============================
# HELPERS
# ==============================
def humanbytes(size: int) -> str:
    """
    Convert bytes to a human-readable format (e.g. 10.5 MB, 2.3 GB).
    """
    if not size:
        return "0 B"

    power = 1024
    n = 0
    power_labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size >= power and n < 4:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"


def extract_title_from_magnet(magnet_link):
    """
    Extract the display name (dn) from a magnet link.
    """
    try:
        qs = parse_qs(urlparse(magnet_link).query)
        return unquote(qs.get("dn", ["Magnet Task"])[0])
    except Exception:
        return "Magnet Task"


async def extract_title_from_torrent(url):
    """
    Extract torrent title directly from its .torrent file.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    info = bencodepy.decode(data)[b'info']
                    return info[b'name'].decode()
    except Exception as e:
        LOGS.error(f"Failed to parse torrent: {e}")
    return "Torrent Task"


# ====================
# NexonBots STYLE INPUT CLASSIFICATION
# ====================
STREAMING_HOSTS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com", "instagram.com",
    "facebook.com", "fb.watch", "twitter.com", "x.com", "tiktok.com",
    "reddit.com", "vimeo.com", "dailymotion.com", "twitch.tv",
    "spotify.com", "soundcloud.com", "tumblr.com", "snapchat.com",
    "pinterest.com", "pin.it", "threads.net",
)

# Google Drive file/folder links - leechable (public, or private via connect)
DRIVE_HOSTS = ("drive.google.com", "docs.google.com", "drive.usercontent.google.com")

MAGNET_RE = re.compile(
    r"^magnet:\?.*xt=urn:(btih|btmh):([a-zA-Z0-9]{32,40}|[a-z2-7]{32}).*"
)


def _host_matches(host: str, domain: str) -> bool:
    host = (host or "").lower().rstrip(".")
    domain = domain.lower()
    return host == domain or host.endswith("." + domain)


def is_torrent_url(url: str) -> bool:
    """True when the URL path (query stripped) points at a .torrent file."""
    try:
        return urlparse(url).path.lower().endswith(".torrent")
    except Exception:
        return False


def classify_leech_input(value: str) -> str:
    """
    Decide what a /leech argument actually is (NexonBots style validation).
    Returns: magnet | torrent_url | torrent_file | http | ftp | mega |
             gdrive | local | streaming | invalid
    """
    v = (value or "").strip()
    if not v:
        return "invalid"

    low = v.lower()
    if low.startswith("magnet:"):
        return "magnet" if MAGNET_RE.match(v) else "invalid"

    if low.startswith(("http://", "https://")):
        try:
            host = urlparse(v).hostname or ""
        except Exception:
            return "invalid"
        if any(_host_matches(host, d) for d in DRIVE_HOSTS):
            return "gdrive"
        if any(_host_matches(host, d) for d in STREAMING_HOSTS):
            return "streaming"
        if any(_host_matches(host, d) for d in ("mega.nz", "mega.co.nz")):
            return "mega"
        return "torrent_url" if is_torrent_url(v) else "http"

    if low.startswith("ftp://"):
        return "ftp"

    if os.path.isfile(v):
        return "torrent_file" if v.lower().endswith(".torrent") else "local"

    return "invalid"


def _filename_from_response(resp, url: str) -> str:
    """Safe local filename from Content-Disposition, falling back to the URL path."""
    cd = resp.headers.get("Content-Disposition") or ""
    raw = ""
    m = re.search(r"filename\*\s*=\s*UTF-8''([^;\"]+)", cd, re.I)
    if not m:
        m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I)
    if not m:
        m = re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    if m:
        raw = unquote(m.group(1).strip().strip('"'))
    if not raw:
        try:
            raw = unquote(urlparse(url).path.rsplit("/", 1)[-1] or "")
        except Exception:
            raw = ""
    # SECURITY: filename comes from an untrusted server - strip any path component
    return safe_media_name(raw) or f"file_{int(time.time())}"


async def http_download(
    url: str,
    dest_dir: str,
    progress_cb=None,
    should_stop=None,
    connect_timeout: int = 60,
    headers: dict = None,
    auth=None,
):
    """
    Stream a direct HTTP/HTTPS link into dest_dir (NexonBots direct-leech parity).
    Returns the local path, or None when cancelled. Raises on HTTP errors and
    on HTML pages (link is not a direct file).
    progress_cb: optional async fn(pct, done, total, speed)
    should_stop: optional callable returning True to cancel
    headers: optional extra headers from the -h flag (override the default UA)
    auth: optional aiohttp.BasicAuth from the -au/-ap flags
    """
    os.makedirs(dest_dir, exist_ok=True)
    timeout_cfg = aiohttp.ClientTimeout(
        total=None, sock_connect=connect_timeout, sock_read=connect_timeout
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VideoUtil/Leech",
        **(headers or {}),
    }

    last_time = time.time()
    last_done = 0.0
    speed = 0.0

    async with aiohttp.ClientSession(timeout=timeout_cfg, headers=headers) as session:
        async with session.get(url, allow_redirects=True, auth=auth) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} while fetching link")

            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype in ("text/html", "application/xhtml+xml"):
                raise RuntimeError(
                    "Link returns an HTML page - it is not a direct file link."
                )

            total = float(resp.headers.get("Content-Length") or 0)
            dest = os.path.join(dest_dir, _filename_from_response(resp, url))
            done = 0.0
            cancelled = False

            async with aiopen(dest, "wb") as fh:
                async for chunk in resp.content.iter_chunked(1 << 16):
                    if should_stop and should_stop():
                        cancelled = True
                        break
                    await fh.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last_time >= 2:
                        speed = (done - last_done) / (now - last_time)
                        last_time = now
                        last_done = done
                        if progress_cb and total > 0:
                            await progress_cb(
                                pct=done * 100.0 / total,
                                done=done,
                                total=total,
                                speed=speed,
                            )

            if cancelled:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                LOGS.info("[HTTP] Download cancelled")
                return None

            if total <= 0:
                total = done
            if progress_cb:
                await progress_cb(pct=100.0, done=done, total=total, speed=speed)

            LOGS.info(f"[HTTP] Download complete \u2014 {dest} ({humanbytes(done)})")
            return dest



# ==============================
# TORRENT DOWNLOADER CLASS
# ==============================
class TorDownloader:
    def __init__(self, path=".", max_retries=3, retry_delay=10, metadata_timeout=180):
        self.__downdir = path
        self.__torpath = os.path.join(path, "torrents")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.metadata_timeout = metadata_timeout
        self.last_error = ""

        # Ensure directories exist
        os.makedirs(self.__downdir, exist_ok=True)
        os.makedirs(self.__torpath, exist_ok=True)

    async def download(self, torrent, name=None, progress_cb=None, should_stop=None):
        """
        Download torrent (magnet or .torrent link).
        Retries automatically on failure.
        progress_cb: optional async fn(pct, done, total, speed, seeders, peers)
        should_stop: optional callable returning True to cancel the download
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                LOGS.info(f"[TorDownloader] Attempt {attempt}/{self.max_retries} \u2014 {torrent}")

                if torrent.startswith("magnet:"):
                    torfile = None
                    torp = TorrentDownloader(torrent, self.__downdir)
                else:
                    # A local .torrent file is used as-is (it is not an HTTP URL)
                    if os.path.isfile(torrent) and torrent.lower().endswith(".torrent"):
                        torfile = torrent
                    else:
                        torfile = await self.get_torfile(torrent)
                    if not torfile:
                        raise Exception("Failed to fetch .torrent file")
                    torp = TorrentDownloader(torfile, self.__downdir)

                dl_task = asyncio.create_task(torp.start_download())

                cancelled = False
                meta_timeout = False
                got_metadata = False
                meta_started = time.time()
                try:
                    while not dl_task.done():
                        if should_stop and should_stop():
                            cancelled = True
                            break
                        try:
                            downloader = getattr(torp, "_downloader", None)
                            handle = getattr(downloader, "_file", None)
                            if handle is not None:
                                st = handle.status()
                                total = float(getattr(st, "total_wanted", 0) or 0)
                                done = float(getattr(st, "total_done", 0) or 0)
                                speed = float(getattr(st, "download_rate", 0) or 0)
                                seeders = int(getattr(st, "num_seeds", 0) or 0)
                                peers = int(getattr(st, "num_peers", 0) or 0)
                                if total > 0:
                                    got_metadata = True
                                pct = (done * 100.0 / total) if total > 0 else 0.0
                                if progress_cb:
                                    await progress_cb(
                                        pct=pct, done=done, total=total,
                                        speed=speed, seeders=seeders, peers=peers,
                                    )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                        if not got_metadata and time.time() - meta_started > self.metadata_timeout:
                            meta_timeout = True
                            break
                        await asyncio.sleep(2)
                except asyncio.CancelledError:
                    try:
                        dl_task.cancel()
                    except Exception:
                        pass
                    raise

                if meta_timeout:
                    try:
                        torp.stop_download()
                    except Exception:
                        pass
                    dl_task.cancel()
                    await asyncio.wait({dl_task}, timeout=5)
                    self.last_error = (
                        f"No torrent metadata within {self.metadata_timeout}s "
                        "- no peers/trackers have this file (dead magnet)."
                    )
                    LOGS.error(f"[TorDownloader] {self.last_error}")
                    return None

                if cancelled:
                    try:
                        torp.stop_download()
                    except Exception:
                        pass
                    dl_task.cancel()
                    await asyncio.wait({dl_task}, timeout=5)
                    LOGS.info("[TorDownloader] Download cancelled")
                    return None

                await dl_task

                if torfile:
                    try:
                        await aioremove(torfile)
                    except Exception:
                        pass

                # On-disk name comes from torrent METADATA; a magnet's dn= is
                # only a display name and often differs (spaced title vs dotted
                # filename). Resolve what the engine actually wrote, then validate.
                dl_path = await self._resolve_download_path(torp, torrent, name)
                if not dl_path:
                    raise Exception("Downloaded file/folder invalid or empty")

                LOGS.info(f"[TorDownloader] Download complete — {dl_path}")
                return dl_path

            except Exception as e:
                LOGS.error(f"[TorDownloader] Error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    LOGS.info(f"[TorDownloader] Retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    LOGS.error("[TorDownloader] Max retries reached, download failed.")
                    self.last_error = f"Download failed after {self.max_retries} attempts."
                    return None

    async def get_torfile(self, url):
        """
        Download .torrent file from URL and return its local path.
        """
        if not os.path.isdir(self.__torpath):
            await mkdir(self.__torpath)

        # SECURITY: filename taken from an untrusted URL - strip any path component
        tor_name = safe_media_name(unquote(url.split("/")[-1]) or "download.torrent")
        des_dir = os.path.join(self.__torpath, tor_name)

        try:
            async with ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        async with aiopen(des_dir, "wb") as file:
                            async for chunk in response.content.iter_any():
                                await file.write(chunk)
                        LOGS.info(f"[TorDownloader] Torrent file downloaded → {des_dir}")
                        return des_dir
                    else:
                        LOGS.error(f"[TorDownloader] HTTP {response.status} while fetching torrent file.")
        except Exception as e:
            LOGS.error(f"[TorDownloader] Failed to fetch torrent file: {e}")
        return None

    async def _validate_download(self, path):
        """
        Validate whether a torrent download was successful.
        """
        if not os.path.exists(path):
            return False

        # Folder (multi-file torrent)
        if os.path.isdir(path):
            def _has_files(p):
                for root, _, files in os.walk(p):
                    if files:
                        return True
                return False
            return await asyncio.to_thread(_has_files, path)

        # File (single torrent)
        return os.path.getsize(path) > 0

    async def _resolve_download_path(self, torp, torrent, name=None):
        """Real path of a finished download.

        Order: engine metadata name (exact, traversal-guarded) > sanitized
        metadata name > magnet dn / torrent title > directory scan.
        Returns None when nothing non-empty can be found.
        """
        candidates = []

        real = ""
        try:
            dler = getattr(torp, "_downloader", None)
            if dler is not None:
                real = str(dler.name or "").strip()
        except Exception:
            real = ""
        if real:
            base = os.path.basename(real.replace("\\", "/").rstrip("/"))
            if base:
                root = os.path.realpath(self.__downdir)
                raw = os.path.realpath(os.path.join(self.__downdir, base))
                # SECURITY: metadata name is attacker-controlled - never escape dir
                if raw.startswith(root + os.sep):
                    candidates.append(os.path.join(self.__downdir, base))
                candidates.append(os.path.join(self.__downdir, safe_media_name(base)))

        if torrent.startswith("magnet:"):
            candidates.append(os.path.join(
                self.__downdir,
                safe_media_name(name or extract_title_from_magnet(torrent)),
            ))
        else:
            try:
                candidates.append(os.path.join(
                    self.__downdir,
                    safe_media_name(torp._torrent_info._info.name()),
                ))
            except Exception:
                pass

        seen = set()
        for cand in candidates:
            if cand and cand not in seen:
                seen.add(cand)
                if await self._validate_download(cand):
                    return cand

        # Last resort: whatever the engine wrote into this fresh task dir.
        for entry in self._scan_download_dir():
            if await self._validate_download(entry):
                LOGS.warning(f"[TorDownloader] Resolved download by directory scan: {entry}")
                return entry
        return None

    def _scan_download_dir(self):
        """Entries of the task dir (excluding the .torrent cache), newest first."""
        try:
            names = [n for n in os.listdir(self.__downdir) if n != "torrents"]
        except OSError:
            return []
        entries = [os.path.join(self.__downdir, n) for n in names]

        def _mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0.0

        entries.sort(key=_mtime, reverse=True)
        return entries
