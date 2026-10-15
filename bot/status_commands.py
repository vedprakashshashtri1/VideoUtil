# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
# Phase 3a — status commands + status buttons.
#
#   /status, /queue    show the ONE shared live status message for this chat (NexonBots)
#   /c<taskid>         cancel a task (task owner or admin only)
#   /cancelall         cancel all tasks in this chat (admin only)
#   [Refresh]/[Close]  status-message buttons (close = admin only)
#   [Prev]/[Next]      pagination buttons when tasks > TASKS_PER_PAGE

import asyncio
import html
import re

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from bot import app, AUTH_USERS, BOT_USERNAME, LOGGER
from bot.task_manager import task_manager, PHASE_CANCELLED
from bot.group_status import (
    show_status_card,
    render_and_refresh,
    drop_chat,
    refresh_allowed,
    can_cancel,
    set_page,
)

_CANCEL_RE = re.compile(r"^/c_?\s?([0-9a-fA-F]{8})\b")


def _is_admin(user_id: int) -> bool:
    try:
        return int(user_id) in {int(a) for a in AUTH_USERS}
    except (TypeError, ValueError):
        return False


@app.on_message(filters.command(["status", f"status@{BOT_USERNAME}", "queue", f"queue@{BOT_USERNAME}"]))
async def status_or_queue_command(client: Client, message: Message):
    chat_id = message.chat.id
    if not await task_manager.has_tasks(chat_id):
        m = await message.reply_text("📭 <b>No active tasks.</b>")
        await asyncio.sleep(6)
        try:
            await m.delete()
            await message.delete()
        except Exception:
            pass
        return

    await show_status_card(chat_id, reply_to_message=message)
    try:
        await message.delete()
    except Exception:
        pass


@app.on_message(filters.regex(r"^/c_?\s?[0-9a-fA-F]{8}\b") & (filters.private | filters.group))
async def cancel_task_command(client: Client, message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    m = _CANCEL_RE.match((message.text or "").strip())
    if not m:
        return await message.reply_text("❌ Usage: <code>/c_153e8551</code>")
    task_id = m.group(1).lower()
    task = await task_manager.get_task(task_id)
    if not task or task.get("is_cancelled") or task.get("phase") == PHASE_CANCELLED:
        return await message.reply_text("❌ <b>Task not found.</b> Already finished or cancelled.")
    if not can_cancel(user_id, task["user_id"], AUTH_USERS):
        return await message.reply_text("⛔ Only the task owner or an admin can cancel it.")
    ok = await task_manager.cancel_task(task_id)
    if ok:
        name = html.escape(message.from_user.first_name or "User")
        confirm = await message.reply_text(
            f"🛑 <b>Task Cancelled</b> <code>{task_id}</code> by "
            f"<a href='tg://user?id={user_id}'>{name}</a>"
        )
        await render_and_refresh(message.chat.id, force=True)
        try:
            await message.delete()
        except Exception:
            pass
        await asyncio.sleep(5)
        try:
            await confirm.delete()
        except Exception:
            pass
    else:
        await message.reply_text("❌ Could not cancel (already gone).")


@app.on_message(filters.command(["cancelall", f"cancelall@{BOT_USERNAME}"]))
async def cancelall_command(client: Client, message: Message):
    if not message.from_user or not _is_admin(message.from_user.id):
        return await message.reply_text("⛔ Admin only.")
    tids = [
        t["task_id"]
        for t in await task_manager.chat_tasks(message.chat.id)
        if t.get("phase") != PHASE_CANCELLED
    ]
    for tid in tids:
        await task_manager.cancel_task(tid)
    m = await message.reply_text(f"🛑 Cancelled <b>{len(tids)}</b> task(s).")
    await render_and_refresh(message.chat.id, force=True)
    try:
        await message.delete()
    except Exception:
        pass
    await asyncio.sleep(5)
    try:
        await m.delete()
    except Exception:
        pass


async def handle_status_callback(client: Client, query, user_id: int):
    """Status-button entry, called by the single shared callback dispatcher
    in call_back_button_handler.py (vst* prefix). NOT registered separately."""
    data = getattr(query, "data", "") or ""
    user_id = int(getattr(query.from_user, "id", user_id) or user_id)
    chat_id = query.message.chat.id
    if data == "vst_ref":
        allowed, wait = refresh_allowed(user_id)
        if not allowed:
            return await query.answer(f"Already refreshed! Try after {wait:.0f}s.", show_alert=True)
        await query.answer("Refreshing…", show_alert=False)
        await render_and_refresh(chat_id, force=True)
    elif data == "vst_close":
        if not _is_admin(user_id):
            return await query.answer("⛔ Admin only.", show_alert=True)
        await query.answer("Closed.", show_alert=False)
        await drop_chat(chat_id)
    elif data.startswith("vst_page:"):
        page_arg = data.split(":")[1]
        if page_arg == "noop":
            return await query.answer()
        try:
            page_num = int(page_arg)
            await set_page(chat_id, page_num)
            await render_and_refresh(chat_id, force=True)
            await query.answer()
        except Exception:
            await query.answer()
    else:
        await query.answer()
