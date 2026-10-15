# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""Post-download pipeline for /leech flags.

NexonBots order (task_listener.py): join -> extract -> -ff -> -meta -> -ns ->
-ss -> -ca/-cv -> -sv -> zip. Split (-sp) happens inside the uploader.
    Every helper is cancel-aware via should_stop() and returns (result, errors)
    instead of raising, so one failed step never kills the whole leech.
    Returns (path, errors, upload_files | None).
    """
import os
import re
import shlex
import asyncio
import logging
import subprocess
from shutil import which

from bot.helper_funcs.archive_helper import extract_downloaded
from bot.screenshot import grab_frames, equal_timestamps
from bot.helper_funcs.split_uploader import (
    binary_split_file,
    is_video_file,
    get_video_duration,
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS,
)
from bot import LOGGER, preset, crf, codec, audio_b

AUDIO_EXTENSIONS = {
    ".m4a", ".mp3", ".aac", ".flac", ".ogg", ".opus", ".wav", ".wma",
    ".ac3", ".eac3", ".mka", ".amr", ".aiff", ".ape", ".mka", ".oga",
}

# encoding settings lists are filled at startup (load_encoding_settings)
DEFAULT_CODEC = "libx264"
DEFAULT_PRESET = "veryfast"
DEFAULT_CRF = "30"
DEFAULT_AUDIO_B = "64k"


def _setting(values, default):
    try:
        if values and values[0] not in (None, ""):
            return str(values[0])
    except (IndexError, TypeError):
        pass
    return default

AUDIO_CODECS = {
    "mp3": "libmp3lame", "m4a": "aac", "aac": "aac", "ogg": "libvorbis",
    "opus": "opus", "flac": "flac", "wav": "pcm_s16le", "wma": "wmav2",
    "ac3": "ac3", "eac3": "eac3",
}

SUB_CODEC_BY_EXT = {"mp4": "mov_text", "m4v": "mov_text", "mkv": "ass"}

JOIN_PART_RE = re.compile(r"^(?P<base>.+)\.(?P<num>\d{3})$")
META_PAIR_RE = re.compile(r"^([^=]+)=(.*)$")

VIDEO_EXTS = set(VIDEO_EXTENSIONS)


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(root)]
        ) == os.path.abspath(root)
    except ValueError:
        return False


def gather_files(path: str):
    if os.path.isfile(path):
        return [path]
    out = []
    if os.path.isdir(path):
        for root, _, names in os.walk(path):
            for n in names:
                out.append(os.path.join(root, n))
    return out


def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _probe_stream(path: str, selector: str) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", selector,
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        return bool((out.stdout or "").strip())
    except Exception:
        return False


def _is_video(path: str) -> bool:
    if _is_image(path):
        return False
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS or is_video_file(path)


def _is_audio(path: str) -> bool:
    if _is_image(path):
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return False
    if ext in AUDIO_EXTENSIONS:
        return True
    return _probe_stream(path, "a:0")


async def _run_cmd(cmd, task_id=None, should_stop=None, tag="cmd"):
    """Run a subprocess with cancel-kill support. Returns (rc, stderr_tail)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    if task_id:
        try:
            from bot.task_manager import task_manager
            task_manager.register_process(task_id, proc)
        except Exception:
            pass
    _, stderr = await proc.communicate()
    if should_stop and should_stop():
        return -1, "cancelled"
    err = (stderr or b"").decode("utf-8", errors="ignore")[-400:]
    if proc.returncode != 0:
        LOGGER.warning(f"[LeechPost] {tag} failed rc={proc.returncode}: {err}")
    return proc.returncode or 0, err


# ---------------------------------------------------------------- join (-j)

