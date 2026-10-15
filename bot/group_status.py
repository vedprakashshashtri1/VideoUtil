# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# Single shared live status message per chat (NexonBots pattern).
#
# Locked spec:
#   - 1 chat = 1 status message. New tasks update the SAME message,
#     a new message is never spawned per task.
#   - Unlimited tasks in one message: ACTIVE tasks get full detail cards,
#     QUEUED tasks get compact one-liners (never exceeds 4096 chars).
#   - One worker per chat, ~8s cycle, edit ONLY when text changed
#     (FloodWait-proof). Per-task interim messages are deleted by the
#     workers (Phase 3 wiring) -- this message is the source of truth.
#   - Cancel: /c<taskid>, task owner or admin only.
#   - Buttons: Refresh (7s/user cooldown) + Close (admin only).

import asyncio
import html
import logging
import re
import time

try:
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:  # wzgram fallback
    try:
        from wzgram.types import InlineKeyboardMarkup, InlineKeyboardButton
    except ImportError:
        InlineKeyboardMarkup = None
        InlineKeyboardButton = None

from bot.task_manager import (
    task_manager,
    PHASE_QUEUED,
    PHASE_DOWNLOADING,
    PHASE_PROCESSING,
    PHASE_SPLITTING,
    PHASE_UPLOADING,
    PHASE_CANCELLED,
)

LOGGER = logging.getLogger(__name__)

STATUS_EDIT_INTERVAL = 8.0
REFRESH_COOLDOWN = 7.0
MAX_MESSAGE_CHARS = 4000
TASKS_PER_PAGE = 4

BAR_LEN = 12
BAR_FULL = "█"
BAR_EMPTY = "░"

# op -> human verb for the Status line.
OP_VERB = {
    "encode": "Encoding",
    "watermark": "Watermarking",
    "hardsub": "Hardsubbing",
    "cut": "Trimming",
    "crop": "Cropping",
    "merge": "Merging",
    "audio": "Audio work",
    "sub": "Subtitles",
    "screenshot": "Screenshots",
    "leech": "Leeching",
    "metadata": "Metadata",
}

_status_store: dict[int, dict] = {}
_store_lock = asyncio.Lock()
_refresh_cooldown: dict[int, float] = {}


def _bar(percent: float) -> str:
    pct = max(0.0, min(100.0, float(percent or 0)))
    filled = min(BAR_LEN, int(pct * BAR_LEN / 100))
    return "❨" + ("⬢" * filled) + ("⬡" * (BAR_LEN - filled)) + "❩"


def _phase_label(task: dict, position: int) -> str:
    phase = task.get("phase", PHASE_QUEUED)
    if phase == PHASE_QUEUED:
        return f"Queued #{position}"
    if phase == PHASE_DOWNLOADING:
        return "Downloading"
    if phase == PHASE_UPLOADING:
        return "Uploading"
    return OP_VERB.get(task.get("op", ""), "Processing")


def _mention(user_id: int) -> str:
    try:
        return f"<a href='tg://user?id={int(user_id)}'>{int(user_id)}</a>"
    except (TypeError, ValueError):
        return "user"


def _engine(task: dict) -> str:
    """Engine shown on the card: transfers run on Pyrogram, work on FFmpeg.
    Download phase may carry an override (torrentp/megatools for leech)."""
    if task.get("phase") == PHASE_DOWNLOADING:
        return html.escape(str(task.get("engine") or "Pyrogram"))
    if task.get("phase") == PHASE_UPLOADING:
        return "Pyrogram"
    return "FFmpeg"


def _mode(task: dict) -> str:
    res = str(task.get("res") or "")
    if res:
        mode = f"#{html.escape(res)}"
    else:
        mode = f"#{html.escape(str(task.get('op') or 'task'))}"
    extra = str(task.get("mode_extra") or "")
    if extra:
        return f"#{html.escape(extra)} | {mode}"
    return mode


def _title(task: dict) -> str:
    name = html.escape(str(task.get("title", "Media"))[:60])
    link = str(task.get("link") or "")
    if link.startswith("http"):
        return f"<a href='{link}'>{name}</a>"
    return f"<b>{name}</b>"


def _user_cell(user_id) -> str:
    try:
        uid = int(user_id)
        return f"<a href='tg://user?id={uid}'>{uid}</a> | {uid}"
    except (TypeError, ValueError):
        return "user"


