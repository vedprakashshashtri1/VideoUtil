# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot
"""NexonBots style archive extraction for /leech (-e).

Prefers the 7z binary (p7zip-full, installed in Docker/Streamlit) and falls
back to Python's zipfile/tarfile so zip and tar still work without it.
"""
import os
import re
import gzip
import zipfile
import tarfile
import asyncio
import logging
import subprocess
from shutil import which
from collections import defaultdict

LOGGER = logging.getLogger("Archive")

ARCH_EXT = (
    ".tar.bz2", ".tar.gz", ".tar.xz", ".tar", ".tbz2", ".tgz", ".zip",
    ".7z", ".z", ".rar", ".iso", ".wim", ".cab", ".arj", ".chm", ".cpio",
    ".deb", ".dmg", ".lzh", ".lzma", ".msi", ".nsis", ".rpm", ".xar",
    ".zst", ".zstd", ".cbz", ".bz2", ".gz", ".xz", ".lzma2", ".ar",
)

FIRST_SPLIT_RE = re.compile(
    r"\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$|^(?!.*\.part\d+\.rar$).*\.rar$"
)
SPLIT_RE = re.compile(r"\.\w+\.\d{3}$|\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$|\.part\d+\.rar$")
NUM_SPLIT_RE = re.compile(r"^(.*?)(\.(?:part0*\d+|\d{3}|r\d+|z\d+))$", re.I)

STDLIB_ZIP = (".zip", ".cbz")
STDLIB_TAR = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz")


def is_archive(name: str) -> bool:
    return name.strip().lower().endswith(ARCH_EXT)


def is_first_archive_split(name: str) -> bool:
    return bool(FIRST_SPLIT_RE.search(name.strip().lower()))


def is_archive_split(name: str) -> bool:
    return bool(SPLIT_RE.search(name.strip().lower()))


def get_base_name(path: str) -> str:
    """Strip the archive (and split) suffix: /x/movie.part1.rar -> /x/movie."""
    directory, name = os.path.split(path)
    changed = True
    while changed:
        changed = False
        low = name.lower()
        for ext in sorted(ARCH_EXT, key=len, reverse=True):
            if low.endswith(ext) and len(name) > len(ext):
                name = name[: -len(ext)]
                changed = True
                break
        if not changed:
            m = NUM_SPLIT_RE.match(name)
            if m and m.group(1):
                name = m.group(1)
                changed = True
    return os.path.join(directory, name)


# compound tarball -> the file 7z drops after the compression layer
_COMPOUND_LAYERS = (
    (".tar.gz", ".tar"), (".tar.bz2", ".tar"), (".tar.xz", ".tar"),
    (".tar.lzma", ".tar"), (".tar.zst", ".tar"),
    (".tgz", ".tar"), (".tbz2", ".tar"), (".tbz", ".tar"),
    (".gz", ""), (".bz2", ""), (".xz", ""),
)


def _inner_layer_name(name: str) -> str:
    """foo.tar.gz -> foo.tar ; bar.gz -> bar (empty string when not compound)."""
    low = name.lower()
    for suf, inner in _COMPOUND_LAYERS:
        if low.endswith(suf) and len(name) > len(suf):
            return name[: -len(suf)] + inner
    return ""


def find_7z():
    for cand in ("7z", "7za", "7zz"):
        path = which(cand)
        if path:
            return path
    return None


def find_archives(path: str):
    """NexonBots proceed_extract(): the archive itself, or archives inside a folder."""
    if os.path.isfile(path):
        return [path] if (is_archive(path) or is_first_archive_split(path)) else []
    found = []
    for dirpath, _, files in os.walk(path, topdown=False):
        for f in files:
            if is_first_archive_split(f) or (is_archive(f) and not f.lower().endswith(".rar")):
                found.append(os.path.join(dirpath, f))
    return found