async def join_split_parts(path, should_stop=None):
    """Join .001/.002... byte-split groups into their base file (NexonBots -j)."""
    joined, errors = 0, []
    dirs = [os.path.dirname(path) or "."] if os.path.isfile(path) else []
    if not dirs:
        for root, _, _ in os.walk(path, topdown=False):
            dirs.append(root)
    for dirpath in dirs:
        if should_stop and should_stop():
            return joined, errors
        try:
            names = os.listdir(dirpath)
        except OSError:
            continue
        groups = {}
        for n in names:
            m = JOIN_PART_RE.match(n)
            if not m:
                continue
            num = int(m.group("num"))
            if num == 0:
                continue
            groups.setdefault(m.group("base"), []).append((num, n))
        for base, parts in groups.items():
            parts.sort()
            nums = [p[0] for p in parts]
            if len(parts) < 2 or nums != list(range(1, len(parts) + 1)):
                continue
            target = os.path.join(dirpath, base)
            if os.path.exists(target):
                errors.append(f"{base}: target already exists, parts kept")
                continue
            try:
                tmp = target + ".joining"
                with open(tmp, "wb") as out:
                    for _, n in parts:
                        if should_stop and should_stop():
                            out.close()
                            os.remove(tmp)
                            return joined, errors
                        with open(os.path.join(dirpath, n), "rb") as src:
                            while True:
                                chunk = src.read(1 << 22)
                                if not chunk:
                                    break
                                out.write(chunk)
                os.replace(tmp, target)
                for _, n in parts:
                    try:
                        os.remove(os.path.join(dirpath, n))
                    except OSError:
                        pass
                joined += 1
                LOGGER.info(f"[LeechPost] Joined {len(parts)} parts -> {base}")
            except Exception as e:
                errors.append(f"{base}: join failed: {e}")
    return joined, errors


# ------------------------------------------------- custom ffmpeg cmds (-ff)

def _ff_matches(token: str, file_path: str) -> bool:
    """NexonBots mltb.* input matching."""
    name = os.path.basename(file_path)
    if token == "mltb":
        return True
    if token == "mltb.video":
        return _is_video(file_path)
    if token == "mltb.audio":
        return _is_audio(file_path)
    if token.startswith("mltb."):
        return name.lower().endswith(token[4:].lower())
    return False


def _ff_output_path(token: str, file_path: str) -> str:
    directory, name = os.path.split(file_path)
    stem, ext = os.path.splitext(name)
    if token == "mltb":
        return file_path
    if token == "mltb.video" or token == "mltb.audio":
        return file_path
    if token.startswith("mltb."):
        new_ext = token[4:]
        if not new_ext.startswith("."):
            new_ext = "." + new_ext
        return os.path.join(directory, stem + new_ext)
    return file_path


async def run_ffmpeg_cmds(path, cmds, task_id=None, should_stop=None):
    """NexonBots -ff: literal ffmpeg arg lists with mltb placeholders (owner only)."""
    produced, errors = [], []
    if isinstance(cmds, str):
        cmds = {cmds}
    files = gather_files(path)
    for raw in sorted(cmds or []):
        if should_stop and should_stop():
            break
        try:
            tokens = shlex.split(raw)
        except ValueError as e:
            errors.append(f"-ff parse: {e}")
            continue
        if not tokens:
            continue
        delete_input = "-del" in tokens
        tokens = [t for t in tokens if t != "-del"]
        if tokens and tokens[0].lower() in ("ffmpeg", "ffmpeg.exe"):
            tokens = tokens[1:]
        placeholders = [i for i, t in enumerate(tokens) if t.startswith("mltb")]
        if not placeholders:
            errors.append("-ff: 'mltb' placeholder missing")
            continue
        for f in files:
            if should_stop and should_stop():
                break
            if not _ff_matches(tokens[placeholders[0]], f):
                continue
            argv = list(tokens)
            argv[placeholders[0]] = f
            if len(placeholders) == 1:
                # input only - append an output next to it
                out_path = f + ".ffout"
                argv.append(out_path)
            else:
                out_idx = placeholders[-1]
                cand = _ff_output_path(tokens[out_idx], f)
                out_path = f + ".ffout" if cand == f else cand
                argv[out_idx] = out_path
            # any leftover placeholder token -> output path
            for k, t in enumerate(argv):
                if t.startswith("mltb"):
                    argv[k] = out_path
            cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error"] + argv
            rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-ff")
            if rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                if out_path.endswith(".ffout") and os.path.abspath(out_path) != os.path.abspath(f):
                    os.replace(out_path, f)
                    produced.append(f)
                else:
                    produced.append(out_path)
                    if delete_input and os.path.abspath(out_path) != os.path.abspath(f):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
            else:
                if os.path.exists(out_path) and out_path.endswith(".ffout"):
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                errors.append(f"-ff {os.path.basename(f)}: {err or 'failed'}")
    return produced, errors


# ------------------------------------------------------ metadata (-meta)

