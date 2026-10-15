# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Validated, persistent encoding settings with an inline Telegram UI."""

import asyncio
import html
import re

from pyrogram import filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardMarkup
from bot.button_styles import InlineKeyboardButton

from bot import AUTH_USERS, BOT_USERNAME, LOGGER, app, audio_b, codec, crf, preset
from bot.helper_funcs import gdrive as gdrive_api
from bot.localisation import Localisation
from database import db


DEFAULT_SETTINGS = {
    "codec": "libx264",
    "crf": "30",
    "preset": "veryfast",
    "audio_bitrate": "64k",
}

CODECS = ("libx264", "libx265")
CRF_VALUES = ("18", "23", "28", "30", "35")
PRESETS = ("ultrafast", "veryfast", "fast", "medium", "slow")
AUDIO_BITRATES = ("64k", "96k", "128k", "192k", "320k")


def current_settings():
    return {
        "codec": codec[0] if codec else DEFAULT_SETTINGS["codec"],
        "crf": crf[0] if crf else DEFAULT_SETTINGS["crf"],
        "preset": preset[0] if preset else DEFAULT_SETTINGS["preset"],
        "audio_bitrate": audio_b[0] if audio_b else DEFAULT_SETTINGS["audio_bitrate"],
    }


def apply_settings(values):
    merged = {**DEFAULT_SETTINGS, **values}
    codec[:] = [str(merged["codec"])]
    crf[:] = [str(merged["crf"])]
    preset[:] = [str(merged["preset"])]
    audio_b[:] = [str(merged["audio_bitrate"])]


async def save_settings():
    try:
        await db.set_encoding_settings(current_settings())
        return True
    except Exception as error:
        LOGGER.error("Unable to persist encoding settings: %s", error)
        return False


async def load_encoding_settings():
    try:
        stored = await db.get_encoding_settings()
    except Exception as error:
        LOGGER.error("Unable to load encoding settings; using defaults: %s", error)
        stored = {}
    valid = {
        key: stored[key]
        for key in DEFAULT_SETTINGS
        if key in stored
    }
    apply_settings(valid)


def settings_text(values=None, changed=None):
    values = values or current_settings()
    heading = "✅ <b>Setting updated successfully!</b>\n\n" if changed else ""
    return (
        f"{heading}"
        "🎬 <b>Video Encoding Settings</b>\n"
        "<blockquote><b>The current settings will be added to your video file:</b></blockquote>\n"
        f"🎞 <b>Codec:</b> <code>{values['codec']}</code>\n"
        f"🎚 <b>CRF:</b> <code>{values['crf']}</code>\n"
        f"⚡ <b>Preset:</b> <code>{values['preset']}</code>\n"
        f"🔊 <b>Audio bitrate:</b> <code>{values['audio_bitrate']}</code>\n\n"
        "<i>Lower CRF = better quality and larger file.</i>"
    )


def option_button(label, field, value, selected, owner_id):
    mark = " ✅" if value == selected else ""
    return InlineKeyboardButton(
        f"{label}{mark}",
        callback_data=f"encset:{owner_id}:{field}:{value}",
    )


def settings_keyboard(owner_id):
    values = current_settings()
    return InlineKeyboardMarkup([
        [
            option_button("H.264", "codec", "libx264", values["codec"], owner_id),
            option_button("H.265", "codec", "libx265", values["codec"], owner_id),
        ],
        [
            option_button(value, "crf", value, values["crf"], owner_id)
            for value in CRF_VALUES
        ],
        [
            option_button("Ultra", "preset", "ultrafast", values["preset"], owner_id),
            option_button("Veryfast", "preset", "veryfast", values["preset"], owner_id),
            option_button("Fast", "preset", "fast", values["preset"], owner_id),
        ],
        [
            option_button("Medium", "preset", "medium", values["preset"], owner_id),
            option_button("Slow", "preset", "slow", values["preset"], owner_id),
        ],
        [
            option_button(value, "audio_bitrate", value, values["audio_bitrate"], owner_id)
            for value in AUDIO_BITRATES[:3]
        ],
        [
            option_button(value, "audio_bitrate", value, values["audio_bitrate"], owner_id)
            for value in AUDIO_BITRATES[3:]
        ],
        [
            InlineKeyboardButton(
                "↩️ Reset to Default",
                callback_data=f"encset:{owner_id}:reset:default",
            )
        ],
        [
            InlineKeyboardButton("‹ Personal Settings", callback_data=f"userset:{owner_id}:home"),
            InlineKeyboardButton("✖️ Close", callback_data="close"),
        ],
    ])


