# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Admin-only server network benchmark, adapted from PrimeSujoy/VideoCover."""

import asyncio
from html import escape
from io import BytesIO
from urllib.request import Request, urlopen

from pyrogram import filters
from pyrogram.enums import ParseMode

from bot import AUTH_USERS, BOT_USERNAME, LOGGER, app
from bot.localisation import Localisation


speedtest_lock = asyncio.Lock()


def _format_speed(bits_per_second):
    size = float(bits_per_second or 0) / 8
    for unit in ("B/s", "KB/s", "MB/s", "GB/s", "TB/s"):
        if size < 1024 or unit == "TB/s":
            return f"{size:.2f} {unit}"
        size /= 1024
    return "0 B/s"


def _format_size(size_bytes):
    size = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return "0 B"


def _safe(value, fallback="Unknown"):
    return escape(str(value)) if value not in (None, "") else fallback


def _download_result_image(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 VideoUtilBot/1.0"})
    with urlopen(request, timeout=30) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if not data:
        raise ValueError("Empty speed-test image")
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("Speed-test image exceeds 10 MB")
    image = BytesIO(data)
    image.name = "speedtest.png"
    return image


def _is_authorized(message):
    user_id = message.from_user.id if message.from_user else 0
    return user_id in AUTH_USERS or message.chat.id in AUTH_USERS


@app.on_message(filters.command(["speedtest", f"speedtest@{BOT_USERNAME}"]))
async def speedtest_command(_, message):
    if not _is_authorized(message):
        return await message.reply_text(Localisation.NOT_AUTH)
    if speedtest_lock.locked():
        return await message.reply_text("⚠️ A speed test is already running. Please wait.")

    progress = await message.reply_text(
        "🚀 <b>Speed Test Started</b>\n\n🔎 Selecting the best server...",
        parse_mode=ParseMode.HTML,
    )

    async with speedtest_lock:
        try:
            from speedtest import Speedtest

            test = await asyncio.to_thread(Speedtest, secure=True)
            await asyncio.to_thread(test.get_best_server)
            await progress.edit_text(
                "🚀 <b>Speed Test Running</b>\n\n⬇️ Measuring download speed...",
                parse_mode=ParseMode.HTML,
            )
            await asyncio.to_thread(test.download)
            await progress.edit_text(
                "🚀 <b>Speed Test Running</b>\n\n⬆️ Measuring upload speed...",
                parse_mode=ParseMode.HTML,
            )
            await asyncio.to_thread(test.upload)

            share_url = None
            try:
                await progress.edit_text(
                    "🚀 <b>Speed Test Complete</b>\n\n🖼️ Generating result image...",
                    parse_mode=ParseMode.HTML,
                )
                share_url = await asyncio.to_thread(test.results.share)
            except Exception as error:
                LOGGER.warning("Speed-test result image unavailable: %s", error)

            result = test.results.dict()
            share_url = share_url or result.get("share")
            server = result.get("server") or {}
            client = result.get("client") or {}
            server_country = ", ".join(
                item
                for item in (_safe(server.get("country"), ""), _safe(server.get("cc"), ""))
                if item
            ) or "Unknown"

            text = (
                "╭─《 🚀 <b>SPEEDTEST INFO</b> 》\n"
                f"├ <b>Upload:</b> <code>{_format_speed(result.get('upload'))}</code>\n"
                f"├ <b>Download:</b> <code>{_format_speed(result.get('download'))}</code>\n"
                f"├ <b>Ping:</b> <code>{float(result.get('ping') or 0):.3f} ms</code>\n"
                f"├ <b>Time:</b> <code>{_safe(result.get('timestamp'))}</code>\n"
                f"├ <b>Data Sent:</b> <code>{_format_size(result.get('bytes_sent'))}</code>\n"
                f"╰ <b>Data Received:</b> <code>{_format_size(result.get('bytes_received'))}</code>\n\n"
                "╭─《 🌐 <b>SPEEDTEST SERVER</b> 》\n"
                f"├ <b>Name:</b> <code>{_safe(server.get('name'))}</code>\n"
                f"├ <b>Country:</b> <code>{server_country}</code>\n"
                f"├ <b>Sponsor:</b> <code>{_safe(server.get('sponsor'))}</code>\n"
                f"├ <b>Latency:</b> <code>{_safe(server.get('latency'))} ms</code>\n"
                f"├ <b>Latitude:</b> <code>{_safe(server.get('lat'))}</code>\n"
                f"╰ <b>Longitude:</b> <code>{_safe(server.get('lon'))}</code>\n\n"
                "╭─《 👤 <b>CLIENT DETAILS</b> 》\n"
                f"├ <b>IP Address:</b> <code>{_safe(client.get('ip'))}</code>\n"
                f"├ <b>Country:</b> <code>{_safe(client.get('country'))}</code>\n"
                f"├ <b>ISP:</b> <code>{_safe(client.get('isp'))}</code>\n"
                "╰ <b>Powered by Nexon Bots</b>"
            )

            if share_url:
                try:
                    image = await asyncio.to_thread(_download_result_image, share_url)
                    await message.reply_photo(
                        photo=image,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                    )
                    return await progress.delete()
                except Exception as error:
                    LOGGER.warning("Unable to send speed-test image: %s", error)
            await progress.edit_text(text, parse_mode=ParseMode.HTML)
        except ImportError:
            await progress.edit_text(
                "❌ <b>Speed-test dependency is missing.</b>\n\n"
                "Install <code>speedtest-cli</code> and restart the bot.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as error:
            LOGGER.exception("Speed test failed: %s", error)
            await progress.edit_text(
                "❌ <b>Speed test failed.</b>\n\n"
                "The test server may be unavailable. Please try again later.",
                parse_mode=ParseMode.HTML,
            )