def _status_head(task: dict, position: int) -> str:
    phase = task.get("phase", PHASE_QUEUED)
    if phase == PHASE_CANCELLED:
        return "╭ 🛑 Cancelling…"
    if phase == PHASE_DOWNLOADING:
        return "╭ ✨ Downloading…"
    if phase == PHASE_UPLOADING:
        return "╭ ✨ Uploading…"
    if phase == PHASE_QUEUED:
        return "╭ QueueUp…"
    verb = OP_VERB.get(task.get("op", ""), "Processing")
    return f"╭ ✨ {verb}…"


def _done_line(task: dict) -> str:
    done = float(task.get("done_bytes") or 0)
    total = float(task.get("total_bytes") or 0)
    if total > 0:
        return f"{_fmt_bytes(done)} / {_fmt_bytes(total)}"
    if done > 0:
        return f"{_fmt_bytes(done)} / Unknown"
    return "0 B / Unknown"


def _status_word(task: dict, position: int) -> str:
    phase = task.get("phase", PHASE_QUEUED)
    if phase == PHASE_CANCELLED:
        return "Cancelling…"
    if phase == PHASE_QUEUED:
        return "Queued"
    if phase == PHASE_DOWNLOADING:
        return "Downloading"
    if phase == PHASE_UPLOADING:
        return "Uploading"
    if phase == PHASE_SPLITTING:
        return "Preparing split parts"
    res = str(task.get("res") or "")
    if res:
        return f"Encoding in {res}"
    return OP_VERB.get(task.get("op", ""), "Processing")


def _detail_card(task: dict, position: int) -> str:
    pct = float(task.get("percent") or 0)
    speed = html.escape(str(task.get("speed") or "—"))
    eta = html.escape(str(task.get("eta") or "N/A"))
    tid = task.get("task_id", "")
    uid = task.get("user_id")
    detail = html.escape(str(task.get("detail") or "").strip())
    detail_line = f"┊ {detail}\n" if detail else ""
    return (
        f"❲{position}❳ Task ID: <code>{tid}</code> | Global: <code>#{position}</code>\n"
        f"{_title(task)}\n"
        f"╭ Task By {_mention(uid)}\n"
        f"┊ <code>{_bar(pct)}</code> <i>{pct:.2f}%</i>\n"
        f"┊ Status » <code>{_status_word(task, position)}</code> » <code>{speed}</code>\n"
        f"{detail_line}"
        f"┊ Done » <i>{_done_line(task)}</i>\n"
        f"┊ ETA » <i>⏳ {eta}</i>\n"
        f"┊ Engine » <i>{_engine(task)}</i>\n"
        f"┊ Mode » <code>{_mode(task)}</code>\n"
        f"╰ Cancel » /c_{tid}"
    )


def _queued_line(task: dict, position: int) -> str:
    tid = task.get("task_id", "")
    uid = task.get("user_id")
    return (
        f"❲{position}❳ Task ID: <code>{tid}</code> | Global: <code>#{position}</code>\n"
        f"{_title(task)}\n"
        f"╭ Task By {_mention(uid)}\n"
        f"┊ <code>{_bar(0)}</code> <i>0.00%</i>\n"
        f"┊ Status » <code>Queued</code> » <code>Global #{position}</code>\n"
        f"┊ Done » <i>0 B / Unknown</i>\n"
        f"┊ ETA » <i>⏳ N/A</i>\n"
        f"┊ Engine » <i>{_engine(task)}</i>\n"
        f"┊ Mode » <code>{_mode(task)}</code>\n"
        f"╰ Cancel » /c_{tid}"
    )


def render_status(
    tasks: list,
    counts: dict,
    sys_stats: str,
    page: int = 1,
    total_pages: int = 1,
    total_tasks: int = 0,
    start_idx: int = 0,
) -> str:
    """Pure render: task dicts + counts + footer -> HTML text. No Telegram."""
    lines = []
    if total_pages > 1:
        lines.append(f"<blockquote><b>Tasks:</b> {total_tasks or len(tasks)} | <b>Page:</b> {page}/{total_pages}</blockquote>\n")
    for i, t in enumerate(tasks, 1):
        pos = start_idx + i
        if t.get("phase") == PHASE_QUEUED:
            lines.append(_queued_line(t, pos))
        else:
            lines.append(_detail_card(t, pos))
        lines.append("")
    if sys_stats:
        lines.append(sys_stats)
    return "\n".join(lines).strip()