def parse_meta_spec(spec):
    """'k=v\\|k2=v2' -> [(k, v)] with escaped pipes kept literal."""
    pairs, buf, i = [], "", 0
    s = spec or ""
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf += "|"
            i += 2
            continue
        if ch == "|":
            pairs.append(buf)
            buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    if buf:
        pairs.append(buf)
    out = []
    for p in pairs:
        m = META_PAIR_RE.match(p.strip())
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _resolve_meta_vars(value: str, file_path: str) -> str:
    name = os.path.basename(file_path)
    stem, ext = os.path.splitext(name)
    year = ""
    m = re.search(r"(19|20)\d{2}", stem)
    if m:
        year = m.group(0)
    return (
        value.replace("{filename}", name)
        .replace("{basename}", stem)
        .replace("{extension}", ext.lstrip("."))
        .replace("{year}", year)
        .replace("{audiolang}", "und")
        .replace("{sublang}", "none")
    )


async def apply_custom_metadata(path, spec, task_id=None, should_stop=None):
    """NexonBots -meta: ffmpeg -c copy -metadata k=v for every media file."""
    pairs = parse_meta_spec(spec)
    if not pairs:
        return ["-meta: could not understand the format (key=value|key2=value2)"]
    errors, done = [], 0
    for f in gather_files(path):
        if should_stop and should_stop():
            break
        if not (_is_video(f) or _is_audio(f)):
            continue
        directory, name = os.path.split(f)
        stem, ext = os.path.splitext(name)
        # keep a real container extension so ffmpeg can pick the muxer
        out = os.path.join(directory, stem + ".meta" + (ext or ".mkv"))
        cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error", "-i", f, "-map", "0", "-c", "copy"]
        for k, v in pairs:
            cmd += ["-metadata", f"{k}={_resolve_meta_vars(v, f)}"]
        if os.path.splitext(f)[1].lower() in (".mp4", ".m4v"):
            cmd += ["-movflags", "+faststart"]
        cmd.append(out)
        rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-meta")
        if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            try:
                os.replace(out, f)
                done += 1
            except OSError as e:
                errors.append(f"{os.path.basename(f)}: {e}")
                if os.path.exists(out):
                    os.remove(out)
        else:
            if os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass
            errors.append(f"{os.path.basename(f)}: {err or 'metadata failed'}")
    return errors


# ----------------------------------------------------- name swap (-ns)

_NAME_SWAP_FLAG_MAP = {"NOFLAG": 0, "I": re.I, "M": re.M, "S": re.S, "X": re.X}


def parse_name_swap(spec):
    """NexonBots common.py:330 - 'pattern:replace:count:FLAG|grp2' -> rules."""
    rules = []
    for group in (spec or "").split("|"):
        if not group.strip():
            continue
        parts = group.split(":")
        pattern = parts[0] if parts else ""
        replace = parts[1] if len(parts) > 1 else ""
        count = 0
        if len(parts) > 2 and parts[2]:
            try:
                count = int(parts[2])
            except ValueError:
                count = 0
        flags = 0
        if len(parts) > 3 and parts[3]:
            raw = parts[3].upper()
            flags = _NAME_SWAP_FLAG_MAP.get(raw, 0)
            if isinstance(flags, int) and not raw.isalpha():
                flags = 0
        if pattern:
            rules.append((pattern, replace, count, flags))
    return rules


async def apply_name_swap(path, spec, should_stop=None):
    rules = parse_name_swap(spec)
    if not rules:
        return 0, ["-ns: pattern is empty"]
    renamed, errors = 0, []

    def _swap(name):
        for pattern, replace, count, flags in rules:
            try:
                name = re.sub(pattern, replace, name, count=count, flags=flags)
            except re.error as e:
                errors.append(f"-ns bad pattern '{pattern}': {e}")
        return name

    targets = []
    if os.path.isfile(path):
        targets.append(path)
    else:
        for root, dirs, names in os.walk(path, topdown=False):
            for n in names:
                targets.append(os.path.join(root, n))
            for d in dirs:
                targets.append(os.path.join(root, d))
    for p in targets:
        if should_stop and should_stop():
            break
        directory, name = os.path.split(p)
        new_name = _swap(name).strip()
        if not new_name or new_name == name:
            continue
        new_name = new_name[:255]
        new_path = os.path.join(directory, new_name)
        if os.path.exists(new_path):
            errors.append(f"{name}: target exists, rename skipped")
            continue
        try:
            os.rename(p, new_path)
            renamed += 1
        except OSError as e:
            errors.append(f"{name}: {e}")
    return renamed, errors