def _selected(label, selected):
    return f"{label} ✓" if selected else label


def personal_settings_text(state, changed=None):
    heading = f"✅ <b>{changed}</b>\n\n" if changed else ""
    thumbnail = "Saved" if state["has_thumbnail"] else "Not set"
    watermark = "Saved" if state["has_watermark"] else "Not set"
    channel = str(state["channel_id"]) if state["channel_id"] else "Not set"
    split_mode_label = "Binary Split" if state.get("split_mode") == "binary" else "Normal Split"
    return (
        f"{heading}"
        "⚙️ <b>Personal Settings</b>\n"
        "<blockquote>These preferences are saved separately for your Telegram account.</blockquote>\n"
        f"🎬 <b>Send video as:</b> <code>{state['media'].title()}</code>\n"
        f"✂️ <b>Split mode:</b> <code>{split_mode_label}</code>\n"
        f"🙈 <b>Spoiler:</b> <code>{'On' if state['spoiler'] else 'Off'}</code>\n"
        f"📤 <b>Upload destination:</b> <code>{state['upload'].title()}</code>\n"
        f"📍 <b>Upload location:</b> <code>{'Google Drive' if state.get('location') == 'gdrive' else 'Telegram'}</code>\n"
        f"🏷️ <b>Metadata:</b> <code>{state['metadata'].title()}</code>\n"
        f"🖼️ <b>Thumbnail:</b> <code>{thumbnail}</code>\n"
        f"💧 <b>Watermark:</b> <code>{watermark}</code>\n"
        f"📢 <b>Upload channel:</b> <code>{channel}</code>\n\n"
        "<i>Default: Video · Normal Split · Spoiler Off · This Group · Telegram</i>"
    )


def personal_settings_keyboard(owner_id, state, is_admin=False):
    upload = state["upload"]
    split_mode = state.get("split_mode", "normal")
    location = state.get("location", "telegram")
    buttons = [
        [
            InlineKeyboardButton(
                _selected("🎬 Video", state["media"] == "video"),
                callback_data=f"userset:{owner_id}:media:video",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                _selected("📄 Document", state["media"] == "document"),
                callback_data=f"userset:{owner_id}:media:document",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                _selected("✂️ Normal Split", split_mode == "normal"),
                callback_data=f"userset:{owner_id}:split:normal",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                _selected("📦 Binary Split", split_mode == "binary"),
                callback_data=f"userset:{owner_id}:split:binary",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                _selected("Spoiler On", state["spoiler"]),
                callback_data=f"userset:{owner_id}:spoiler:on",
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                _selected("Spoiler Off", not state["spoiler"]),
                callback_data=f"userset:{owner_id}:spoiler:off",
                style=ButtonStyle.DANGER,
            ),
        ],
        [
            InlineKeyboardButton(
                _selected("This Group", upload == "group"),
                callback_data=f"userset:{owner_id}:upload:group",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                _selected("DM", upload == "dm"),
                callback_data=f"userset:{owner_id}:upload:dm",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                _selected("Channel", upload == "channel"),
                callback_data=f"userset:{owner_id}:upload:channel",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                _selected("📍 Telegram", location == "telegram"),
                callback_data=f"userset:{owner_id}:location:telegram",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                _selected("☁️ Google Drive", location == "gdrive"),
                callback_data=f"userset:{owner_id}:location:gdrive",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                _selected("Metadata On", state["metadata"].lower() == "on"),
                callback_data=f"userset:{owner_id}:metadata:on",
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                _selected("Metadata Off", state["metadata"].lower() != "on"),
                callback_data=f"userset:{owner_id}:metadata:off",
                style=ButtonStyle.DANGER,
            ),
        ],
        [
            InlineKeyboardButton("🖼️ Thumbnail", callback_data=f"userset:{owner_id}:thumbnail:view"),
            InlineKeyboardButton("💧 Watermark", callback_data=f"userset:{owner_id}:watermark:help"),
        ],
        [InlineKeyboardButton("📢 Upload Channel", callback_data=f"userset:{owner_id}:channel:help")],
        [InlineKeyboardButton("🛠️ Custom Google Drive setup", callback_data=f"userset:{owner_id}:gdrive:view")],
    ]
    if state["has_thumbnail"]:
        buttons.append([
            InlineKeyboardButton(
                "Delete Thumbnail",
                callback_data=f"userset:{owner_id}:thumbnail:delete",
                style=ButtonStyle.DANGER,
            )
        ])
    if state["has_watermark"]:
        buttons.append([
            InlineKeyboardButton(
                "Delete Watermark",
                callback_data=f"userset:{owner_id}:watermark:delete",
                style=ButtonStyle.DANGER,
            )
        ])
    if is_admin:
        buttons.append([
            InlineKeyboardButton("🎞️ Encoding Settings", callback_data=f"userset:{owner_id}:encoding")
        ])
    buttons.append([InlineKeyboardButton("✖️ Close", callback_data="close")])
    return InlineKeyboardMarkup(buttons)