def fit_text(
    full: str,
    tasks: list,
    counts: dict,
    sys_stats: str,
    start_idx: int = 0,
) -> str:
    """4096 guard: full cards first, auto-compact to one-liners if too long."""
    if len(full) <= MAX_MESSAGE_CHARS:
        return full
    # Fallback: everything as compact lines (still ONE message, unlimited tasks).
    lines = []
    for i, t in enumerate(tasks, 1):
        pos = start_idx + i
        title = html.escape(str(t.get("title", "Media"))[:18])
        op = html.escape(str(t.get("op", ""))[:10])
        lines.append(f"{pos}. <code>{t.get('task_id', '')}</code> {op} {title} /c_{t.get('task_id', '')}")
    if sys_stats:
        lines.append(sys_stats)
    text = "\n".join(lines)
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1] + "…"
    return text


def _parse_speed(text: str) -> float:
    """'8.73MB/s' -> bytes/sec (best effort, 0 on garbage)."""
    try:
        m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)?", str(text or ""), re.I)
        if not m:
            return 0.0
        num = float(m.group(1))
        unit = (m.group(2) or "B").upper()
        return num * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}.get(unit, 1)
    except (TypeError, ValueError):
        return 0.0


def _fmt_bytes(size: float) -> str:
    size = max(0.0, float(size or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f}{unit}"
        size /= 1024.0
    return "0B"


def make_manager_progress(task_id: str):
    """Download-phase progress callback feeding ONLY the shared status.

    Drop-in for progress_for_pyrogram: same (current, total, *args) shape,
    but never touches any message (FloodWait-proof by construction).
    """
    start = time.time()

    async def _cb(current, total, *args):
        if task_manager.is_cancelled(task_id):
            raise asyncio.CancelledError(f"Task {task_id} was cancelled during download")
        try:
            total_f = float(total or 0)
            cur_f = float(current or 0)
            pct = (cur_f * 100.0 / total_f) if total_f > 0 else 0.0
            elapsed = max(time.time() - start, 0.001)
            speed = cur_f / elapsed
            eta_s = int((total_f - cur_f) / speed) if speed > 0 else 0
            eta = f"{eta_s // 60}m{eta_s % 60}s" if eta_s >= 60 else f"{eta_s}s"
            await task_manager.update_progress(
                task_id, pct, f"{_fmt_bytes(speed)}/s", eta,
                done_bytes=cur_f, total_bytes=total_f,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    return _cb


class UploadSink:
    """Duck-typed status message that swallows all display output.

    Handed to the uploader for wired tasks so the shared status message is
    the ONLY live view. All edits/deletes are no-ops. Failures surface via
    the uploader's boolean return value (the caller replies visibly).
    """

    def __init__(self, task_id=None):
        self.task_id = task_id

    async def edit_text(self, *args, **kwargs):
        return None

    async def edit_caption(self, *args, **kwargs):
        return None

    async def delete(self, *args, **kwargs):
        return None


def system_snapshot() -> dict:
    """CPU/RAM/disk/uptime. Never raises (psutil optional)."""
    snap = {"cpu": 0.0, "ram": 0.0, "free_gb": 0.0, "free_pct": 0.0, "up": "0m"}
    try:
        import psutil

        snap["cpu"] = float(psutil.cpu_percent(interval=None))
        snap["ram"] = float(psutil.virtual_memory().percent)
        du = psutil.disk_usage(".")
        snap["free_gb"] = du.free / (1024**3)
        snap["free_pct"] = 100.0 - float(du.percent)
        from bot import BOT_START_TIME

        up = int(time.time() - BOT_START_TIME)
        d, up = divmod(up, 86400)
        h, up = divmod(up, 3600)
        m, _ = divmod(up, 60)
        snap["up"] = (f"{d}d" if d else "") + f"{h}h{m}m"
    except Exception:
        pass
    return snap


def build_footer(snap: dict, dl_bps: float = 0.0, ul_bps: float = 0.0) -> str:
    free = _fmt_bytes(snap.get("free_gb", 0) * (1024**3))
    return (
        "⌬ <b>BOT STATS</b>\n"
        "▬▬▬▬▬✘▬▬▬▬▬\n"
        f"╭ <b>CPU »</b> {snap.get('cpu', 0):.1f}% | <b>FREE »</b> {free}\n"
        f"├ <b>RAM »</b> {snap.get('ram', 0):.1f}% | <b>UP »</b> {snap.get('up', '0m')}\n"
        f"╰ <b>DL »</b> {_fmt_bytes(dl_bps)}/s | <b>UL »</b> {_fmt_bytes(ul_bps)}/s"
    )


def get_sys_stats() -> str:
    """Legacy footer (no totals). Kept for the idle/empty card."""
    return build_footer(system_snapshot())


def build_buttons(page: int = 1, total_pages: int = 1) -> object | None:
    if InlineKeyboardMarkup is None or InlineKeyboardButton is None:
        return None
    rows = []
    if total_pages > 1:
        prev_page = page - 1 if page > 1 else total_pages
        next_page = page + 1 if page < total_pages else 1
        rows.append([
            InlineKeyboardButton("◀️ Prev", callback_data=f"vst_page:{prev_page}"),
            InlineKeyboardButton(f"{page} / {total_pages}", callback_data="vst_page:noop"),
            InlineKeyboardButton("Next ▶️", callback_data=f"vst_page:{next_page}"),
        ])
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="vst_ref"),
    ])
    return InlineKeyboardMarkup(rows)