# -------------------------------------------------- screenshots (-ss)

async def make_screenshots(path, value, task_id=None, should_stop=None):
    try:
        count = int(str(value)) if value is not True else 10
    except (TypeError, ValueError):
        count = 10
    count = max(1, min(count, 50))
    dirs, errors = [], []
    videos = [f for f in gather_files(path) if _is_video(f)]
    for v in videos:
        if should_stop and should_stop():
            break
        dur = get_video_duration(v)
        if not dur or dur < 1:
            errors.append(f"{os.path.basename(v)}: duration not found")
            continue
        ts = equal_timestamps(dur, count)
        if not ts:
            errors.append(f"{os.path.basename(v)}: timestamps could not be created")
            continue
        out_dir = os.path.join(
            os.path.dirname(v), os.path.splitext(os.path.basename(v))[0] + "_mltbss"
        )
        try:
            files = await grab_frames(v, ts, out_dir, task_id)
            if files:
                dirs.append(out_dir)
            else:
                errors.append(f"{os.path.basename(v)}: screenshots failed")
        except Exception as e:
            errors.append(f"{os.path.basename(v)}: {e}")
    return dirs, errors


# -------------------------------------------- convert media (-cv / -ca)

def _spec_targets(value):
    """NexonBots common.py:1132 - 'mkv - webm flv' -> (target, op, listed)."""
    data = str(value or "").split()
    if not data:
        return None, None, []
    target = data[0].lower().lstrip(".")
    op = None
    listed = []
    if len(data) > 2 and data[1] in ("+", "-"):
        op = data[1]
        listed = [x.lower().lstrip(".") for x in data[2:]]
    return target, op, listed


def _convert_wanted(ext, target, op, listed):
    ext = ext.lower().lstrip(".")
    if ext == target:
        return False
    if op == "+":
        return ext in listed
    if op == "-":
        return ext not in listed
    return True


async def _convert_one_video(f, target, task_id=None, should_stop=None):
    out = os.path.splitext(f)[0] + "." + target
    if out == f:
        return None, ""
    sub = SUB_CODEC_BY_EXT.get(target, "copy")
    # 1) stream copy remux
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
        "-i", f, "-map", "0", "-c", "copy",
        "-c:s", sub, out,
    ]
    rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-cv(copy)")
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        return out, ""
    if os.path.exists(out):
        try:
            os.remove(out)
        except OSError:
            pass
    if should_stop and should_stop():
        return None, "cancelled"
    # 2) re-encode
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
        "-i", f, "-map", "0:v", "-map", "0:a?", "-map", "0:s?",
        "-c:v", _setting(codec, DEFAULT_CODEC),
        "-preset", _setting(preset, DEFAULT_PRESET),
        "-crf", _setting(crf, DEFAULT_CRF),
        "-c:a", "aac", "-b:a", _setting(audio_b, DEFAULT_AUDIO_B),
        "-c:s", sub, "-map_metadata", "0", out,
    ]
    rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-cv")
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        return out, ""
    if os.path.exists(out):
        try:
            os.remove(out)
        except OSError:
            pass
    return None, err or "convert failed"


async def _convert_one_audio(f, target, task_id=None, should_stop=None):
    out = os.path.splitext(f)[0] + "." + target
    if out == f:
        return None, ""
    acodec = AUDIO_CODECS.get(target)
    if not acodec:
        return None, f"audio target '{target}' not supported (mp3 m4a ogg opus flac wav ac3)"
    br = _setting(audio_b, DEFAULT_AUDIO_B) if target not in ("flac", "wav") else None
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
        "-i", f, "-vn", "-map", "0:a:0?",
        "-c:a", acodec,
    ]
    if br:
        cmd += ["-b:a", br]
    cmd += ["-map_metadata", "0", out]
    rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-ca")
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        return out, ""
    if os.path.exists(out):
        try:
            os.remove(out)
        except OSError:
            pass
    return None, err or "audio convert failed"