# ==================== GOOGLE DRIVE CONNECTION PANEL ====================
_GDRIVE_UI = {}  # user_id -> {"message", "task", "done", "stale"}


async def _gdrive_state(user_id):
    state = await db.get_gdrive_settings(user_id)
    state["connected"] = await gdrive_api.is_connected(user_id)
    return state


def gdrive_panel_text(state, changed=None, alert=False, oauth_ready=True, auto_ok=True):
    heading = f"{'⚠️' if alert else '✅'} <b>{html.escape(changed)}</b>\n\n" if changed else ""
    auto = "Enabled" if state.get("auto_folder", True) else "Disabled"
    own = "ON" if state.get("own_drive") else "OFF"
    parent = state.get("parent_folder") or ""
    parent_line = f"<code>{html.escape(parent)}</code>" if parent else "My Drive Root (Auto)"
    if state.get("connected"):
        login = html.escape(state.get("email") or "Connected")
        intro = "✅ Your Google Drive is connected.\n"
    elif not oauth_ready:
        login = "Not connected"
        intro = (
            "The bot owner has not set up Google Drive yet.\n"
            "<i>GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET are missing in secrets.</i>"
        )
    elif auto_ok:
        login = "Not connected"
        intro = (
            "Click the button below to connect your Google Drive.\n"
            "A browser page will open — log in and grant access.\n\n"
            "The bot will automatically confirm once done.\n\n"
            "<i>No code pasting required!</i>"
        )
    else:
        login = "Not connected"
        intro = (
            "Click the button below to connect your Google Drive.\n"
            "A browser page will open — log in and grant access.\n\n"
            "<i>After logging in, copy the link from your browser's address "
            "bar and paste it here.</i>"
        )
    return (
        f"{heading}"
        "🔑 <b>Google Drive Connection</b>\n\n"
        f"{intro}\n\n"
        f"• <b>Drive Login:</b> <code>{login}</code>\n"
        f"• <b>Auto Folder Creation:</b> <code>{auto}</code>\n"
        f"• <b>Default Parent:</b> {parent_line}\n"
        f"• <b>Own Drive:</b> <code>{own}</code>\n"
        "<i>Leech: Drive file/folder links work for everyone - no connection needed.</i>"
    )


