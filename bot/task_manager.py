# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# VideoUtil central task registry + concurrency slots.
#
# Design (locked spec):
#   - Every job gets an 8-char task ID -> per-task cancel via /c<id>.
#   - 3 separate semaphores: download(5) / heavy(1, shared by
#     encode+watermark+hardsub) / upload(1).
#   - Light ops (cut/crop/merge/audio/subs/...) take NO slot, they only
#     register (status + dedupe + cancel).
#   - Handoff is event-driven (asyncio.Semaphore): the instant a slot is
#     released the next waiter wakes up -- no polling loops anywhere.
#   - Dependency-free (stdlib only) so it can be unit-tested headless.

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager

LOGGER = logging.getLogger(__name__)

# --- Concurrency slots (tunable) ---
MAX_CONCURRENT_DOWNLOADS = 5
MAX_CONCURRENT_HEAVY = 1      # encode + watermark + hardsub share ONE slot
MAX_CONCURRENT_UPLOADS = 1

# Heavy operations: full re-encode, eat all CPU cores.
HEAVY_OPS = frozenset({"encode", "watermark", "hardsub"})

# Lifecycle phases shown on the shared status message.
PHASE_QUEUED = "queued"
PHASE_DOWNLOADING = "downloading"
PHASE_PROCESSING = "processing"
PHASE_SPLITTING = "splitting"
PHASE_UPLOADING = "uploading"
PHASE_DONE = "done"
PHASE_CANCELLED = "cancelled"


def new_task_id() -> str:
    """8-hex task ID used by /c<id> cancel."""
    return secrets.token_hex(4)


def build_dedupe_key(user_id: int, file_uid: str, op: str, params: str = "") -> str:
    """Same file + same operation pressed twice -> duplicate, not a new job."""
    return f"{user_id}:{file_uid}:{op}:{params}"