async def convert_media(path, cv=None, ca=None, task_id=None, should_stop=None):
    """NexonBots -cv/-ca: convert containers, original deleted on success."""
    converted, errors = [], []
    targets = []
    if cv:
        targets.append(("video", cv))
    if ca:
        targets.append(("audio", ca))
    for kind, value in targets:
        target, op, listed = _spec_targets(value)
        if not target:
            errors.append(f"-{'cv' if kind == 'video' else '-ca'}: target missing")
            continue
        for f in gather_files(path):
            if should_stop and should_stop():
                break
            ext = os.path.splitext(f)[1].lower().lstrip(".")
            if kind == "video":
                if not _is_video(f):
                    continue
            else:
                if not _is_audio(f):
                    continue
            if not _convert_wanted(ext, target, op, listed):
                continue
            if kind == "video":
                out, err = await _convert_one_video(f, target, task_id, should_stop)
            else:
                out, err = await _convert_one_audio(f, target, task_id, should_stop)
            if out:
                try:
                    os.remove(f)
                    converted.append(out)
                    LOGGER.info(f"[LeechPost] Converted {os.path.basename(f)} -> {out}")
                except OSError as e:
                    errors.append(f"{os.path.basename(f)}: {e}")
            elif err and err != "cancelled":
                errors.append(f"{os.path.basename(f)}: {err}")
    return converted, errors


# ------------------------------------------------- sample video (-sv)

async def make_sample(path, value, task_id=None, should_stop=None):
    """NexonBots -sv: head/middle/tail segments -> SAMPLE.<name>."""
    sample_dur, part_dur = 60, 4
    if isinstance(value, str) and value.strip():
        bits = value.split(":")
        try:
            if bits[0]:
                sample_dur = int(bits[0])
            if len(bits) > 1 and bits[1]:
                part_dur = int(bits[1])
        except ValueError:
            errors = [f"-sv: could not understand value '{value}' (e.g. 70:5)"]
            return [], errors
    produced, errors = [], []
    part_dur = max(1, min(part_dur, sample_dur))
    for v in [f for f in gather_files(path) if _is_video(f)]:
        if should_stop and should_stop():
            break
        dur = get_video_duration(v)
        if not dur or dur < 2:
            errors.append(f"{os.path.basename(v)}: duration too short")
            continue
        if dur <= sample_dur:
            # short video: copy whole file as sample
            out = os.path.join(os.path.dirname(v), "SAMPLE." + os.path.basename(v))
            cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
                   "-i", v, "-map", "0", "-c", "copy", out]
            rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-sv")
            if rc == 0 and os.path.exists(out):
                produced.append(out)
            else:
                errors.append(f"{os.path.basename(v)}: {err or 'sample failed'}")
            continue

        seg = min(part_dur, dur)
        n = max(2, min(int(sample_dur / seg) + 1, 10))
        starts = [i * (dur - seg) / (n - 1) for i in range(n)]
        has_audio = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", v,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            outb, _ = await proc.communicate()
            has_audio = bool(outb.strip())
        except Exception:
            has_audio = False

        fc, inputs = [], []
        for i, s in enumerate(starts):
            e = min(s + seg, dur)
            if s >= e:
                continue
            fc.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
            inputs.append(f"[v{i}]")
            if has_audio:
                fc.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
                inputs.append(f"[a{i}]")
        if not inputs:
            errors.append(f"{os.path.basename(v)}: no segments")
            continue
        seg_count = len(inputs) // (2 if has_audio else 1)
        if has_audio:
            fc.append(
                "".join(f"[v{i}][a{i}]" for i in range(seg_count))
                + f"concat=n={seg_count}:v=1:a=1[outv][outa]"
            )
            map_args = ["-map", "[outv]", "-map", "[outa]"]
        else:
            fc.append(
                "".join(f"[v{i}]" for i in range(seg_count))
                + f"concat=n={seg_count}:v=1:a=0[outv]"
            )
            map_args = ["-map", "[outv]"]

        out = os.path.join(os.path.dirname(v), "SAMPLE." + os.path.basename(v))
        # movflags is a mov/mp4 muxer option - mkv output rejects it
        mux_flags = (
            ["-movflags", "+faststart"]
            if os.path.splitext(out)[1].lower() in (".mp4", ".m4v", ".mov")
            else []
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
            "-i", v, "-filter_complex", ";".join(fc),
        ] + map_args + [
            "-c:v", _setting(codec, DEFAULT_CODEC),
            "-preset", _setting(preset, DEFAULT_PRESET),
            "-crf", _setting(crf, DEFAULT_CRF),
            "-c:a", "aac", "-b:a", _setting(audio_b, DEFAULT_AUDIO_B),
        ] + mux_flags + [out]
        rc, err = await _run_cmd(cmd, task_id, should_stop, tag="-sv")
        if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            produced.append(out)
            LOGGER.info(f"[LeechPost] Sample created: {out}")
        else:
            if os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass
            errors.append(f"{os.path.basename(v)}: {err or 'sample failed'}")
    return produced, errors


