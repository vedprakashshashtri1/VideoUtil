# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Google Drive OAuth (auto-confirm loopback flow) + Drive link downloads."""

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import secrets
import time
from html import unescape as html_unescape
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import aiohttp
from aiofiles import open as aiofiles_open
from aiohttp import web

from bot.config import Config

LOGS = logging.getLogger("GDrive")

SCOPES = "https://www.googleapis.com/auth/drive"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VideoUtil/Drive"
CONNECT_TTL = 900  # an Authorize link stays valid for 15 minutes

# Python's built-in mimetypes has no .mkv (and Linux containers may lack it in
# /etc/mime.types) - extension fallback so Type: never shows octet-stream for
# common media.
_EXT_MIME = {
    ".mkv": "video/x-matroska",
    ".mk3d": "video/x-matroska-3d",
    ".mka": "audio/x-matroska",
    ".mp4": "video/mp4",
    ".m4v": "video/x-m4v",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".flv": "video/x-flv",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".wmv": "video/x-ms-wmv",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".opus": "audio/opus",
    ".srt": "application/x-subrip",
    ".ass": "text/x-ssa",
    ".ssa": "text/x-ssa",
    ".sub": "text/x-microdvd",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
}

_PENDING = {}          # state -> {user_id, verifier, created, consumed}
_RESULT_CB = None      # async fn(user_id, ok, detail) - wired by the settings UI
_receiver = {"runner": None, "site": None}
_receiver_lock = asyncio.Lock()


class GDriveError(RuntimeError):
    """Permanent Drive failure - shown to the user as-is (no retry)."""


class UploadCancelled(GDriveError):
    """User cancelled the task while a Drive upload was running."""


# ====================
# OAUTH CONFIGURATION
# ====================

def oauth_configured():
    return bool(Config.GDRIVE_CLIENT_ID and Config.GDRIVE_CLIENT_SECRET)


def set_result_callback(cb):
    global _RESULT_CB
    _RESULT_CB = cb


async def _emit(user_id, ok, detail):
    cb = _RESULT_CB
    if not cb:
        return
    try:
        await cb(user_id, ok, detail)
    except Exception as e:
        LOGS.warning("GDrive result callback failed: %s", e)