class TaskManager:
    def __init__(
        self,
        max_downloads: int = MAX_CONCURRENT_DOWNLOADS,
        max_heavy: int = MAX_CONCURRENT_HEAVY,
        max_uploads: int = MAX_CONCURRENT_UPLOADS,
    ):
        self._sem_dl = asyncio.Semaphore(max_downloads)
        self._sem_heavy = asyncio.Semaphore(max_heavy)
        self._sem_ul = asyncio.Semaphore(max_uploads)
        self._lock = asyncio.Lock()
        self._tasks: dict[str, dict] = {}
        self._active_dedupe: set[str] = set()
        self._seq = 0
        self._maintenance = False

    # -- registration -------------------------------------------------
    async def register(
        self,
        user_id: int,
        chat_id: int,
        op: str,
        title: str = "Media",
        dedupe_key: str | None = None,
        link: str = "",
        res: str = "",
    ) -> tuple[str | None, str]:
        """Atomically dedupe-check and register. Returns (task_id, error).

        error == '' on success; task_id is None when rejected.
        """
        async with self._lock:
            if self._maintenance:
                return None, "⚠️ Network maintenance running. Try again in a bit."
            if dedupe_key and dedupe_key in self._active_dedupe:
                return None, "⚠️ Same task is already running. Wait for it to finish."
            self._seq += 1
            task_id = new_task_id()
            while task_id in self._tasks:  # paranoia: avoid the ~1-in-4bn clash
                task_id = new_task_id()
            self._tasks[task_id] = {
                "task_id": task_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "op": op,
                "title": str(title or "Media")[:80],
                "link": str(link or ""),
                "res": str(res or ""),
                "phase": PHASE_QUEUED,
                "seq": self._seq,
                "dedupe_key": dedupe_key,
                "cancel_event": asyncio.Event(),
                "processes": [],
                "created_at": time.time(),
                # Live progress snapshot (written by workers, read by status):
                "percent": 0.0,
                "speed": "",
                "eta": "",
                "detail": "",
                "done_bytes": 0.0,
                "total_bytes": 0.0,
            }
            if dedupe_key:
                self._active_dedupe.add(dedupe_key)
            LOGGER.info(f"Task {task_id} registered: op={op} user={user_id} chat={chat_id}")
            return task_id, ""

    async def complete(self, task_id: str) -> None:
        """Idempotent: frees dedupe key + registry entry. Call in finally."""
        async with self._lock:
            entry = self._tasks.pop(task_id, None)
            if entry and entry.get("dedupe_key"):
                self._active_dedupe.discard(entry["dedupe_key"])
            if entry:
                LOGGER.info(f"Task {task_id} completed/freed.")

    # -- slots (event-driven handoff, no polling) ----------------------
    @asynccontextmanager
    async def download_slot(self, task_id: str):
        await self._sem_dl.acquire()
        try:
            yield
        finally:
            self._sem_dl.release()

    @asynccontextmanager
    async def heavy_slot(self, task_id: str):
        await self._sem_heavy.acquire()
        try:
            yield
        finally:
            self._sem_heavy.release()

    @asynccontextmanager
    async def upload_slot(self, task_id: str):
        await self._sem_ul.acquire()
        try:
            yield
        finally:
            self._sem_ul.release()

    async def acquire_heavy(self) -> None:
        """Manual acquire for sections that can't use `async with`
        (avoids re-indenting large legacy blocks). Pair with release_heavy."""
        await self._sem_heavy.acquire()

    def release_heavy(self) -> None:
        try:
            self._sem_heavy.release()
        except ValueError:
            pass  # already released (double-complete safety)

    # -- phase + progress snapshot -------------------------------------
    async def set_phase(self, task_id: str, phase: str) -> None:
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["phase"] = phase

    async def update_progress(
        self,
        task_id: str,
        percent: float | None = None,
        speed: str | None = None,
        eta: str | None = None,
        detail: str | None = None,
        done_bytes: float | None = None,
        total_bytes: float | None = None,
        res: str | None = None,
        engine: str | None = None,
        mode_extra: str | None = None,
    ) -> None:
        async with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return
            if percent is not None:
                entry["percent"] = max(0.0, min(100.0, float(percent)))
            if speed is not None:
                entry["speed"] = str(speed)
            if eta is not None:
                entry["eta"] = str(eta)
            if detail is not None:
                entry["detail"] = str(detail)
            if done_bytes is not None:
                entry["done_bytes"] = max(0.0, float(done_bytes))
            if total_bytes is not None:
                entry["total_bytes"] = max(0.0, float(total_bytes))
            if res is not None:
                entry["res"] = str(res)
            if engine is not None:
                entry["engine"] = str(engine)
            if mode_extra is not None:
                entry["mode_extra"] = str(mode_extra)

    # -- cancellation ---------------------------------------------------
    def register_process(self, task_id: str, process) -> None:
        """Attach a running ffmpeg/subprocess so cancel can kill it instantly."""
        entry = self._tasks.get(task_id)
        if entry is not None:
            entry["processes"].append(process)

    def is_cancelled(self, task_id: str) -> bool:
        entry = self._tasks.get(task_id)
        return bool(entry and entry["cancel_event"].is_set())

    async def cancel_task(self, task_id: str) -> bool:
        was_queued = False
        async with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return False
            was_queued = (entry.get("phase") == PHASE_QUEUED)
            entry["cancel_event"].set()
            entry["phase"] = PHASE_CANCELLED
            if entry.get("dedupe_key"):
                self._active_dedupe.discard(entry["dedupe_key"])
        for proc in entry.get("processes", []):
            try:
                proc.kill()
                LOGGER.info(f"Killed subprocess of cancelled task {task_id}")
            except Exception:
                pass
        self.prune_queue(task_id)
        if was_queued:
            await self.complete(task_id)
        return True

    def prune_queue(self, task_id: str) -> None:
        """Purge task_id immediately from any in-memory waiting queues."""
        import sys
        try:
            from bot import data, data1, data2, data3, data4, data5, data6, data7, crop
            for q in (data, data1, data2, data3, data4, data5, data6, data7, crop):
                i = len(q) - 1
                while i >= 0:
                    item = q[i]
                    tid = None
                    if isinstance(item, (tuple, list)) and len(item) > 0:
                        tid = item[-1] if isinstance(item[-1], str) else (item[3] if len(item) >= 4 and isinstance(item[3], str) else None)
                    elif isinstance(item, str):
                        tid = item
                    if tid == task_id:
                        del q[i]
                    i -= 1
        except Exception as e:
            LOGGER.warning(f"Error pruning core queues: {e}")

        module_queue_map = [
            ("bot.watermark", ["watermark_queue"]),
            ("bot.split_videos", ["cut_queue"]),
            ("bot.merge_video", ["merge_queue"]),
            ("bot.subtitles", ["subtitle_queue", "hardsub_queue", "extractsub_queue", "rsub_queue"]),
            ("bot.audio", ["extractaudio_queue", "remaudio_queue", "audio_queue", "addaudio_queue"]),
        ]
        for mod_name, q_names in module_queue_map:
            mod = sys.modules.get(mod_name)
            if mod:
                for qn in q_names:
                    q = getattr(mod, qn, None)
                    if isinstance(q, list):
                        i = len(q) - 1
                        while i >= 0:
                            item = q[i]
                            tid = None
                            if isinstance(item, (tuple, list)) and len(item) > 0:
                                tid = item[-1] if isinstance(item[-1], str) else (item[2] if len(item) >= 3 and isinstance(item[2], str) else None)
                            elif isinstance(item, str):
                                tid = item
                            if tid == task_id:
                                del q[i]
                            i -= 1

    async def cancel_user_tasks(self, user_id: int, chat_id: int | None = None) -> int:
        tids = [
            tid
            for tid, e in self._tasks.items()
            if e["user_id"] == user_id
            and (chat_id is None or e["chat_id"] == chat_id)
            and not e["cancel_event"].is_set()
            and e["phase"] != PHASE_CANCELLED
        ]
        for tid in tids:
            await self.cancel_task(tid)
        return len(tids)

    # -- views for the status renderer ----------------------------------
    async def chat_tasks(self, chat_id: int) -> list[dict]:
        # Cancelled-but-not-yet-finished tasks are included: the status card
        # must show them as "Cancelling…" until the worker actually stops.
        async with self._lock:
            return sorted(
                (
                    dict(e, processes=None, cancel_event=None)
                    for e in self._tasks.values()
                    if e["chat_id"] == chat_id
                ),
                key=lambda e: e["seq"],
            )

    async def get_task(self, task_id: str) -> dict | None:
        async with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return None
            return {
                "task_id": entry["task_id"],
                "user_id": entry["user_id"],
                "chat_id": entry["chat_id"],
                "op": entry["op"],
                "phase": entry["phase"],
                "is_cancelled": entry["cancel_event"].is_set() or entry["phase"] == PHASE_CANCELLED,
            }

    async def live_position(self, task_id: str) -> int:
        """1-based FIFO position among active tasks (for 'Global #n')."""
        async with self._lock:
            entry = self._tasks.get(task_id)
            if not entry or entry["cancel_event"].is_set() or entry["phase"] == PHASE_CANCELLED:
                return 0
            return 1 + sum(
                1 for e in self._tasks.values()
                if e["seq"] < entry["seq"]
                and not e["cancel_event"].is_set()
                and e["phase"] != PHASE_CANCELLED
            )

    async def phase_counts(self, chat_id: int | None = None) -> dict[str, int]:
        async with self._lock:
            counts = {"queued": 0, "downloading": 0, "processing": 0, "uploading": 0}
            for e in self._tasks.values():
                if chat_id is not None and e["chat_id"] != chat_id:
                    continue
                if e["cancel_event"].is_set() or e["phase"] == PHASE_CANCELLED:
                    continue
                if e["phase"] in counts:
                    counts[e["phase"]] += 1
            return counts

    async def has_tasks(self, chat_id: int | None = None) -> bool:
        # Includes cancelled-but-running tasks so the status message survives
        # (showing "Cancelling…") instead of vanishing on the first /c.
        async with self._lock:
            if chat_id is None:
                return bool(self._tasks)
            return any(
                e["chat_id"] == chat_id
                for e in self._tasks.values()
            )

    # -- maintenance (speedtest) ----------------------------------------
    async def try_begin_maintenance(self) -> bool:
        async with self._lock:
            if self._maintenance or self._tasks:
                return False
            self._maintenance = True
            return True

    async def end_maintenance(self) -> None:
        async with self._lock:
            self._maintenance = False


# Global instance used by all bot modules.
task_manager = TaskManager()

def prune_queue_task(task_id: str) -> None:
    task_manager.prune_queue(task_id)
