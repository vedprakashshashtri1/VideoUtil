# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""NexonBots style flag parsing shared by /leech and the util commands.

Mirrors NexonBots `arg_parser` (bot/helper/ext_utils/bot_utils.py:225):
- link = tokens BEFORE the first recognized/unknown flag token
- always-bool flags never consume a value
- bool-capable flags (-e -z -b -d -sv -ss -seedr) take a value only when a
  value follows; otherwise True
- value flags consume tokens until the next recognized flag
- a value wrapped in [...] may itself contain flag tokens
- unknown flag-looking tokens are reported instead of silently corrupting
  the link (slightly safer than NexonBots, same otherwise)
"""
import os
import re

FLAG_RE = re.compile(r"^-[A-Za-z]{1,6}$")

# kind: "bool"    -> always True, never consumes a value
#       "boolval" -> True alone; consumes a value when one follows
#       "value"   -> always consumes a value
LEECH_FLAG_KINDS = {
    "-s": "bool", "-j": "bool", "-f": "bool", "-fd": "bool", "-fu": "bool",
    "-sync": "bool", "-hl": "bool", "-doc": "bool", "-med": "bool",
    "-ut": "bool", "-bt": "bool", "-yt": "bool", "-ad": "bool",
    "-seedr": "bool",
    "-b": "boolval", "-e": "boolval", "-z": "boolval", "-d": "boolval",
    "-sv": "boolval", "-ss": "boolval",
    "-n": "value", "-m": "value", "-meta": "value", "-up": "value",
    "-ud": "value", "-gc": "value", "-rcf": "value", "-au": "value",
    "-ap": "value", "-h": "value", "-t": "value", "-ca": "value",
    "-cv": "value", "-ns": "value", "-tl": "value", "-sp": "value",
    "-i": "value", "-ff": "value",
}

# NexonBots mirror_leech.py:138-177 defaults (fresh containers per call)
def _leech_defaults():
    return {
        "-doc": False, "-med": False, "-d": False, "-j": False, "-s": False,
        "-b": False, "-e": False, "-z": False, "-sv": False, "-ss": False,
        "-f": False, "-fd": False, "-fu": False, "-sync": False,
        "-hl": False, "-ut": False, "-bt": False, "-yt": False,
        "-ad": False, "-seedr": False,
        "-i": 0, "-sp": 0,
        "link": "",
        "-n": "", "-m": "", "-meta": "", "-up": "", "-ud": "", "-gc": "",
        "-rcf": "", "-au": "", "-ap": "", "-h": "", "-t": "", "-ca": "",
        "-cv": "", "-ns": "", "-tl": "", "-ff": set(),
    }


# Flags recognised by the util commands (encode/audio/tools upload pipeline)
UTIL_FLAG_KINDS = {
    "-n": "value", "-doc": "bool", "-med": "bool",
    "-t": "value", "-sp": "value",
}

# flag -> why it is not usable yet ("Phase B" = rclone work, gated by user)
FLAG_STATUS = {
    "-up": "upload destination - part of Phase B (Drive), "
           "will be enabled when you ask for it",
    "-ud": "rclone/Drive dump destination - Phase B (rclone)",
    "-gc": "Google Drive category - Phase B (rclone)",
    "-rcf": "rclone flags - Phase B (rclone)",
    "-sync": "rclone sync - Phase B (rclone), only for /clone",
    "-s": "torrent file selection - torrentp engine has no selective "
          "download support",
    "-d": "seeding - the torrentp engine does not seed",
    "-ad": "AllDebrid API integration is not available yet",
    "-seedr": "Seedr.cc integration is not available yet",
    "-yt": "YouTube upload integration is not available yet",
}

PHASE_B_FLAGS = ("-up", "-ud", "-gc", "-rcf", "-sync")
OWNER_ONLY_FLAGS = ("-ff",)


def parse_size(value):
    """NexonBots get_size_bytes(): '500mb'/'2g'/'4000000000' -> bytes (0 if bad)."""
    if value in (None, False, True, ""):
        return 0
    s = str(value).strip().lower()
    if not s:
        return 0
    try:
        # substring checks mirror NexonBots get_size_bytes()
        if "k" in s:
            return int(float(s.split("k")[0]) * 1024)
        if "m" in s:
            return int(float(s.split("m")[0]) * 1048576)
        if "g" in s:
            return int(float(s.split("g")[0]) * 1073741824)
        if "t" in s:
            return int(float(s.split("t")[0]) * 1099511627776)
        return int(float(s))  # bare digits = bytes (NexonBots -sp rule)
    except (ValueError, IndexError, TypeError):
        return 0


def parse_split_size(value):
    """-sp: bare digits are bytes, otherwise size suffixes (NexonBots common.py:666)."""
    if value in (None, False, True, ""):
        return 0
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    return parse_size(s)


def parse_leech_flags(items):
    """
    NexonBots arg_parser port.
    Returns (args, link, unknown_flags, set_keys).
    """
    args = _leech_defaults()
    unknown = []
    set_keys = []
    consumed = set()
    arg_start = -1
    i = 0
    total = len(items or [])

    while i < total:
        part = items[i]

        if part in args:
            if arg_start == -1:
                arg_start = i
            set_keys.append(part)
            kind = LEECH_FLAG_KINDS.get(part, "value")

            if kind == "bool" or (kind == "boolval" and i + 1 == total):
                args[part] = True
                consumed.add(i)
                i += 1
                continue

            # boolval followed only by another always-bool flag -> True
            if kind == "boolval" and i + 1 < total:
                nxt = items[i + 1]
                if nxt in args and LEECH_FLAG_KINDS.get(nxt) == "bool":
                    args[part] = True
                    consumed.add(i)
                    i += 1
                    continue

            sub_list = []
            j = i + 1
            while j < total:
                nxt = items[j]
                nxt_recognized = nxt in args
                if nxt_recognized:
                    if part == "-gc" and nxt == "-gc":
                        sub_list.append(nxt)
                        j += 1
                        continue
                    if not sub_list:
                        if kind == "boolval":
                            args[part] = True
                        break
                    check = " ".join(sub_list).strip()
                    if check.startswith("[") and check.endswith("]"):
                        break
                    if not check.startswith("["):
                        break
                    # value opens with [ but is not closed yet -> keep flags
                    sub_list.append(nxt)
                    consumed.add(j)
                    j += 1
                    continue
                sub_list.append(nxt)
                consumed.add(j)
                j += 1

            if sub_list:
                value = " ".join(sub_list)
                if part == "-ff":
                    # NexonBots literal_eval: ["cmd1", "cmd2"] -> individual cmds
                    if value.startswith("[") and value.endswith("]"):
                        try:
                            import ast
                            ev = ast.literal_eval(value)
                            if isinstance(ev, (list, tuple, set)):
                                args["-ff"].update(str(x) for x in ev)
                            else:
                                args["-ff"].add(str(ev))
                        except Exception:
                            args["-ff"].add(value[1:-1].strip())
                    else:
                        args["-ff"].add(value)
                else:
                    if value.startswith("[") and value.endswith("]"):
                        value = value[1:-1].strip()
                    args[part] = value
                i = j
            else:
                i += 1
            continue

        # unknown flag-looking token at top level (not consumed as a value)
        if i not in consumed and FLAG_RE.match(part):
            unknown.append(part)
            if arg_start == -1:
                arg_start = i
            consumed.add(i)
            i += 1
            continue

        i += 1

    # tokens after flags that were never consumed (e.g. typo tail or a value
    # flag left dangling). arg_start == -1 means NO flag-like token exists at
    # all - then every token is link material (plain `/leech <link>`), never
    # report it as an unknown flag.
    orphans = [
        items[k] for k in range(total)
        if arg_start != -1 and k not in consumed and k >= arg_start
        and not FLAG_RE.match(items[k] or "")
    ]
    if orphans:
        unknown.extend(orphans)

    link = ""
    link_items = items[:arg_start] if arg_start != -1 else [
        items[k] for k in range(total) if k not in consumed
    ]
    if link_items:
        link = " ".join(link_items).strip()

    # keep flag output types consistent with NexonBots defaults
    try:
        args["-i"] = int(args["-i"]) if not isinstance(args["-i"], bool) else 0
    except (TypeError, ValueError):
        args["-i"] = 0

    return args, link, unknown, set_keys


def parse_util_flags(tokens):
    """Strip util-command flags. Returns (rest_tokens, flags_dict)."""
    rest = []
    flags = {}
    i = 0
    total = len(tokens or [])
    while i < total:
        t = tokens[i]
        if t in UTIL_FLAG_KINDS:
            if UTIL_FLAG_KINDS[t] == "bool":
                flags[t] = True
                i += 1
            else:
                if i + 1 < total and not FLAG_RE.match(tokens[i + 1]):
                    flags[t] = tokens[i + 1]
                    i += 2
                else:
                    flags[t] = True
                    i += 1
            continue
        rest.append(t)
        i += 1
    return rest, flags


def flags_from_message(message):
    """(rest, flags) parsed from a message's text OR caption (util commands)."""
    raw = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    parts = raw.strip().split()
    return parse_util_flags(parts[1:] if parts else [])