def _redirect_parts():
    uri = (Config.GDRIVE_REDIRECT_URI or "").strip() or "http://localhost:8080/oauth2callback"
    u = urlparse(uri)
    host = (u.hostname or "localhost").lower()
    port = u.port or (443 if u.scheme == "https" else 80)
    path = u.path or "/"
    return uri, host, port, path


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_auth_url(state, challenge):
    params = {
        "response_type": "code",
        "client_id": Config.GDRIVE_CLIENT_ID,
        "redirect_uri": _redirect_parts()[0],
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    return AUTH_ENDPOINT + "?" + urlencode(params)


# ====================
# TOKEN STORE
# ====================

def _tokens_path(user_id):
    folder = os.path.join(Config.WORK_DIR, "gdrive_tokens")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{int(user_id)}.json")


def _save_tokens_file(user_id, data):
    path = _tokens_path(user_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _read_tokens(user_id):
    path = _tokens_path(user_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and data.get("access_token") else None
    except (OSError, ValueError):
        return None


async def _db_load(user_id):
    from database import db
    return await db.get_gdrive_tokens(user_id)


async def _db_save(user_id, data):
    from database import db
    await db.set_gdrive_tokens(user_id, data)


async def _db_delete(user_id):
    from database import db
    await db.delete_gdrive_tokens(user_id)


async def _write_tokens(user_id, data):
    _save_tokens_file(user_id, data)
    try:
        await _db_save(user_id, data)
    except Exception as e:
        LOGS.warning("Drive token DB save failed for %s: %s", user_id, e)


async def _persisted_tokens(user_id):
    data = _read_tokens(user_id)
    if data:
        return data
    try:
        data = await _db_load(user_id)
    except Exception as e:
        LOGS.warning("Drive token DB load failed for %s: %s", user_id, e)
        data = None
    if isinstance(data, dict) and data.get("access_token"):
        try:
            _save_tokens_file(user_id, data)
        except OSError:
            pass
        return data
    return None


async def is_connected(user_id):
    return bool(await _persisted_tokens(user_id))


_user_locks = {}


def _lock_for(user_id):
    key = int(user_id)
    lock = _user_locks.get(key)
    if lock is None:
        lock = _user_locks[key] = asyncio.Lock()
    return lock


async def _refresh_tokens(user_id, data):
    payload = {
        "client_id": Config.GDRIVE_CLIENT_ID,
        "refresh_token": data.get("refresh_token", ""),
        "grant_type": "refresh_token",
    }
    if Config.GDRIVE_CLIENT_SECRET:
        payload["client_secret"] = Config.GDRIVE_CLIENT_SECRET
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(TOKEN_ENDPOINT, data=payload) as resp:
            js = await resp.json(content_type=None)
    token = js.get("access_token")
    if not token:
        raise RuntimeError(js.get("error_description") or js.get("error") or "refresh failed")
    data = dict(data)
    data["access_token"] = token
    data["expires_at"] = time.time() + int(js.get("expires_in") or 3600)
    if js.get("refresh_token"):
        data["refresh_token"] = js["refresh_token"]
    await _write_tokens(user_id, data)
    return data


async def load_tokens(user_id):
    data = await _persisted_tokens(user_id)
    if not data:
        return None
    if float(data.get("expires_at") or 0) <= time.time() + 60:
        if not data.get("refresh_token"):
            return None
        async with _lock_for(user_id):
            data = _read_tokens(user_id)
            if not data:
                return None
            if float(data.get("expires_at") or 0) <= time.time() + 60:
                try:
                    data = await _refresh_tokens(user_id, data)
                except Exception as e:
                    LOGS.warning("Drive token refresh failed for %s: %s", user_id, e)
                    return None
    return data


async def leech_drive_uid(requester_id=None):
    """WZML-X style global credential for LEECH: the bot owner's Drive login
    serves every user; falls back to the requester's own connect. 0 = nobody."""
    owner = int(Config.OWNER_ID or 0)
    if owner and await load_tokens(owner):
        return owner
    rid = int(requester_id or 0)
    if rid and rid != owner and await load_tokens(rid):
        return rid
    return 0


async def disconnect_drive(user_id):
    data = await _persisted_tokens(user_id)
    if data and data.get("refresh_token"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(REVOKE_ENDPOINT, data={"token": data["refresh_token"]}) as resp:
                    await resp.read()
        except Exception as e:
            LOGS.info("Drive revoke skipped: %s", e)
    try:
        os.remove(_tokens_path(user_id))
    except OSError:
        pass
    try:
        await _db_delete(user_id)
    except Exception as e:
        LOGS.warning("Drive token DB delete failed for %s: %s", user_id, e)


# ====================
# CONNECT FLOW (PKCE + loopback auto-confirm)
# ====================

def _prune_pending():
    now = time.time()
    for state in [s for s, e in _PENDING.items() if now - e["created"] > CONNECT_TTL]:
        _PENDING.pop(state, None)


def has_pending(user_id):
    _prune_pending()
    return any(
        e["user_id"] == int(user_id) and not e["consumed"]
        for e in _PENDING.values()
    )


async def begin_connect(user_id):
    """Create a fresh PKCE session. Returns (auth_url, auto_confirm_ok)."""
    if not oauth_configured():
        raise RuntimeError(
            "Google Drive OAuth is not configured on this bot yet "
            "(set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET)."
        )
    _prune_pending()
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    _PENDING[state] = {
        "user_id": int(user_id),
        "verifier": verifier,
        "created": time.time(),
        "consumed": False,
    }
    auto_ok = await _ensure_receiver()
    return build_auth_url(state, challenge), auto_ok


async def _ensure_receiver():
    """Start the localhost OAuth callback server once. True when listening."""
    async with _receiver_lock:
        if _receiver.get("site") is not None:
            return True
        uri, host, port, path = _redirect_parts()
        if host not in ("localhost", "127.0.0.1", "::1"):
            return False
        app = web.Application()
        app.router.add_get(path, _handle_callback)
        runner = web.AppRunner(app, access_log=None)
        try:
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
        except Exception as e:
            LOGS.warning("OAuth callback listener could not bind port %s: %s", port, e)
            try:
                await runner.cleanup()
            except Exception:
                pass
            return False
        _receiver["runner"] = runner
        _receiver["site"] = True
        LOGS.info("Drive OAuth callback listening on 127.0.0.1:%s%s", port, path)
        return True


async def _handle_callback(request):
    code = request.query.get("code") or ""
    state = request.query.get("state") or ""
    error = request.query.get("error") or ""
    if error:
        entry = _PENDING.get(state)
        if entry and not entry["consumed"]:
            entry["consumed"] = True
            await _emit(entry["user_id"], False, request.query.get("error_description") or error)
        page = _page("Connection cancelled", "You closed the Google consent screen. Click Authorize to try again.")
    elif not code or not state:
        page = _page("Missing code", "Google did not send an authorization code. Go back to Telegram.")
    else:
        ok = await _consume(state, code)
        if ok:
            page = _page("Google Drive connected", "You can close this tab and go back to Telegram.")
        else:
            page = _page("Link expired", "This connect link expired. Open /settings - Google Drive and click Authorize again.")
    return web.Response(text=page, content_type="text/html")


def _page(title, body):
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>"
        "body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
        ".card{background:#1e293b;padding:32px 40px;border-radius:16px;text-align:center;"
        "max-width:420px;box-shadow:0 8px 30px rgba(0,0,0,.4)}"
        "h1{font-size:20px;margin:0 0 10px}p{margin:0;color:#94a3b8;font-size:14px;line-height:1.5}"
        "</style></head><body><div class='card'>"
        f"<h1>{title}</h1><p>{body}</p></div></body></html>"
    )


async def _consume(state, code):
    entry = _PENDING.get(state)
    if not entry or entry["consumed"]:
        return False
    entry["consumed"] = True
    try:
        await _exchange(entry, code)
    except Exception as e:
        LOGS.warning("Drive code exchange failed: %s", e)
        await _emit(entry["user_id"], False, str(e))
        return False
    return True


async def _exchange(entry, code):
    payload = {
        "code": code,
        "client_id": Config.GDRIVE_CLIENT_ID,
        "redirect_uri": _redirect_parts()[0],
        "grant_type": "authorization_code",
        "code_verifier": entry["verifier"],
    }
    if Config.GDRIVE_CLIENT_SECRET:
        payload["client_secret"] = Config.GDRIVE_CLIENT_SECRET
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
        async with session.post(TOKEN_ENDPOINT, data=payload) as resp:
            js = await resp.json(content_type=None)
    token = js.get("access_token")
    if not token:
        raise RuntimeError(js.get("error_description") or js.get("error") or "Google rejected the code.")
    user_id = entry["user_id"]
    data = (await _persisted_tokens(user_id)) or {}
    data.update({
        "access_token": token,
        "refresh_token": js.get("refresh_token") or data.get("refresh_token", ""),
        "expires_at": time.time() + int(js.get("expires_in") or 3600),
        "scope": js.get("scope", SCOPES),
        "obtained_at": time.time(),
    })
    await _write_tokens(user_id, data)
    email = await fetch_account_email(token) or ""
    await _emit(user_id, True, email)
    return email


def _parse_redirect(text):
    """-> (code, state) from a pasted redirect URL, or ("", "") when unusable."""
    t = (text or "").strip()
    if "code=" not in t:
        return "", ""
    try:
        query = parse_qs(urlparse(t).query)
    except Exception:
        return "", ""
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    return code, state


async def complete_paste(user_id, text):
    """Consume a manually pasted redirect URL. Raises ValueError with a friendly message."""
    _prune_pending()
    code, state = _parse_redirect(text)
    if not code:
        raise ValueError("That does not look like the Google redirect link (no code found).")
    if state:
        entry = _PENDING.get(state)
        if entry is None or entry["user_id"] != int(user_id):
            raise ValueError("This connect link has expired. Open /settings, Google Drive and click Authorize again.")
    else:
        entry = next(
            (e for e in reversed(list(_PENDING.values()))
             if e["user_id"] == int(user_id) and not e["consumed"]),
            None,
        )
        if entry is None:
            raise ValueError("No Google Drive connection is waiting. Open /settings, Google Drive and click Authorize first.")
    if entry["consumed"]:
        raise ValueError("This link was already used. Click Authorize for a fresh one.")
    entry["consumed"] = True
    try:
        return await _exchange(entry, code)
    except Exception as e:
        await _emit(user_id, False, str(e))
        raise


# ====================
# ACCOUNT INFO
# ====================

async def drive_mime(file_id, user_id):
    """MIME type of a Drive file via the user's connect. Raises GDriveError."""
    tokens = await load_tokens(user_id)
    if not tokens:
        raise GDriveError("Connect your Google Drive first (Settings > Google Drive).")
    info = await _file_info(file_id, tokens)
    return info.get("mimeType", "")


async def fetch_account_email(access_token):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(
                f"{API_BASE}/about?fields=user(emailAddress)",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status != 200:
                    return ""
                js = await resp.json(content_type=None)
        return (js.get("user") or {}).get("emailAddress") or ""
    except Exception as e:
        LOGS.warning("Drive about lookup failed: %s", e)
        return ""


# ====================
# LINK PARSING
# ====================

_FILE_PATH_RE = re.compile(r"/file/d/([A-Za-z0-9_-]{20,})")
_FOLDER_PATH_RE = re.compile(r"/folders/([A-Za-z0-9_-]{20,})")
_GENERIC_PATH_RE = re.compile(r"/d/([A-Za-z0-9_-]{20,})")
_ID_PARAM_RE = re.compile(r"[?&](?:id|file_id)=([A-Za-z0-9_-]{20,})")


def is_drive_host(host):
    host = (host or "").lower().rstrip(".")
    return (
        host == "drive.google.com"
        or host.endswith(".drive.google.com")
        or host == "docs.google.com"
        or host == "drive.usercontent.google.com"
    )


def parse_drive_url(url):
    """-> (kind, file_id); kind is "file" | "folder" | None."""
    try:
        u = urlparse((url or "").strip())
    except Exception:
        return None, ""
    if not is_drive_host(u.hostname or ""):
        return None, ""
    for pattern, kind in (
        (_FOLDER_PATH_RE, "folder"),
        (_FILE_PATH_RE, "file"),
        (_GENERIC_PATH_RE, "file"),
    ):
        m = pattern.search(u.path or "")
        if m:
            return kind, m.group(1)
    try:
        params = parse_qs(u.query or "")
    except Exception:
        params = {}
    for key in ("id", "file_id"):
        values = params.get(key) or []
        if values and re.fullmatch(r"[A-Za-z0-9_-]{20,}", values[0]):
            return "file", values[0]
    return None, ""


# ====================
# DOWNLOAD
# ====================

def _filename_from_headers(headers):
    from bot.helper_funcs.utils import safe_media_name

    cd = headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*\s*=\s*UTF-8''([^;\"]+)", cd, re.I)
    if not m:
        m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I)
    if not m:
        m = re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    if not m:
        return ""
    raw = unquote(m.group(1).strip().strip('"'))
    if not raw:
        return ""
    return safe_media_name(raw)


def _looks_like_file(resp):
    cd = (resp.headers.get("Content-Disposition") or "").lower()
    if "attachment" in cd or "filename" in cd:
        return True
    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    return ctype not in ("", "text/html", "application/xhtml+xml")


def _confirm_url(body, file_id):
    m = re.search(r'<form[^>]*action="([^"]+)"', body, re.I)
    if m and ("download" in m.group(1) or "confirm" in body):
        action = html_unescape(m.group(1))
        inputs = {}
        for tag in re.findall(r"<input[^>]*>", body, re.I):
            nm = re.search(r'name="([^"]+)"', tag)
            if not nm:
                continue
            vm = re.search(r'value="([^"]*)"', tag)
            inputs[nm.group(1)] = html_unescape(vm.group(1)) if vm else ""
        if inputs:
            sep = "&" if "?" in action else "?"
            return action + sep + urlencode(inputs)
    m = re.search(r"confirm=([0-9A-Za-z_-]+)", body)
    token = m.group(1) if m else "t"
    return (
        f"https://drive.usercontent.google.com/download"
        f"?id={file_id}&export=download&confirm={quote(token)}"
    )


def _private_hint(body, final_url=""):
    low = (body or "").lower()
    url_low = (final_url or "").lower()
    if "accounts.google.com" in url_low or "servicelogin" in low or "sign in" in low:
        return (
            "This Drive file is private. Connect your Google Drive "
            "(Settings > Google Drive > Authorize) and try again."
        )
    if "request access" in low or "you need access" in low or "don't have access" in low:
        return "You do not have access to this file. Ask the owner to share it with you."
    if "too many" in low or "quota" in low or "rate limit" in low:
        return "Google Drive is rate-limiting right now. Try again in a few minutes."
    return "Google Drive did not return the file. The link may be dead or private."


async def _write_stream(resp, part, final_path, progress_cb, should_stop,
                         base_done=0, total=None):
    append = resp.status == 206
    if not append:
        base_done = 0
    if total is None:
        total = int(resp.headers.get("Content-Length") or 0) + (base_done if append else 0)
    if append:
        m = re.search(r"bytes\s+\d+-\d+/(\d+)", resp.headers.get("Content-Range") or "")
        if m:
            total = int(m.group(1))

    done = float(base_done)
    cancelled = False
    last_time = time.time()
    last_done = done
    speed = 0.0
    mode = "ab" if append else "wb"

    async with aiofiles_open(part, mode) as fh:
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
                        pct=min(done * 100.0 / total, 100.0),
                        done=done, total=total, speed=speed,
                    )

    if cancelled:
        LOGS.info("[GDrive] Download paused by user")
        return None

    if total <= 0:
        total = done
    os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
    os.replace(part, final_path)
    if progress_cb:
        await progress_cb(pct=100.0, done=done, total=total, speed=speed)
    LOGS.info("[GDrive] Download complete - %s (%s bytes)", final_path, int(done))
    return final_path


async def _api_download(file_id, dest_dir, tokens, progress_cb, should_stop, part):
    info = await _file_info(file_id, tokens)
    file_id = info.get("id") or file_id
    name = _safe_name(info.get("name") or f"drive_{file_id}")
    final_path = os.path.join(dest_dir, name)
    url = f"{API_BASE}/files/{file_id}?alt=media"
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "User-Agent": UA,
    }
    resume = os.path.getsize(part) if os.path.isfile(part) else 0
    if resume:
        headers["Range"] = f"bytes={resume}-"
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status == 401:
                raise GDriveError("Google Drive access expired - reconnect in Settings > Google Drive.")
            if resp.status == 404:
                raise GDriveError("File not found - check the Google Drive link.")
            if resp.status == 403:
                raise GDriveError("No access to this file - ask the owner to share it.")
            if resp.status == 416:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise RuntimeError("resume range rejected")
            if resp.status not in (200, 206):
                raise RuntimeError(f"Drive API HTTP {resp.status}")
            return await _write_stream(
                resp, part, final_path, progress_cb, should_stop,
                base_done=resume if resp.status == 206 else 0,
            )


async def _file_info(file_id, tokens):
    url = (
        f"{API_BASE}/files/{file_id}"
        "?fields=id,name,mimeType,size,shortcutDetails(targetId)"
    )
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(2):
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    raise GDriveError("Google Drive access expired - reconnect in Settings > Google Drive.")
                if resp.status == 404:
                    raise GDriveError("File not found - check the Google Drive link.")
                if resp.status == 403:
                    raise GDriveError("No access to this file - ask the owner to share it.")
                if resp.status != 200:
                    raise RuntimeError(f"Drive API HTTP {resp.status}")
                js = await resp.json(content_type=None)
            if js.get("mimeType") == "application/vnd.google-apps.folder":
                raise GDriveError("Folder links are not supported yet - send a single file link.")
            if js.get("mimeType") == "application/vnd.google-apps.shortcut":
                target = (js.get("shortcutDetails") or {}).get("targetId")
                if not target:
                    raise GDriveError("This shortcut points nowhere.")
                file_id = target
                continue
            return js
    raise GDriveError("Could not read this Drive file.")


# ==================== FOLDER LISTING (leech whole folders) ====================
FOLDER_MIME = "application/vnd.google-apps.folder"
FOLDER_MAX_FILES = 200
FOLDER_MAX_DEPTH = 8


async def _folder_name(folder_id, tokens):
    url = f"{API_BASE}/files/{folder_id}?fields=id,name,mimeType"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        async with session.get(url, headers=headers) as resp:
            if resp.status == 401:
                raise GDriveError("Google Drive access expired - reconnect in Settings > Google Drive.")
            if resp.status in (403, 404):
                raise GDriveError("Folder not found or no access - check the folder link.")
            if resp.status != 200:
                raise RuntimeError(f"Drive API HTTP {resp.status}")
            js = await resp.json(content_type=None)
    if js.get("mimeType") != FOLDER_MIME:
        raise GDriveError("That link is not a folder - send a single file link.")
    return js.get("name") or "Drive Folder"


async def _list_page(user_id, folder_id, page_token=""):
    tokens = await load_tokens(user_id)
    if not tokens:
        raise GDriveError("Connect your Google Drive first (Settings > Google Drive).")
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "nextPageToken,files(id,name,mimeType,size)",
        "pageSize": "100",
        "spaces": "drive",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if page_token:
        params["pageToken"] = page_token
    url = f"{API_BASE}/files?{urlencode(params)}"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    raise GDriveError("Google Drive access expired - reconnect in Settings > Google Drive.")
                if resp.status == 404:
                    raise GDriveError("Folder not found or no access - check the folder link.")
                if resp.status == 403:
                    body = (await resp.text())[:300]
                    if "rateLimitExceeded" in body or "userRateLimitExceeded" in body:
                        if attempt == 0:
                            await asyncio.sleep(2)
                            continue
                        raise GDriveError("Google Drive rate limit hit - try again in a minute.")
                    raise GDriveError("No access to this folder - ask the owner to share it.")
                if resp.status == 429 and attempt == 0:
                    await asyncio.sleep(2)
                    continue
                if resp.status != 200:
                    raise RuntimeError(f"Drive API HTTP {resp.status}")
                return await resp.json(content_type=None)
    raise RuntimeError("Drive API list failed.")


async def drive_list_folder(folder_id, user_id):
    """Walk a folder (recursively) -> (entries, skipped, folder_name).
    entries = [(file_id, name, size), ...] downloadable files in walk order.
    skipped = native Google Docs + shortcuts + subfolders past the depth cap.
    Raises GDriveError on missing connect / no access / folder too big."""
    tokens = await load_tokens(user_id)
    if not tokens:
        raise GDriveError("Connect your Google Drive first (Settings > Google Drive).")
    folder_name = await _folder_name(folder_id, tokens)
    entries = []
    skipped = 0
    queue = [(folder_id, 0)]
    while queue:
        fid, depth = queue.pop(0)
        page_token = ""
        while True:
            js = await _list_page(user_id, fid, page_token)
            for item in js.get("files", []):
                mime = item.get("mimeType") or ""
                if mime == FOLDER_MIME:
                    if depth + 1 > FOLDER_MAX_DEPTH:
                        skipped += 1
                    else:
                        queue.append((item.get("id"), depth + 1))
                    continue
                if mime.startswith("application/vnd.google-apps."):
                    skipped += 1
                    continue
                if len(entries) >= FOLDER_MAX_FILES:
                    raise GDriveError(
                        f"Folder too large - more than {FOLDER_MAX_FILES} files."
                    )
                entries.append(
                    (item.get("id"), item.get("name") or "file", int(item.get("size") or 0))
                )
            page_token = js.get("nextPageToken") or ""
            if not page_token:
                break
    return entries, skipped, folder_name


async def _public_download(file_id, dest_dir, progress_cb, should_stop, part):
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=300)
    resume = os.path.getsize(part) if os.path.isfile(part) else 0
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as session:
        async def fetch(url, ranged):
            headers = {"Range": f"bytes={resume}-"} if ranged and resume else {}
            resp = await session.get(url, headers=headers, allow_redirects=True)
            return resp

        resp = await fetch(f"https://drive.google.com/uc?export=download&id={file_id}", True)
        async with resp:
            if resp.status == 404:
                raise GDriveError("File not found - check the Google Drive link.")
            if _looks_like_file(resp):
                name = _filename_from_headers(resp.headers) or f"drive_{file_id}"
                return await _write_stream(
                    resp, part, os.path.join(dest_dir, name),
                    progress_cb, should_stop,
                    base_done=resume if resp.status == 206 else 0,
                )
            body = await resp.text(errors="ignore")
            final_url = str(resp.url)

        confirm = _confirm_url(body, file_id)
        if confirm and "accounts.google.com" not in final_url:
            resp2 = await fetch(confirm, True)
            async with resp2:
                if resp2.status == 404:
                    raise GDriveError("File not found - check the Google Drive link.")
                if _looks_like_file(resp2):
                    name = _filename_from_headers(resp2.headers) or f"drive_{file_id}"
                    return await _write_stream(
                        resp2, part, os.path.join(dest_dir, name),
                        progress_cb, should_stop,
                        base_done=resume if resp2.status == 206 else 0,
                    )
                body = await resp2.text(errors="ignore")
                final_url = str(resp2.url)
        raise GDriveError(_private_hint(body, final_url))


async def drive_download(file_id, dest_dir, user_id=None, progress_cb=None, should_stop=None):
    """Download a Drive file (public link, or private via the user's connect).
    Returns the local path, None when cancelled. Raises GDriveError on failures."""
    os.makedirs(dest_dir, exist_ok=True)
    tokens = await load_tokens(user_id) if user_id else None
    part = os.path.join(dest_dir, f"{file_id}.part")
    last_err = None
    for attempt in range(1, 4):
        if should_stop and should_stop():
            return None
        try:
            if tokens:
                path = await _api_download(file_id, dest_dir, tokens, progress_cb, should_stop, part)
            else:
                path = await _public_download(file_id, dest_dir, progress_cb, should_stop, part)
            if path is None:
                return None
            return path
        except (GDriveError, asyncio.CancelledError):
            raise
        except Exception as e:
            last_err = e
            LOGS.warning("[GDrive] attempt %s failed: %s", attempt, e)
            if attempt < 3:
                await asyncio.sleep(2 * attempt)
    raise GDriveError(f"Download failed after 3 tries: {last_err}")


def _safe_name(name):
    from bot.helper_funcs.utils import safe_media_name
    return safe_media_name(name)


# ====================
# UPLOADS (Milestone 2)
# ====================

UPLOAD_CHUNK = 8 * 1024 * 1024


async def upload_drive_uid(user_id=None):
    """Whose Drive receives uploads: own_drive toggle first, then owner, then requester."""
    uid = int(user_id or 0)
    own = False
    if uid:
        try:
            from database import db as _db
            own = bool((await _db.get_gdrive_settings(uid)).get("own_drive"))
        except Exception:
            own = False
    if own and uid and await load_tokens(uid):
        return uid
    owner = int(Config.OWNER_ID or 0)
    if owner and await load_tokens(owner):
        return owner
    if uid and uid != owner and await load_tokens(uid):
        return uid
    return 0


async def resolve_upload_folder(requester_id, drive_uid):
    env_folder = getattr(Config, "GDRIVE_UPLOAD_FOLDER", "") or os.getenv("GDRIVE_UPLOAD_FOLDER", "")
    try:
        from database import db as _db
        own = str((await _db.get_gdrive_settings(requester_id)).get("parent_folder") or "")
    except Exception:
        own = ""
    requester_is_owner = int(requester_id or 0) == int(getattr(Config, "OWNER_ID", 0) or 0)
    if requester_is_owner:
        # Owner's Default Parent Folder (e.g. the VIP folder) wins over the env default.
        return own or env_folder
    if drive_uid == int(Config.OWNER_ID or 0):
        return env_folder or own
    return own or env_folder


async def drive_upload_file(drive_uid, file_path, progress_cb=None, folder_id="", cancel_check=None):
    """Resumable upload; returns {"id", "name", "mime"} and shares the file publicly."""
    tokens = await load_tokens(drive_uid)
    if not tokens:
        raise GDriveError("Google Drive is not connected.")
    name = os.path.basename(file_path)
    size = os.path.getsize(file_path)
    if size <= 0:
        raise GDriveError("Cannot upload an empty file.")
    mime = (
        mimetypes.guess_type(name)[0]
        or _EXT_MIME.get(os.path.splitext(name)[1].lower())
        or "application/octet-stream"
    )
    meta = {"name": name}
    if folder_id:
        meta["parents"] = [folder_id]

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=180)
    async with aiohttp.ClientSession(
        timeout=timeout, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    ) as session:
        async with session.post(
            f"{UPLOAD_BASE}/files?uploadType=resumable",
            json=meta,
            headers={
                "Content-Type": "application/json",
                "X-Upload-Content-Type": mime,
                "X-Upload-Content-Length": str(size),
            },
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise GDriveError(f"Drive upload init failed ({resp.status}): {body[:200]}")
            session_uri = resp.headers.get("Location")
            init_body = "" if session_uri else (await resp.text())[:200]
        if not session_uri:
            raise GDriveError(
                f"Drive upload init failed: no session URL: {init_body}"
            )

        sent = 0
        final = None
        with open(file_path, "rb") as fh:
            while sent < size:
                if cancel_check and cancel_check():
                    raise UploadCancelled("cancelled")
                fh.seek(sent)
                chunk = fh.read(min(UPLOAD_CHUNK, size - sent))
                if not chunk:
                    raise GDriveError("Drive upload: file read failed")
                end = sent + len(chunk) - 1
                advance = None
                for try_n in range(4):
                    try:
                        async with session.put(
                            session_uri,
                            data=chunk,
                            headers={
                                "Content-Length": str(len(chunk)),
                                "Content-Range": f"bytes {sent}-{end}/{size}",
                            },
                        ) as resp:
                            if resp.status in (200, 201):
                                final = await resp.json()
                                break
                            if resp.status == 308:
                                rng = resp.headers.get("Range", "")
                                if "-" in rng:
                                    try:
                                        advance = int(rng.rsplit("-", 1)[1]) + 1
                                    except ValueError:
                                        advance = end + 1
                                else:
                                    advance = end + 1
                                if advance <= sent:
                                    advance = end + 1
                                break
                            if resp.status in (401, 403) and try_n == 0:
                                fresh = await load_tokens(drive_uid)
                                if not fresh:
                                    raise GDriveError("Drive token expired - reconnect Google Drive.")
                                session.headers["Authorization"] = f"Bearer {fresh['access_token']}"
                                continue
                            if resp.status >= 500:
                                await asyncio.sleep(1.5 * (try_n + 1))
                                continue
                            body = await resp.text()
                            raise GDriveError(f"Drive upload failed ({resp.status}): {body[:180]}")
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        if try_n == 3:
                            raise GDriveError(f"Drive upload network error: {e}")
                        await asyncio.sleep(1.5 * (try_n + 1))
                if final is not None:
                    break
                if advance is None:
                    raise GDriveError("Drive upload failed: retries exhausted")
                sent = advance
                if progress_cb:
                    await progress_cb(min(sent, size), size)

        if final is None:
            raise GDriveError("Drive upload failed: no result")
        file_id = final.get("id")
        if not file_id:
            raise GDriveError("Drive upload failed: no file id")
        try:
            async with session.post(
                f"{API_BASE}/files/{file_id}/permissions",
                json={"type": "anyone", "role": "reader"},
            ) as resp:
                if resp.status >= 400:
                    LOGS.warning(
                        "[GDrive] public share failed (%s): %s",
                        resp.status,
                        (await resp.text())[:150],
                    )
        except Exception as e:
            LOGS.warning("[GDrive] public share error: %s", e)
        if progress_cb:
            await progress_cb(size, size)
        return {"id": file_id, "name": final.get("name") or name, "mime": mime}
