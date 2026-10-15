# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Centralized Telegram transport and WZGram management layer."""

import asyncio
import importlib.metadata
import logging
from typing import Optional
from packaging import version as pkg_version
import httpx

from bot.config import Config
from database import db

LOGGER = logging.getLogger(__name__)

PYPI_URL = "https://pypi.org/pypi/wzgram/json"
CHECK_INTERVAL_SECONDS = 86400  # 24 hours


def get_installed_wzgram_version() -> str:
    """Dynamically get the currently installed WZGram version."""
    try:
        return importlib.metadata.version("wzgram")
    except Exception:
        return "Unknown"


def get_flood_wait_seconds(error: Exception, default: int = 1) -> int:
    """Extract wait duration from a FloodWait error safely across versions."""
    return getattr(error, "value", None) or getattr(error, "x", None) or default


async def check_wzgram_updates(client=None) -> Optional[dict]:
    """Check PyPI for new WZGram versions and notify owner/admins once per new version.

    CRITICAL RULES:
    - Never automatically install, upgrade, or restart.
    - Never modify requirements or trigger Git actions.
    - Notify owner only once per new release (persisted in DB).
    - Errors must not crash or block the bot.
    """
    installed_str = get_installed_wzgram_version()
    if installed_str == "Unknown":
        LOGGER.debug("WZGram version could not be determined; skipping update check.")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(PYPI_URL)
            if response.status_code != 200:
                LOGGER.debug(f"PyPI returned status {response.status_code}")
                return None
            data = response.json()
            latest_str = data.get("info", {}).get("version")
            if not latest_str:
                return None
    except Exception as exc:
        LOGGER.debug(f"WZGram update check network error: {exc}")
        return None

    try:
        installed_v = pkg_version.parse(installed_str)
        latest_v = pkg_version.parse(latest_str)
    except Exception as exc:
        LOGGER.warning(f"Could not parse WZGram versions ('{installed_str}', '{latest_str}'): {exc}")
        return None

    if latest_v <= installed_v:
        LOGGER.info(f"WZGram is up to date (installed: {installed_str}, latest: {latest_str}).")
        return {"installed": installed_str, "latest": latest_str, "update_available": False}

    # An update is available! Check if already notified for this exact version
    last_notified = None
    try:
        last_notified = await db.get_last_notified_wzgram_version()
    except Exception as exc:
        LOGGER.debug(f"Could not read last notified version from DB: {exc}")

    if last_notified:
        try:
            if pkg_version.parse(last_notified) >= latest_v:
                LOGGER.debug(f"Admin already notified for WZGram v{latest_str}.")
                return {"installed": installed_str, "latest": latest_str, "update_available": True, "notified": False}
        except Exception as exc:
            LOGGER.debug(f"Ignoring unreadable last-notified version {last_notified!r}: {exc}")

    # Format notification message
    pypi_page = f"https://pypi.org/project/wzgram/{latest_str}/"
    notification_text = (
        f"📢 <b>WZGram Update Available</b>\n\n"
        f"• <b>Installed version:</b> <code>{installed_str}</code>\n"
        f"• <b>Latest stable version:</b> <code>{latest_str}</code>\n\n"
        f"<b>Manual update command:</b>\n"
        f"<code>pip install -U wzgram</code>\n\n"
        f"<b>Exact pin for requirements.txt:</b>\n"
        f"<code>wzgram=={latest_str}</code>\n\n"
        f"🔗 <a href='{pypi_page}'>PyPI Release Notes</a>\n\n"
        f"⚠️ <i>Please test this update in a staging environment before manual deployment and restart. "
        f"Auto-update is permanently disabled for stability.</i>"
    )

    sent = False
    targets = list(Config.AUTH_USERS)
    if client and targets:
        for admin_id in targets:
            try:
                await client.send_message(
                    chat_id=admin_id,
                    text=notification_text,
                    disable_web_page_preview=True
                )
                sent = True
            except Exception as send_err:
                LOGGER.warning(f"Failed to send update notification to admin {admin_id}: {send_err}")

    # Persist the version only once at least one admin was actually notified (or
    # there is nobody to notify), so transient send failures are retried on the
    # next cycle instead of silently losing the one-and-only notification.
    if sent or not targets:
        try:
            await db.set_last_notified_wzgram_version(latest_str)
        except Exception as db_err:
            LOGGER.debug(f"Could not persist last notified version to DB: {db_err}")

    return {
        "installed": installed_str,
        "latest": latest_str,
        "update_available": True,
        "notified": sent
    }


async def wzgram_update_checker_loop(client):
    """Background task running periodic update checks without blocking startup."""
    # Delay initial check slightly to let bot finish starting up cleanly
    await asyncio.sleep(60)
    while True:
        try:
            await check_wzgram_updates(client)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            LOGGER.debug(f"Error in WZGram update checker loop: {exc}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