# -------------------------------------------------------- zip (-z)

async def zip_output(path, password="", split_size=0, safe_root=None,
                     task_id=None, should_stop=None):
    """NexonBots -z: store-mode zip (7z preferred), originals removed when safe."""
    parent = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(os.path.abspath(path).rstrip("/\\"))
    # src_dir always holds `base`; `parent` may be remapped to safe_root for output
    src_dir = parent
    if safe_root and not _is_under(path, safe_root):
        parent = os.path.abspath(safe_root)
        os.makedirs(parent, exist_ok=True)
    target = os.path.join(parent, base + ".zip")

    size = 0
    if os.path.isfile(path):
        size = os.path.getsize(path)
    else:
        for f in gather_files(path):
            try:
                size += os.path.getsize(f)
            except OSError:
                pass

    sevenz = which("7z") or which("7za") or which("7zz")
    outputs, errors = [], []

    if sevenz:
        cmd = [sevenz, "a", "-mx=0", "-mmt=on", "-y"]
        if password:
            cmd.append(f"-p{password}")
        if split_size and size > split_size:
            cmd.append(f"-v{split_size}b")
        cmd += [target, base]
        rc, err = await _run_cmd_quiet(
            cmd, cwd=src_dir, task_id=task_id, should_stop=should_stop, tag="-z"
        )
        if rc == 0:
            outputs = sorted(
                os.path.join(parent, n)
                for n in os.listdir(parent)
                if n.startswith(base + ".zip")
            )
        else:
            errors.append(f"zip failed: {err or '7z error'}")
            return [], errors
    else:
        if password:
            return [], ["password zip needs 7z (p7zip-full in Docker/Streamlit)"]
        try:
            import zipfile
            tmp = target + ".tmp"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                if os.path.isfile(path):
                    zf.write(path, base)
                else:
                    for root, _, names in os.walk(path):
                        for n in names:
                            full = os.path.join(root, n)
                            rel = os.path.relpath(full, src_dir)
                            zf.write(full, rel)
            os.replace(tmp, target)
            outputs = [target]
        except Exception as e:
            if os.path.exists(target + ".tmp"):
                try:
                    os.remove(target + ".tmp")
                except OSError:
                    pass
            return [], [f"zip failed: {e}"]
        if split_size and size > split_size:
            try:
                parts = await asyncio.to_thread(binary_split_file, target, split_size)
                os.remove(target)
                outputs = parts
            except Exception as e:
                errors.append(f"zip split failed: {e}")

    # originals drop only inside the task dir (NexonBots deletes after zip)
    if safe_root and _is_under(path, safe_root):
        try:
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError as e:
            errors.append(f"original cleanup: {e}")
    elif not safe_root:
        pass
    return outputs, errors


async def _run_cmd_quiet(cmd, cwd=None, task_id=None, should_stop=None, tag="cmd"):
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    if task_id:
        try:
            from bot.task_manager import task_manager
            task_manager.register_process(task_id, proc)
        except Exception:
            pass
    _, stderr = await proc.communicate()
    if should_stop and should_stop():
        return -1, "cancelled"
    err = (stderr or b"").decode("utf-8", errors="ignore")[-400:]
    if proc.returncode != 0:
        LOGGER.warning(f"[LeechPost] {tag} failed rc={proc.returncode}: {err}")
    return proc.returncode or 0, err


# -------------------------------------------------------- orchestrator