def gdrive_panel_keyboard(owner_id, state, auth_url=None):
    rows = []
    if state.get("connected"):
        if auth_url:
            rows.append([InlineKeyboardButton("🔄 Switch Account ↗", url=auth_url)])
        rows.append([InlineKeyboardButton(
            "🔌 Disconnect Drive",
            callback_data=f"userset:{owner_id}:gdrive:disconnect",
            style=ButtonStyle.DANGER,
        )])
    elif auth_url:
        rows.append([InlineKeyboardButton("🔗 Authorize Google Drive ↗", url=auth_url)])
    else:
        rows.append([InlineKeyboardButton(
            "➕ Connect Google Drive",
            callback_data=f"userset:{owner_id}:gdrive:connect",
        )])
    rows.append([
        InlineKeyboardButton(
            f"Auto Folder: {'ON' if state.get('auto_folder', True) else 'OFF'}",
            callback_data=f"userset:{owner_id}:gdrive:autofolder",
        ),
        InlineKeyboardButton(
            f"Own Drive: {'ON' if state.get('own_drive') else 'OFF'}",
            callback_data=f"userset:{owner_id}:gdrive:owndrive",
        ),
    ])
    rows.append([InlineKeyboardButton(
        "📁 Default Parent Folder",
        callback_data=f"userset:{owner_id}:gdrive:parent",
    )])
    rows.append([
        InlineKeyboardButton("‹ Personal Settings", callback_data=f"userset:{owner_id}:home"),
        InlineKeyboardButton("✖️ Close", callback_data="close"),
    ])
    return InlineKeyboardMarkup(rows)


def _stale_gdrive_ui(user_id):
    ui = _GDRIVE_UI.get(int(user_id))
    if not ui:
        return
    ui["stale"] = True
    task = ui.get("task")
    if task and not task.done():
        task.cancel()


def _cancel_gdrive_wait(user_id):
    ui = _GDRIVE_UI.get(int(user_id))
    if not ui:
        return
    task = ui.get("task")
    if task and not task.done():
        task.cancel()


def _arm_wait_notice(message, user_id, ui):
    async def _later():
        try:
            await asyncio.sleep(45)
        except asyncio.CancelledError:
            return
        if ui.get("done") or ui.get("stale"):
            return
        try:
            await message.reply_text(
                "⏳ <b>Still waiting for Google…</b>\n\n"
                "If the browser page did not confirm, copy the link from your "
                "browser's address bar (it starts with <code>http://localhost</code>) "
                "and paste it here."
            )
        except Exception:
            pass

    ui["task"] = asyncio.create_task(_later())


async def render_gdrive_panel(message, user_id, changed=None, alert=False, arm=False):
    state = await _gdrive_state(user_id)
    oauth_ready = gdrive_api.oauth_configured()
    auth_url, auto_ok = None, True
    if oauth_ready:
        try:
            auth_url, auto_ok = await gdrive_api.begin_connect(user_id)
        except Exception as e:
            LOGGER.warning("[GDrive] could not start connect session: %s", e)
            auth_url = None
    ui = {"message": message, "task": None, "done": False, "stale": False}
    _GDRIVE_UI[int(user_id)] = ui
    if arm and auth_url and not state.get("connected"):
        _arm_wait_notice(message, user_id, ui)
    await _safe_edit(
        message,
        gdrive_panel_text(state, changed=changed, alert=alert,
                          oauth_ready=oauth_ready, auto_ok=auto_ok),
        reply_markup=gdrive_panel_keyboard(user_id, state, auth_url=auth_url),
    )


async def _gdrive_result(user_id, ok, detail):
    uid = int(user_id)
    ui = _GDRIVE_UI.get(uid)
    if ui:
        ui["done"] = True
        _cancel_gdrive_wait(uid)
    if ok:
        await db.set_gdrive_setting(uid, "email", detail or "")
        note = f"Google Drive connected as {detail}" if detail else "Google Drive connected"
        if ui and not ui.get("stale"):
            await render_gdrive_panel(ui["message"], uid, changed=note)
        elif ui:
            try:
                await ui["message"].reply_text(f"✅ <b>{html.escape(note)}</b>")
            except Exception:
                pass
    else:
        err = str(detail or "unknown error")
        if ui and not ui.get("stale"):
            await render_gdrive_panel(
                ui["message"], uid,
                changed=f"Could not connect: {err}", alert=True,
            )
        elif ui:
            try:
                await ui["message"].reply_text(f"⚠️ <b>Google Drive:</b> {html.escape(err)}")
            except Exception:
                pass


