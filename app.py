# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Streamlit entrypoint that keeps the Telegram bot in a child process."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time

import streamlit as st


REQUIRED_SECRETS = (
    "APP_ID",
    "API_HASH",
    "TG_BOT_TOKEN",
    "BOT_USERNAME",
    "AUTH_USERS",
    "LOG_CHANNEL",
    "DB_URL",
    "DB_NAME",
)
OPTIONAL_SECRETS = (
    "SESSION_NAME",
    "UPDATES_CHANNEL",
    "PICS",
    "DUMP_CHANNEL",
    "USER_SESSION_STRING",
    "STRING_API_ID",
    "STRING_API_HASH",
    "SESSION_USER_ID",
    "UPSTREAM_REPO",
    "GIT_TOKEN",
    "OWNER_ID",
    "GDRIVE_CLIENT_ID",
    "GDRIVE_CLIENT_SECRET",
    "GDRIVE_PROJECT_ID",
    "GDRIVE_REDIRECT_URI",
    "INDEX_URL",
)
def load_secrets() -> dict[str, str]:
    try:
        available = dict(st.secrets)
    except FileNotFoundError:
        available = {}

    values: dict[str, str] = {}
    for key in REQUIRED_SECRETS + OPTIONAL_SECRETS:
        value = available.get(key)
        if value is not None:
            values[key] = str(value)
    return values


def get_code_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        pass
    try:
        latest = 0.0
        for root, _, files in os.walk("bot"):
            for f in files:
                if f.endswith(".py"):
                    latest = max(latest, os.path.getmtime(os.path.join(root, f)))
        return str(latest)
    except Exception:
        return ""


def get_release_version() -> str:
    try:
        with open("VERSION", "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def kill_existing_bot_processes() -> None:
    """Kill any orphaned background bot processes holding the session lock."""
    current_pid = os.getpid()
    try:
        subprocess.run(["pkill", "-9", "-f", "python.*-m bot"], stderr=subprocess.DEVNULL)
    except Exception:
        pass
    if sys.platform == "win32":
        # pkill and /proc do not exist on Windows - stop bots via PowerShell.
        try:
            script = (
                "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                "Where-Object { $_.CommandLine -match '-m bot' -and "
                f"$_.ProcessId -ne {current_pid} }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                timeout=25,
            )
        except Exception:
            pass
    if os.path.exists("/proc"):
        try:
            for pid_entry in os.listdir("/proc"):
                if not pid_entry.isdigit():
                    continue
                pid = int(pid_entry)
                if pid == current_pid:
                    continue
                try:
                    cmdline_path = f"/proc/{pid}/cmdline"
                    if os.path.exists(cmdline_path):
                        with open(cmdline_path, "rb") as f:
                            cmd = f.read().decode("utf-8", errors="ignore").replace("\0", " ")
                        if "-m bot" in cmd or "bot/__main__.py" in cmd:
                            os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
        except Exception:
            pass
    time.sleep(0.5)
    try:
        for fname in os.listdir("."):
            if fname.endswith(".session.lock") or fname.endswith(".session-journal"):
                try:
                    os.remove(fname)
                except Exception:
                    pass
    except Exception:
        pass


def export_environment(values: dict[str, str]) -> None:
    for key, value in values.items():
        os.environ[key] = value
    os.environ["STREAMLIT_DEPLOYMENT"] = "1"


BOT_LOG_FILE = "bot_output.log"


@st.cache_resource(show_spinner="Starting Telegram bot…")
def start_bot(config_fingerprint: str) -> subprocess.Popen[bytes]:
    kill_existing_bot_processes()
    # Capture the bot's own stdout/stderr so the panel can show detailed logs.
    # Popen dups the fd, so our copy can be closed immediately afterwards.
    try:
        log_handle = open(BOT_LOG_FILE, "ab", buffering=0)
    except OSError:
        log_handle = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "bot"],
            env=os.environ.copy(),
            start_new_session=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT if log_handle is not None else None,
        )
    finally:
        if log_handle is not None:
            log_handle.close()
    return proc


def tail_log(path: str, max_bytes: int = 65536, max_lines: int = 200) -> str:
    """Return the last chunk of a possibly-large log file."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes), os.SEEK_SET)
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = data.splitlines()
    if size > max_bytes:
        lines = lines[1:]
    return "\n".join(lines[-max_lines:])


def stop_bot(process: subprocess.Popen[bytes] | None = None) -> None:
    if process and process.poll() is None:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=2)
            except Exception:
                pass
    kill_existing_bot_processes()


st.set_page_config(page_title="VideoUtil Bot", page_icon="🎬", layout="centered")
st.title("🎬 VideoUtil Telegram Bot")
st.caption("Streamlit process manager for the VideoUtil bot")

secrets = load_secrets()
missing = [key for key in REQUIRED_SECRETS if not secrets.get(key)]

if missing:
    st.error("Missing Streamlit secrets: " + ", ".join(missing))
    st.code("Copy .streamlit/secrets.toml.example into Streamlit Advanced settings → Secrets.")
    st.stop()

export_environment(secrets)
code_rev = get_code_revision()
release = get_release_version()
fingerprint = hashlib.sha256(
    ("\0".join(f"{key}={secrets[key]}" for key in sorted(secrets)) + f"\0rev={code_rev}").encode()
).hexdigest()


@st.fragment(run_every=2)
def live_panel():
    bot_process = start_bot(fingerprint)
    exit_code = bot_process.poll()
    if exit_code is None:
        st.success(f"Bot is running — PID {bot_process.pid}")
    else:
        st.error(f"Bot stopped with exit code {exit_code}. Check the logs below.")
    if code_rev:
        st.caption(f"Code version: {release} `{code_rev[:7]}`" if release else f"Code version: `{code_rev[:7]}`")

    if st.button("⚡ Restart Bot", type="secondary", use_container_width=True):
        stop_bot(bot_process)
        start_bot.clear()
        st.rerun()

    st.subheader("📋 Bot logs — auto-refresh every 2s")
    log_text = tail_log(BOT_LOG_FILE)
    if log_text.strip():
        st.code(log_text, language="log", line_numbers=False)
    else:
        st.caption("No bot output yet — logs appear here as soon as the bot starts.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Refresh Logs", use_container_width=True):
            st.rerun()
    with col_b:
        if st.button("📋 Copy Logs", use_container_width=True):
            if log_text.strip():
                try:
                    st.clipboard.write_text(log_text)
                    st.toast("Logs copied to clipboard!")
                except Exception:
                    st.warning("Clipboard blocked by the browser — select the log box and press Ctrl+C.")
            else:
                st.toast("No logs to copy yet")


live_panel()

st.info(
    "Streamlit Community Cloud sleeps inactive apps after 12 hours. "
    "Open this page to wake the bot again."
)