async def run_leech_pipeline(
    dl_path,
    fargs,
    *,
    download_dir=None,
    task_id=None,
    user_id=None,
    should_stop=None,
    set_phase=None,
    set_detail=None,
    force=False,
):
    """
    NexonBots post-download order. Returns (path, errors).
    Mutates files under dl_path; extraction may change the returned path.
    """
    from bot.task_manager import PHASE_PROCESSING

    errors = []

    async def _step(label, coro_factory, heavy=False):
        if should_stop and should_stop():
            return
        if set_detail:
            await set_detail(label)
        if set_phase and task_id:
            await set_phase(PHASE_PROCESSING)
        if heavy and task_id and not force:
            from bot.task_manager import task_manager
            async with task_manager.heavy_slot(task_id):
                res = await coro_factory()
        else:
            res = await coro_factory()
        return res

    # 1) join
    if fargs.get("-j"):
        res = await _step("Joining split parts...", lambda: join_split_parts(dl_path, should_stop))
        if res:
            _, errs = res
            errors += errs

    # 2) extract
    if fargs.get("-e"):
        pwd = fargs.get("-e") if isinstance(fargs.get("-e"), str) else ""
        res = await _step(
            "Extracting archive...",
            lambda: extract_downloaded(
                dl_path, password=pwd, should_stop=should_stop,
                safe_root=download_dir,
            ),
        )
        if res:
            new_path, count, errs = res
            errors += errs
            if new_path and os.path.exists(new_path):
                dl_path = new_path
            if count:
                LOGGER.info(f"[LeechPost] Extracted {count} archive(s)")

    # 3) custom ffmpeg cmds
    if fargs.get("-ff"):
        res = await _step(
            "Running ffmpeg cmds...",
            lambda: run_ffmpeg_cmds(dl_path, fargs.get("-ff"), task_id, should_stop),
            heavy=True,
        )
        if res:
            _, errs = res
            errors += errs

    # 4) metadata (DB first, then -meta so -meta wins)
    db_meta = False
    if user_id:
        try:
            from database import db
            db_meta = (await db.get_metadata(user_id) or "").lower() == "on"
        except Exception:
            db_meta = False
    if db_meta or fargs.get("-meta"):
        async def _meta_step():
            for f in list(gather_files(dl_path)):
                if should_stop and should_stop():
                    break
                if not (_is_video(f) or _is_audio(f)):
                    continue
                current = f
                if db_meta:
                    try:
                        from bot.helper_funcs.utils import add_metadata
                        out = os.path.join(
                            os.path.dirname(f), f"meta_{os.path.basename(f)}"
                        )
                        newf = await add_metadata(current, out, user_id)
                        if newf and os.path.exists(newf) and os.path.abspath(newf) != os.path.abspath(current):
                            os.replace(newf, current)
                    except Exception as e:
                        errors.append(f"db metadata: {e}")
                if fargs.get("-meta"):
                    errors.extend(
                        await apply_custom_metadata(
                            current, fargs.get("-meta"), task_id, should_stop
                        )
                    )
            return None
        await _step("Applying metadata...", _meta_step)

    # 5) name swap
    if fargs.get("-ns"):
        res = await _step(
            "Swapping names...",
            lambda: apply_name_swap(dl_path, fargs.get("-ns"), should_stop),
        )
        if res:
            _, errs = res
            errors += errs

    # 6) screenshots
    if fargs.get("-ss"):
        res = await _step(
            "Generating screenshots...",
            lambda: make_screenshots(
                dl_path, fargs.get("-ss"), task_id, should_stop
            ),
            heavy=True,
        )
        if res:
            _, errs = res
            errors += errs

    # 7) convert
    if fargs.get("-cv") or fargs.get("-ca"):
        res = await _step(
            "Converting media...",
            lambda: convert_media(
                dl_path, fargs.get("-cv") or None, fargs.get("-ca") or None,
                task_id, should_stop,
            ),
            heavy=True,
        )
        if res:
            _, errs = res
            errors += errs

    # 8) sample video
    if fargs.get("-sv"):
        res = await _step(
            "Creating sample video...",
            lambda: make_sample(dl_path, fargs.get("-sv"), task_id, should_stop),
            heavy=True,
        )
        if res:
            _, errs = res
            errors += errs

    # 9) zip
    upload_files = None
    if fargs.get("-z"):
        pwd = fargs.get("-z") if isinstance(fargs.get("-z"), str) else ""
        split_size = 0
        try:
            from bot.helper_funcs.flags import parse_split_size
            split_size = parse_split_size(fargs.get("-sp"))
        except Exception:
            split_size = 0
        res = await _step(
            "Zipping output...",
            lambda: zip_output(
                dl_path, password=pwd, split_size=split_size,
                safe_root=download_dir, task_id=task_id, should_stop=should_stop,
            ),
            heavy=True,
        )
        if res:
            outs, errs = res
            errors += errs
            if outs:
                upload_files = outs
                if len(outs) == 1 and os.path.isdir(outs[0]):
                    dl_path = outs[0]
                elif len(outs) == 1:
                    dl_path = outs[0]
                else:
                    dl_path = download_dir or os.path.dirname(outs[0])

    if set_detail:
        await set_detail("")
    return dl_path, errors, upload_files
