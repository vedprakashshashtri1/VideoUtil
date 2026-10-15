# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
import asyncio
import ast
import html
import io
import logging
import os
import re
import shlex
import shutil
import sys
import time
import traceback

from bot import (
    BOT_START_TIME,
    LOGGER,
    LOG_FILE_ZZGEVC,
    LOG_CHANNEL,
    TG_BOT_TOKEN,
    API_HASH,
    MAX_MESSAGE_LENGTH,
    AUTH_USERS,
    crf,
    codec,
    resolution,
    audio_b,
    preset,
    name,
    size,
    data,
    pid_list
)


from bot.commands import Command
from bot.localisation import Localisation
from bot.helper_funcs.display_progress import (
    TimeFormatter,
    humanbytes
)

# --- Admin shell hardening: allowlist + audit logging + secret masking ---
# SECURITY: /exec runs strict read-only diagnostic commands on the host.
_EXEC_ALLOWED_FIRST = frozenset({
    "ls", "dir", "pwd", "whoami", "id", "groups", "uname", "uptime",
    "df", "du", "free", "nproc", "vmstat", "iostat", "ps", "top",
    "cat", "tail", "head", "wc", "echo",
    "ffmpeg", "ffprobe", "mediainfo", "git", "neofetch",
})
_EXEC_CMD_REGEX = re.compile(r'^[A-Za-z0-9._/\-]+(\s+[A-Za-z0-9._/:=@%+-]+)*$')

_EXEC_BLOCKED_SUBSTRINGS = (
    "rm ", "rm -", "rmdir", "shutdown", "reboot", "halt", "poweroff",
    "mkfs", "dd ", "chmod", "chown", ":(){", "kill", "pkill", "killall",
    "env", "printenv", "export ", "unset ", "git push",
    "curl", "wget", "ssh", "scp", "ftp", "nc ", "netcat",
    "token", "api_hash", "db_url", "dburl", "session",
    "mv /", "mv ~", "cp /", ">", ">>", "|", ";", "&&", "`", "$(",
)

# SECURITY: /eval AST inspection to prevent escape & code injection
_EVAL_DANGEROUS_NAMES = frozenset({
    "__import__", "getattr", "globals", "locals", "vars",
    "compile", "exec", "eval", "open", "breakpoint"
})


def _mask_secrets(text: str) -> str:
    """Redact bot secrets / token-like strings before display or logging."""
    try:
        redacted = str(text or "")
        for secret in (TG_BOT_TOKEN, API_HASH):
            if secret and len(str(secret)) > 4:
                redacted = redacted.replace(str(secret), "[REDACTED]")
        # Generic BotFather-style tokens that may appear in logs/output
        redacted = re.sub(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b", "[REDACTED_TOKEN]", redacted)
        return redacted
    except Exception:
        return "[unrenderable output]"


def _is_exec_allowed(cmd: str) -> tuple:
    """Returns (allowed: bool, reason: str)."""
    stripped = (cmd or "").strip()
    if not stripped:
        return False, "empty command"
    if not _EXEC_CMD_REGEX.match(stripped):
        return False, "forbidden characters in command line (no quotes, subshells, or pipes)"
    try:
        args = shlex.split(stripped)
    except Exception as e:
        return False, f"invalid command syntax: {e}"
    if not args:
        return False, "empty command"
    first = args[0].lower().lstrip("/")
    if first not in _EXEC_ALLOWED_FIRST:
        return False, f"'{first}' is not in the read-only allowlist"
    lowered = stripped.lower()
    for bad in _EXEC_BLOCKED_SUBSTRINGS:
        if bad in lowered:
            return False, f"forbidden pattern '{bad.strip()}'"
    return True, "ok"


def _is_eval_blocked(code: str) -> str:
    """Returns the matched dangerous pattern or AST violation, or '' if clean."""
    try:
        parsed = ast.parse(code)
    except Exception as e:
        return f"syntax error: {e}"

    for node in ast.walk(parsed):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "import statements are forbidden"
        if isinstance(node, ast.Name):
            if node.id in _EVAL_DANGEROUS_NAMES or node.id.startswith("__") or node.id.endswith("__"):
                return f"forbidden name '{node.id}'"
        if isinstance(node, ast.Attribute):
            if node.attr in _EVAL_DANGEROUS_NAMES or node.attr.startswith("__") or node.attr.endswith("__"):
                return f"forbidden attribute '{node.attr}'"
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "__class__":
                return "forbidden subscript on class"
    return ""


async def _log_admin_action(client, kind: str, user_id: int, cmd: str, note: str) -> None:
    """Audit-log every /exec and /eval invocation (file log + LOG_CHANNEL)."""
    safe_cmd = _mask_secrets(cmd)
    LOGGER.warning(f"ADMIN {kind} by {user_id}: {safe_cmd} [{note}]")
    try:
        if LOG_CHANNEL:
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=(
                    f"🛡 <b>ADMIN {kind}</b>\n"
                    f"User: <code>{user_id}</code>\n"
                    f"Cmd: <code>{safe_cmd[:1500]}</code>\n"
                    f"Result: {note}"
                ),
            )
    except Exception as log_err:
        LOGGER.warning(f"Failed to forward admin audit log: {log_err}")