def _extract_one(archive: str, dest: str, password: str = "", depth: int = 0) -> bool:
    """Extract one archive. Raises on unsupported formats, returns True on success."""
    sevenz = find_7z()
    if sevenz:
        inner_name = _inner_layer_name(os.path.basename(archive))
        inner_pre = inner_name and os.path.isfile(os.path.join(dest, inner_name))
        cmd = [sevenz, "x", archive, f"-o{dest}", "-y", "-aot", "-bb0"]
        if password:
            cmd.insert(2, f"-p{password}")
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if proc.returncode == 0:
            # 7z stops after the compression layer of tar.gz/tgz/... - pull the
            # inner tar (created by this run only) so contents actually appear.
            if inner_name and not inner_pre and depth < 3:
                inner = os.path.join(dest, inner_name)
                if os.path.isfile(inner) and is_archive(inner):
                    try:
                        if _extract_one(inner, dest, password, depth + 1):
                            try:
                                os.remove(inner)
                            except OSError:
                                pass
                    except Exception as e:
                        LOGGER.warning(f"[Extract] inner layer {inner}: {e}")
            return True
        err = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"7z exited {proc.returncode}: {err}")

    low = archive.lower()
    if low.endswith(STDLIB_ZIP) and not is_archive_split(low):
        if password:
            raise RuntimeError("Password zip needs 7z (p7zip-full)")
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                # SECURITY: zip-slip - never write outside the target folder
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    LOGGER.warning(f"[Extract] Skipping unsafe zip entry: {name}")
                    continue
            zf.extractall(dest)
        return True

    if low.endswith(STDLIB_TAR):
        if password:
            raise RuntimeError("Password tar needs 7z (p7zip-full)")
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:  # Python without the filter kwarg
                tf.extractall(dest)
        return True

    if low.endswith(".gz"):
        if password:
            raise RuntimeError("Password gz needs 7z (p7zip-full)")
        target = os.path.join(dest, os.path.basename(archive)[:-3])
        with gzip.open(archive, "rb") as src, open(target, "wb") as out:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        return True

    raise RuntimeError(
        f"{os.path.splitext(archive)[1] or 'archive'} format needs 7z installed"
    )


def _delete_group(dirpath: str, members) -> None:
    """NexonBots: after a successful extract, drop the archives/splits of that folder."""
    try:
        for f in os.listdir(dirpath):
            if is_archive(f) or is_archive_split(f):
                try:
                    os.remove(os.path.join(dirpath, f))
                except OSError:
                    pass
    except OSError as e:
        LOGGER.warning(f"[Extract] Cleanup failed in {dirpath}: {e}")


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


async def extract_downloaded(path, password="", should_stop=None, safe_root=None):
    """
    Extract archives found at `path` (NexonBots style).
    Returns (upload_path, extracted_count, errors) - never raises.
    """
    if not path or not os.path.exists(path):
        return path, 0, []

    try:
        archives = await asyncio.to_thread(find_archives, path)
    except Exception as e:
        return path, 0, [str(e)]

    if not archives:
        LOGGER.info("[Extract] No archives found - uploading as-is")
        return path, 0, []

    single = os.path.isfile(path)
    upload_path = path
    extracted = 0
    errors = []
    groups = defaultdict(list)
    for arc in archives:
        groups[os.path.dirname(arc) or "."].append(arc)

    for dirpath, arcs in groups.items():
        dir_ok = True
        for arc in arcs:
            if should_stop and should_stop():
                return upload_path, extracted, errors
            dest = get_base_name(arc) if single else dirpath
            try:
                os.makedirs(dest, exist_ok=True)
                ok = await asyncio.to_thread(_extract_one, arc, dest, password or "")
            except Exception as e:
                dir_ok = False
                errors.append(f"{os.path.basename(arc)}: {e}")
                LOGGER.warning(f"[Extract] {arc}: {e}")
                continue
            if not ok:
                dir_ok = False
                errors.append(f"{os.path.basename(arc)}: extraction failed")
                continue
            extracted += 1
            if single:
                upload_path = dest
            LOGGER.info(f"[Extract] {arc} -> {dest}")

        if dir_ok:
            if safe_root and not _is_under(dirpath, safe_root):
                LOGGER.info(f"[Extract] Skipping archive cleanup outside task dir: {dirpath}")
            else:
                await asyncio.to_thread(_delete_group, dirpath, arcs)

    return upload_path, extracted, errors