async def _gdrive_set_parent(query, user_id):
    ask = await query.message.reply_text(
        "📁 <b>Default Parent Folder</b>\n\n"
        "Send your Drive <b>folder</b> link or folder ID.\n"
        "Send <code>/skip</code> to use My Drive Root (Auto)."
    )
    try:
        incoming = await app.listen(
            chat_id=query.message.chat.id, user_id=user_id, timeout=60
        )
        text = (incoming.text or "").strip()
    except Exception:
        return await ask.edit_text("⌛ Timed out. Open the panel again to set the folder.")
    try:
        await incoming.delete()
    except Exception:
        pass
    if text.lower() in ("/skip", "skip"):
        await db.set_gdrive_setting(user_id, "parent_folder", "")
        notice = "Default parent set to My Drive Root (Auto)"
    else:
        kind, folder_id = gdrive_api.parse_drive_url(text)
        if kind != "folder" and re.fullmatch(r"[A-Za-z0-9_-]{20,}", text or ""):
            kind, folder_id = "folder", text
        if kind != "folder":
            return await ask.edit_text(
                "⚠️ That does not look like a Drive folder link. Open the panel and try again."
            )
        try:
            mime = await gdrive_api.drive_mime(folder_id, user_id)
        except Exception as err:
            return await ask.edit_text(f"⚠️ {html.escape(str(err))}")
        if mime != "application/vnd.google-apps.folder":
            return await ask.edit_text("⚠️ That link points to a file, not a folder.")
        await db.set_gdrive_setting(user_id, "parent_folder", folder_id)
        notice = "Default parent folder saved"
    try:
        await ask.delete()
    except Exception:
        pass
    await render_gdrive_panel(query.message, user_id, changed=notice)


async def _gdrive_action(query, user_id, action):
    if action == "view":
        await query.answer()
        return await render_gdrive_panel(query.message, user_id, arm=True)

    if action == "connect":
        return await query.answer(
            "The bot owner must set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET "
            "in the hosting secrets first.",
            show_alert=True,
        )

    if action == "disconnect":
        _cancel_gdrive_wait(user_id)
        await gdrive_api.disconnect_drive(user_id)
        await db.set_gdrive_setting(user_id, "email", "")
        await query.answer("✅ Google Drive disconnected")
        return await render_gdrive_panel(
            query.message, user_id, changed="Google Drive disconnected"
        )

    if action == "autofolder":
        state = await db.get_gdrive_settings(user_id)
        value = not state.get("auto_folder", True)
        await db.set_gdrive_setting(user_id, "auto_folder", value)
        notice = f"Auto Folder Creation {'enabled' if value else 'disabled'}"
        await query.answer(f"✅ {notice}")
        return await render_gdrive_panel(query.message, user_id, changed=notice)

    if action == "owndrive":
        state = await db.get_gdrive_settings(user_id)
        value = not state.get("own_drive", False)
        await db.set_gdrive_setting(user_id, "own_drive", value)
        notice = (
            "Own Drive ON - saved: uploads will target your Drive (Drive upload ships with next update)"
            if value else
            "Own Drive OFF - saved: uploads will target the bot default Drive (Drive upload ships with next update)"
        )
        await query.answer(f"✅ {notice}")
        return await render_gdrive_panel(query.message, user_id, changed=notice)

    if action == "parent":
        await query.answer()
        return await _gdrive_set_parent(query, user_id)

    return await query.answer("Unsupported settings action.", show_alert=True)