_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name, fallback="download"):
    """Safe single path component for -n / -m (mirrors utils.safe_media_name)."""
    base = os.path.basename(str(name or "").replace("\\", "/").strip())
    base = _INVALID_NAME_CHARS.sub("", base).strip(" .")
    return base or fallback


def blocked_flags(set_keys):
    """[(flag, reason)] for flags that cannot run yet (Phase B / unsupported)."""
    out = []
    for key in LEECH_FLAG_KINDS:
        if key in set_keys and key in FLAG_STATUS:
            out.append((key, FLAG_STATUS[key]))
    return out


def flags_fingerprint(args, set_keys):
    """Canonical string of the flags a user set - used in the dedupe key."""
    parts = []
    for key in LEECH_FLAG_KINDS:
        if key not in set_keys:
            continue
        val = args.get(key)
        if val is True:
            parts.append(key)
        elif isinstance(val, set):
            parts.append(f"{key}={'~'.join(sorted(val))}")
        elif val not in (None, False, "", 0):
            parts.append(f"{key}={val}")
    return "|".join(parts)


# --- usage text ---

_LEECH_HELP_SECTIONS = [
    (
        "Basics",
        "Reply to a link/file with the command, or:\n"
        "<code>/leech link -flags</code>\n"
        "Always write the link BEFORE the flags.\n"
        "If a flag needs a value, write it like: <code>-n new name</code>",
    ),
    (
        "Extract / Zip / Join  (-e -z -j)",
        "<code>/leech link -e</code> - extract archive\n"
        "<code>/leech link -e pass</code> - password protected archive\n"
        "<code>/leech link -z</code> - zip the upload\n"
        "<code>/leech link -z pass -e</code> - extract first, then zip\n"
        "<code>/leech link -j</code> - join split .001/.002 parts\n"
        "Note: with both -e and -z, extract runs first.",
    ),
    (
        "Rename / Folder / Name swap  (-n -m -ns)",
        "<code>/leech link -n new name</code> - rename the download\n"
        "<code>/leech link -m folder name</code> - put the content in a folder\n"
        "<code>/leech link -ns pattern:replace:count:FLAG</code>\n"
        "  FLAG: s=case sensitive, i=ignore case (default applies to all)\n"
        "  group rules with '|': <code>-ns [0-9]::|\\[mltb\\]:mltb</code>\n"
        "  Renames files/folders with regex.",
    ),
    (
        "Screenshots / Sample / Convert  (-ss -sv -ca -cv)",
        "<code>/leech link -ss</code> - 10 screenshots (or <code>-ss 6</code>)\n"
        "<code>/leech link -sv</code> - 60s sample (or <code>-sv 70:5</code> = "
        "sample:part seconds)\n"
        "<code>/leech link -ca mp3</code> - convert audio "
        "(<code>-ca mp3 + flac ogg</code> = only listed outputs, "
        "<code>-ca mp3 - flac ogg</code> = all except listed)\n"
        "<code>/leech link -cv mp4</code> - convert video "
        "(<code>-cv mkv - webm flv</code> also works)",
    ),
    (
        "Thumb / Layout / Split / Type  (-t -tl -sp -doc -med)",
        "<code>/leech link -t image-url</code> - set thumbnail\n"
        "<code>/leech link -t none</code> - no thumbnail\n"
        "<code>/leech link -t https://t.me/chan/12</code> - Telegram photo link\n"
        "<code>/leech link -tl 3x3</code> - grid thumbnail (frames from video)\n"
        "<code>/leech link -sp 500mb</code> - split size (mb/gb/bytes)\n"
        "<code>/leech link -doc</code> - send as document\n"
        "<code>/leech link -med</code> - send as media (streamable)",
    ),
    (
        "Transmission / Force  (-hl -bt -ut -f -fd -fu)",
        "<code>-hl</code> - hybrid: up to 2GB by bot, larger by bot/user "
        "(needs a premium session)\n<code>-bt</code> - bot client only\n"
        "<code>-ut</code> - user session only (USER_SESSION_STRING required)\n"
        "<code>-f</code> - skip download+upload+processing queues\n"
        "<code>-fd</code> - skip download queue only\n"
        "<code>-fu</code> - skip upload queue only",
    ),
    (
        "Headers / Auth / Metadata  (-h -au -ap -meta)",
        "<code>/leech link -h key: value key1: value1</code> - custom headers\n"
        "<code>/leech link -au user -ap pass</code> - HTTP basic auth\n"
        "<code>/leech link -meta title=Name|artist=Someone</code> - "
        "container metadata (dynamic: {filename} {basename} {extension} "
        "{year})",
    ),
    (
        "FFmpeg cmds  (-ff)  [owner only]",
        "<code>/leech link -ff [\"-i mltb.mkv -c copy mltb.mkv\"]</code>\n"
        "The bracket form is required (for args with spaces). mltb = input, "
        "the second mltb token = output. Use mltb.video / mltb.audio / mltb.ext "
        "to filter files. <code>-del</code> deletes the original.",
    ),
    (
        "Bulk / Multi  (-b -i)",
        "Reply to a text message / .txt file (one link per line):\n"
        "<code>/leech -b</code> - all links (use -b 2:5 for a range)\n"
        "<code>/leech -i 3</code> - only the first 3 links\n"
        "Command flags apply to every link; each line's own flags override them.",
    ),
    (
        "Flags that do not work yet",
        "Phase B (rclone): -up -ud -gc -rcf -sync\n"
        "Unsupported: -s (file select), -d (seed), -ad (AllDebrid), "
        "-seedr, -yt (YouTube upload)\n"
        "Using them stops the task with that message.",
    ),
]


def leech_flag_help_messages():
    """Chunked /leechhelp replies (Telegram 4096 char limit)."""
    msgs = ["🚩 <b>All /leech flags</b>\n"]
    for title, body in _LEECH_HELP_SECTIONS:
        block = f"\n<b>▸ {title}</b>\n{body}"
        if len(msgs[-1]) + len(block) > 3600:
            msgs.append(block)
        else:
            msgs[-1] += block
    msgs.append(
        "\n💡 Util commands (/720p, /extract_audio, /cut, /merge...) also "
        "accept these flags: <code>-n -doc -med -t -sp</code>"
    )
    return msgs