def refresh_allowed(user_id: int, now: float | None = None) -> tuple[bool, float]:
    """Per-user refresh cooldown. Returns (allowed, wait_seconds)."""
    now = time.time() if now is None else now
    last = _refresh_cooldown.get(user_id, 0.0)
    wait = REFRESH_COOLDOWN - (now - last)
    if wait > 0:
        return False, wait
    _refresh_cooldown[user_id] = now
    return True, 0.0


def can_cancel(requester_id: int, owner_id: int, admin_ids) -> bool:
    """Task owner or admin/owner may cancel. Nobody else."""
    try:
        if int(requester_id) == int(owner_id):
            return True
    except (TypeError, ValueError):
        pass
    try:
        return int(requester_id) in {int(a) for a in (admin_ids or [])}
    except (TypeError, ValueError):
        return False


async def set_page(chat_id: int, page: int) -> None:
    """Set the current pagination page for a chat."""
    async with _store_lock:
        if chat_id in _status_store:
            _status_store[chat_id]["page"] = max(1, int(page))


async def _edit_status(message, text: str, markup) -> bool:
    try:
        kwargs = {"disable_web_page_preview": True}
        if markup is not None:
            await message.edit_text(text, reply_markup=markup, **kwargs)
        else:
            await message.edit_text(text, **kwargs)
        return True
    except Exception as e:
        LOGGER.debug(f"status edit skipped: {e}")
        return False