async def get_personal_settings(user_id):
    await db.ensure_user_defaults(user_id)
    media, split_mode, spoiler, upload, metadata, thumbnail, watermark, channel_id, location = await asyncio.gather(
        db.get_media_preference(user_id),
        db.get_split_mode(user_id),
        db.get_user_spoiler(user_id),
        db.get_upload_preference(user_id),
        db.get_metadata(user_id),
        db.get_thumbnail(user_id),
        db.get_watermark(user_id),
        db.get_user_channel(user_id),
        db.get_upload_location(user_id),
    )
    return {
        "media": media or "video",
        "split_mode": split_mode or "normal",
        "spoiler": bool(spoiler),
        "upload": upload or "group",
        "metadata": metadata or "Off",
        "thumbnail": thumbnail,
        "has_thumbnail": bool(thumbnail),
        "watermark": watermark,
        "has_watermark": bool(watermark),
        "channel_id": channel_id,
        "location": location or "telegram",
    }


def _personal_settings_allowed(user_id, chat_id):
    # SECURITY: personal settings are per-user - any authorized sender or chat id
    # opens their OWN panel only (callback enforces from_user == owner). The
    # encoding section stays AUTH_USERS-only via the keyboard + callback check.
    return user_id in AUTH_USERS or chat_id in AUTH_USERS


async def _safe_edit(message, text, reply_markup=None):
    try:
        return await message.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        return None
    except RPCError as e:
        LOGGER.warning(f"[Settings] edit failed: {e}")
        return None


async def render_personal_settings(message, owner_id, changed=None):
    _stale_gdrive_ui(owner_id)
    state = await get_personal_settings(owner_id)
    await _safe_edit(
        message,
        personal_settings_text(state, changed=changed),
        reply_markup=personal_settings_keyboard(owner_id, state, owner_id in AUTH_USERS),
    )


async def require_admin(message):
    if not message.from_user or message.from_user.id not in AUTH_USERS:
        await message.reply_text(Localisation.NOT_AUTH)
        return False
    return True


async def update_field(message, field, value):
    if not await require_admin(message):
        return
    apply_settings({field: value})
    await save_settings()
    await message.reply_text(settings_text(changed=field), reply_markup=settings_keyboard(message.from_user.id))


@app.on_message(filters.incoming & filters.command(["settings", f"settings@{BOT_USERNAME}"]))
async def show_encoding_settings(_, message):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id or not _personal_settings_allowed(user_id, message.chat.id):
        return await message.reply_text(Localisation.NOT_AUTH)
    _stale_gdrive_ui(user_id)
    state = await get_personal_settings(user_id)
    await message.reply_text(
        personal_settings_text(state),
        reply_markup=personal_settings_keyboard(user_id, state, user_id in AUTH_USERS),
    )


@app.on_message(filters.incoming & filters.command(["encsettings", f"encsettings@{BOT_USERNAME}"]))
async def show_encoding_panel(_, message):
    if not await require_admin(message):
        return
    await message.reply_text(settings_text(), reply_markup=settings_keyboard(message.from_user.id))


@app.on_message(filters.incoming & filters.command([
    "resetsettings",
    "reset_settings",
    f"resetsettings@{BOT_USERNAME}",
    f"reset_settings@{BOT_USERNAME}",
]))
async def reset_encoding_settings(_, message):
    if not await require_admin(message):
        return
    apply_settings(DEFAULT_SETTINGS)
    await save_settings()
    await message.reply_text(
        "↩️ <b>Encoding settings reset to default.</b>\n\n" + settings_text(),
        reply_markup=settings_keyboard(message.from_user.id),
    )


@app.on_message(filters.incoming & filters.command(["codec", f"codec@{BOT_USERNAME}"]))
async def change_codec(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) != 2 or args[1].lower() not in CODECS:
        return await message.reply_text("Usage: <code>/codec libx264</code> or <code>/codec libx265</code>")
    await update_field(message, "codec", args[1].lower())