async def exec_message_f(client, message):
  if message.from_user.id in AUTH_USERS:
    if True:
        DELAY_BETWEEN_EDITS = 0.3
        PROCESS_RUN_TIME = 100
        cmd = message.text.split(" ", maxsplit=1)[1]

        allowed, deny_reason = _is_exec_allowed(cmd)
        await _log_admin_action(
            client, "EXEC", message.from_user.id, cmd,
            "allowed" if allowed else f"BLOCKED: {deny_reason}",
        )
        if not allowed:
            return await message.reply_text(
                f"⛔ <b>Command blocked:</b> {deny_reason}\n\n"
                f"Allowed: <code>{', '.join(sorted(_EXEC_ALLOWED_FIRST))}</code> (read-only)"
            )

        reply_to_id = message.id
        if message.reply_to_message:
            reply_to_id = message.reply_to_message.id

        # SECURITY: Use create_subprocess_exec with args to prevent shell injection
        args = shlex.split(cmd.strip())
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return await message.reply_text("⛔ Command timed out after 60s.")

        e = stderr.decode()
        if not e:
            e = "No Error"
        o = stdout.decode()
        if not o:
            o = "No Output"
        else:
            _o = o.split("\n")
            o = "`\n".join(_o)
        OUTPUT = f"**QUERY:**\n__Command:__\n`{cmd}` \n__PID:__\n`{process.pid}`\n\n**stderr:** \n`{e}`\n**Output:**\n{o}"
        OUTPUT = _mask_secrets(OUTPUT)
        safe_cmd = _mask_secrets(cmd)

        if len(OUTPUT) > MAX_MESSAGE_LENGTH:
            with open("exec.text", "w+", encoding="utf8") as out_file:
                out_file.write(str(OUTPUT))
            await client.send_document(
                chat_id=message.chat.id,
                document="exec.text",
                caption=safe_cmd[:1000],
                disable_notification=True,
                reply_to_message_id=reply_to_id
            )
            os.remove("exec.text")
            await message.delete()
        else:
            await message.reply_text(OUTPUT)
  else:
    return
async def eval_message_f(client, message):
    if message.from_user.id in AUTH_USERS:
        status_message = await message.reply_text("Processing ...")
        cmd = message.text.split(" ", maxsplit=1)[1]

        blocked = _is_eval_blocked(cmd)
        await _log_admin_action(
            client, "EVAL", message.from_user.id, cmd,
            "allowed" if not blocked else f"BLOCKED: '{blocked}'",
        )
        if blocked:
            await status_message.edit(
                f"⛔ <b>Eval blocked:</b> forbidden pattern <code>{html.escape(blocked)}</code>"
            )
            return

        reply_to_id = message.id
        if message.reply_to_message:
            reply_to_id = message.reply_to_message.id

        old_stderr = sys.stderr
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        redirected_error = sys.stderr = io.StringIO()
        stdout, stderr, exc = None, None, None

        # SECURITY: Guarantee restoration of stdout/stderr even on crash
        try:
            try:
                await aexec(cmd, client, message)
            except Exception:
                exc = traceback.format_exc()

            stdout = redirected_output.getvalue()
            stderr = redirected_error.getvalue()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        evaluation = ""
        if exc:
            evaluation = exc
        elif stderr:
            evaluation = stderr
        elif stdout:
            evaluation = stdout
        else:
            evaluation = "Success"

        safe_cmd_text = html.escape(_mask_secrets(cmd))
        safe_eval_text = html.escape(_mask_secrets(evaluation.strip()))
        final_output = f"<b>EVAL</b>: <code>{safe_cmd_text}</code>\n\n<b>OUTPUT</b>:\n<code>{safe_eval_text}</code>\n"

        if len(final_output) > MAX_MESSAGE_LENGTH:
            with open("eval.text", "w+", encoding="utf8") as out_file:
                out_file.write(str(final_output))
            await message.reply_document(
                document="eval.text",
                caption=_mask_secrets(cmd)[:1000],
                disable_notification=True,
                reply_to_message_id=reply_to_id,
            )
            os.remove("eval.text")
            await status_message.delete()
        else:
            await status_message.edit(final_output)


async def aexec(code, client, message):
    exec(
        f"async def __aexec(client, message): "
        + "".join(f"\n {l}" for l in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)


async def upload_log_file(client, message):
  if message.from_user.id in AUTH_USERS:
    await message.reply_document(
        LOG_FILE_ZZGEVC
    )
  else:
    return