async def render_and_refresh(chat_id: int, force: bool = False) -> None:
    """Render current tasks and edit the stored message if text changed."""
    async with _store_lock:
        session = _status_store.get(chat_id)
        if not session:
            return
        message = session["message"]
        last_text = session.get("last_text", "")
        current_page = session.get("page", 1)

    tasks = await task_manager.chat_tasks(chat_id)
    if not tasks:
        # Zero tasks left -> delete the status message immediately!
        async with _store_lock:
            session = _status_store.pop(chat_id, None)
        if session and session.get("message"):
            try:
                await session["message"].delete()
            except Exception:
                pass
        return

    counts = await task_manager.phase_counts(chat_id)
    dl_total = sum(
        _parse_speed(t.get("speed")) for t in tasks if t.get("phase") == "downloading"
    )
    ul_total = sum(
        _parse_speed(t.get("speed")) for t in tasks if t.get("phase") == "uploading"
    )
    footer = build_footer(system_snapshot(), dl_total, ul_total)

    total_tasks = len(tasks)
    total_pages = max(1, (total_tasks + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    if current_page > total_pages:
        current_page = total_pages
    if current_page < 1:
        current_page = 1

    start_idx = (current_page - 1) * TASKS_PER_PAGE
    end_idx = start_idx + TASKS_PER_PAGE
    page_tasks = tasks[start_idx:end_idx]

    full = render_status(
        page_tasks, counts, footer,
        page=current_page, total_pages=total_pages,
        total_tasks=total_tasks, start_idx=start_idx
    )
    text = fit_text(full, page_tasks, counts, footer, start_idx=start_idx)
    markup = build_buttons(current_page, total_pages)

    if text == last_text and not force:
        return  # unchanged -> skip edit (FloodWait-proof)
    ok = await _edit_status(message, text, markup)
    if ok:
        async with _store_lock:
            if chat_id in _status_store:
                _status_store[chat_id]["last_text"] = text
                _status_store[chat_id]["page"] = current_page


async def _worker(chat_id: int, interval: float = STATUS_EDIT_INTERVAL) -> None:
    """One worker per chat. Deletes the message the instant tasks hit zero."""
    try:
        while True:
            if not await task_manager.has_tasks(chat_id):
                # Zero tasks -> progress message is deleted immediately.
                async with _store_lock:
                    session = _status_store.pop(chat_id, None)
                if session is not None:
                    try:
                        await session["message"].delete()
                    except Exception:
                        pass
                return
            await render_and_refresh(chat_id)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        LOGGER.warning(f"status worker died for chat {chat_id}: {e}")
    finally:
        async with _store_lock:
            session = _status_store.get(chat_id)
            if session and session.get("worker") is asyncio.current_task():
                session["worker"] = None


async def ensure_worker(chat_id: int) -> None:
    """Start the per-chat worker if not running. Called on task register."""
    async with _store_lock:
        session = _status_store.get(chat_id)
        if not session or not session.get("message"):
            return
        worker = session.get("worker")
        if worker and not worker.done():
            return
        session["worker"] = asyncio.create_task(_worker(chat_id))


async def attach_message(chat_id: int, message, initial_text: str = "", page: int = 1) -> None:
    """Bind (or rebind) the live status message for a chat. Old one deleted."""
    old = None
    async with _store_lock:
        session = _status_store.get(chat_id)
        if session and session.get("message") is not message:
            old = session.get("message")
        _status_store[chat_id] = {
            "message": message,
            "last_text": initial_text,
            "worker": (session or {}).get("worker"),
            "page": page,
        }
    if old is not None:
        try:
            await old.delete()
        except Exception:
            pass
    await ensure_worker(chat_id)
    if not initial_text:
        await render_and_refresh(chat_id, force=True)


async def show_status_card(chat_id: int, reply_to_message=None) -> None:
    """Send a fresh live status message at the bottom of the chat, deleting any old one."""
    tasks = await task_manager.chat_tasks(chat_id)
    if not tasks:
        return

    async with _store_lock:
        session = _status_store.get(chat_id)
        current_page = (session.get("page", 1)) if session else 1
        old_msg = session.get("message") if session else None

    if old_msg is not None:
        try:
            await old_msg.delete()
        except Exception:
            pass

    counts = await task_manager.phase_counts(chat_id)
    dl_total = sum(
        _parse_speed(t.get("speed")) for t in tasks if t.get("phase") == "downloading"
    )
    ul_total = sum(
        _parse_speed(t.get("speed")) for t in tasks if t.get("phase") == "uploading"
    )
    footer = build_footer(system_snapshot(), dl_total, ul_total)

    total_tasks = len(tasks)
    total_pages = max(1, (total_tasks + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    if current_page > total_pages:
        current_page = total_pages
    if current_page < 1:
        current_page = 1

    start_idx = (current_page - 1) * TASKS_PER_PAGE
    end_idx = start_idx + TASKS_PER_PAGE
    page_tasks = tasks[start_idx:end_idx]

    full = render_status(
        page_tasks, counts, footer,
        page=current_page, total_pages=total_pages,
        total_tasks=total_tasks, start_idx=start_idx
    )
    text = fit_text(full, page_tasks, counts, footer, start_idx=start_idx)
    markup = build_buttons(current_page, total_pages)

    try:
        from bot import app
        thread_id = None
        if reply_to_message:
            thread_id = getattr(reply_to_message, "message_thread_id", None)
        kwargs = {"disable_web_page_preview": True, "reply_markup": markup}
        if thread_id:
            kwargs["message_thread_id"] = thread_id
        st = await app.send_message(chat_id, text, **kwargs)
        await attach_message(chat_id, st, initial_text=text, page=current_page)
    except Exception as ex:
        LOGGER.warning(f"Could not send new status message via app: {ex}")
        target = reply_to_message or (session.get("message") if session else None)
        if target:
            try:
                msg_obj = target.message if hasattr(target, "message") and not hasattr(target, "reply_text") else target
                st = await msg_obj.reply_text(text, reply_markup=markup, disable_web_page_preview=True)
                await attach_message(chat_id, st, initial_text=text, page=current_page)
                return
            except Exception:
                pass
        await render_and_refresh(chat_id, force=True)


async def announce_task(message) -> None:
    """Send (or rebind) the shared status message for a newly queued task.

    When a new task arrives, delete the old status message and post a fresh one
    at the bottom of the chat (NexonBots style). Never raises."""
    try:
        msg_obj = message.message if hasattr(message, "message") and not hasattr(message, "reply_text") else message
        await show_status_card(msg_obj.chat.id, reply_to_message=msg_obj)
    except Exception as e:
        LOGGER.warning(f"status announce failed: {e}")


async def drop_chat(chat_id: int) -> None:
    async with _store_lock:
        session = _status_store.pop(chat_id, None)
    if session is not None:
        worker = session.get("worker")
        if worker and not worker.done() and worker is not asyncio.current_task():
            worker.cancel()
        try:
            await session["message"].delete()
        except Exception:
            pass