@app.on_message(filters.incoming & filters.command(["crf", f"crf@{BOT_USERNAME}"]))
async def change_crf(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) != 2 or not args[1].isdigit() or not 0 <= int(args[1]) <= 51:
        return await message.reply_text("Usage: <code>/crf 30</code> (allowed range: 0–51)")
    await update_field(message, "crf", str(int(args[1])))


@app.on_message(filters.incoming & filters.command(["preset", f"preset@{BOT_USERNAME}"]))
async def change_preset(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) != 2 or args[1].lower() not in PRESETS:
        return await message.reply_text("Allowed presets: <code>ultrafast, veryfast, fast, medium, slow</code>")
    await update_field(message, "preset", args[1].lower())


@app.on_message(filters.incoming & filters.command(["audio", f"audio@{BOT_USERNAME}"]))
async def change_audio_bitrate(_, message):
    args = message.text.split(maxsplit=1)
    value = args[1].lower() if len(args) == 2 else ""
    if not re.fullmatch(r"(?:3[2-9]|[4-9]\d|[12]\d\d|3[01]\d|320)k", value):
        return await message.reply_text("Usage: <code>/audio 64k</code> (allowed range: 32k–320k)")
    await update_field(message, "audio_bitrate", value)


@app.on_callback_query(filters.regex(r"^encset:"), group=-1)
async def encoding_settings_callback(_, query):
    try:
        _, owner, field, value = query.data.split(":", 3)
        owner_id = int(owner)
    except (TypeError, ValueError):
        return await query.answer("Invalid settings action.", show_alert=True)

    if query.from_user.id != owner_id or query.from_user.id not in AUTH_USERS:
        return await query.answer("This settings panel is not for you.", show_alert=True)

    allowed = {
        "codec": CODECS,
        "crf": CRF_VALUES,
        "preset": PRESETS,
        "audio_bitrate": AUDIO_BITRATES,
    }
    if field == "reset":
        apply_settings(DEFAULT_SETTINGS)
        notice = "Defaults restored"
    elif field in allowed and value in allowed[field]:
        apply_settings({field: value})
        notice = "Setting updated"
    else:
        return await query.answer("Unsupported settings value.", show_alert=True)

    await save_settings()
    await query.answer(f"✅ {notice}")
    await _safe_edit(
        query.message,
        settings_text(changed=field),
        reply_markup=settings_keyboard(owner_id),
    )


