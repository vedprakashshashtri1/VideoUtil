# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Optional HTTP health-check server for container hosting platforms.

Cloud Run, Hugging Face Spaces, Koyeb, Northflank, Railway and Heroku expect
the process to listen on ``$PORT`` (the container image defaults to 7860).
Plain VPS/Streamlit runs without a ``PORT`` environment variable skip the
server entirely.
"""

from __future__ import annotations

import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *args):
        pass


def start_health_server(logger) -> int | None:
    raw = os.environ.get("PORT") or os.environ.get("HEALTH_PORT") or ""
    if not raw.strip():
        return None
    try:
        port = int(raw.strip())
    except ValueError:
        logger.warning("Invalid PORT value %r — health server not started", raw)
        return None
    if port <= 0 or port > 65535:
        logger.warning("PORT %s out of range — health server not started", port)
        return None

    def _serve():
        try:
            server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
            server.daemon_threads = True
            logger.info("Health server listening on :%s (/ and /health)", port)
            server.serve_forever()
        except OSError as exc:
            logger.warning("Health server could not bind :%s — %s", port, exc)

    threading.Thread(target=_serve, name="health-server", daemon=True).start()
    return port