@app.on_callback_query(filters.regex(r"^userset:"), group=-2)
async def personal_settings_callback(_, query):
    try:
        _, owner, section, value = (query.data.split(":", 3) + [""])[:4]
        owner_id = int(owner)
    except (TypeError, ValueError):
        return await query.answer("Invalid settings action.", show_alert=True)

    if query.from_user.id != owner_id:
        return await query.answer("This settings panel is not for you.", show_alert=True)
    if not _personal_settings_allowed(owner_id, query.message.chat.id):
        return await query.answer("You are not authorized to use this bot.", show_alert=True)

    try:
        if section == "home":
            await query.answer()
            return await render_personal_settings(query.message, owner_id)

        if section == "encoding":
            if owner_id not in AUTH_USERS:
                return await query.answer("Encoding settings are admin-only.", show_alert=True)
            await query.answer()
            return await _safe_edit(
                query.message,
                settings_text(),
                reply_markup=settings_keyboard(owner_id),
            )

        if section == "gdrive":
            return await _gdrive_action(query, owner_id, value or "view")

        notice = None
        if section == "media" and value in {"video", "document"}:
            await db.set_media_preference(owner_id, value)
            notice = f"Send video as set to {value.title()}"
        elif section == "split" and value in {"normal", "binary"}:
            await db.set_split_mode(owner_id, value)
            label = "Binary Split" if value == "binary" else "Normal Split"
            notice = f"Split mode set to {label}"
        elif section == "spoiler" and value in {"on", "off"}:
            await db.set_user_spoiler(owner_id, value == "on")
            notice = f"Spoiler mode set to {value.upper()}"
        elif section == "upload" and value in {"group", "dm", "channel"}:
            if value == "channel" and not await db.get_user_channel(owner_id):
                return await query.answer(
                    "Set a channel first with /setchannel @username or channel_id.",
                    show_alert=True,
                )
            await db.set_upload_preference(owner_id, value)
            notice = f"Upload destination set to {value.title()}"
        elif section == "location" and value in {"telegram", "gdrive"}:
            if value == "gdrive":
                from bot.helper_funcs import gdrive as gdrive_mod
                if not await gdrive_mod.leech_drive_uid(owner_id):
                    return await query.answer(
                        "Google Drive is not connected - open ☁️ Google Drive panel and connect first.",
                        show_alert=True,
                    )
            await db.set_upload_location(owner_id, value)
            notice = (
                "Upload location set to Google Drive"
                if value == "gdrive"
                else "Upload location set to Telegram"
            )
        elif section == "metadata" and value in {"on", "off"}:
            await db.set_metadata(owner_id, value.title())
            notice = f"Metadata set to {value.upper()}"
        elif section == "thumbnail" and value == "view":
            thumbnail = await db.get_thumbnail(owner_id)
            if not thumbnail:
                return await query.answer(
                    "No thumbnail saved. Reply to an image with /setthumb.",
                    show_alert=True,
                )
            await query.answer("Opening saved thumbnail")
            return await query.message.reply_photo(
                photo=thumbnail,
                caption="🖼️ <b>Your saved thumbnail</b>\n\nUse /delthumb to remove it.",
            )
        elif section == "thumbnail" and value == "delete":
            await db.del_thumbnail(owner_id)
            notice = "Saved thumbnail deleted"
        elif section == "watermark" and value == "help":
            watermark = await db.get_watermark(owner_id)
            await query.answer()
            return await query.message.reply_text(
                "💧 <b>Watermark</b>\n\n"
                f"Current: <code>{'Saved' if watermark else 'Not set'}</code>\n\n"
                "Set: reply to an image with <code>/setwatermark</code>\n"
                "View: <code>/getwatermark</code>\n"
                "Remove: <code>/delwatermark</code>"
            )
        elif section == "watermark" and value == "delete":
            await db.del_watermark(owner_id)
            notice = "Saved watermark deleted"
        elif section == "channel" and value == "help":
            channel_id = await db.get_user_channel(owner_id)
            await query.answer()
            return await query.message.reply_text(
                "📢 <b>Upload Channel</b>\n\n"
                f"Current: <code>{channel_id or 'Not set'}</code>\n\n"
                "Set: <code>/setchannel @username</code>\n"
                "View: <code>/getchannel</code>\n"
                "Remove: <code>/delchannel</code>\n\n"
                "The bot must be an admin with permission to post messages.",
            )
        else:
            return await query.answer("Unsupported settings action.", show_alert=True)

        await query.answer(f"✅ {notice}")
        await render_personal_settings(query.message, owner_id, changed=notice)
    except Exception as error:
        LOGGER.exception("Unable to update personal settings: %s", error)
        await query.answer("Failed to update settings. Please try again.", show_alert=True)


# Manual paste fallback: the redirect URL arrives here when the browser could
# not reach the bot's local callback (remote users), or the link was pasted.
@app.on_message(
    filters.incoming & filters.text & filters.regex(r"(?i)[?&]code="),
    group=-5,
)
async def gdrive_paste_redirect(_, message):
    user = message.from_user
    text = message.text or ""
    if not user or "code=" not in text:
        return
    if not gdrive_api.has_pending(user.id):
        return
    try:
        await gdrive_api.complete_paste(user.id, text)
    except ValueError as err:
        return await message.reply_text(f"⚠️ {html.escape(str(err))}")
    except Exception as err:
        LOGGER.warning("[GDrive] pasted-link exchange failed: %s", err)
        return await message.reply_text(
            "❌ Google rejected that link. Open Settings > Google Drive and click Authorize again."
        )
    try:
        await message.delete()
    except Exception:
        pass


gdrive_api.set_result_callback(_gdrive_result)
