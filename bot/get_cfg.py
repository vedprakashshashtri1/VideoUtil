#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot

import os
from pathlib import Path

_dotenv_loaded = False
_colab_userdata = None
_streamlit_secrets = None


def _load_dotenv():
    """Load `.env` from the working directory (or repo root) into os.environ.

    Real environment variables always win, so platform dashboards (Heroku,
    Northflank, Koyeb, Hugging Face, Google Cloud) and Streamlit secrets
    override anything declared in `.env`.
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        path = base / ".env"
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
        break


def _simple_toml(text):
    """Minimal `key = value` / `[section]` parser used when tomllib is missing."""
    out, section = {}, ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().strip("\"'") + "."
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().strip("\"'")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[section + key] = value
    return out


def _flatten_secrets(mapping, prefix=""):
    flat = {}
    for key, value in mapping.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten_secrets(value, prefix=f"{path}."))
        elif isinstance(value, bool):
            flat[path] = "1" if value else "0"
        elif isinstance(value, (int, float)):
            flat[path] = str(value)
        elif isinstance(value, str):
            flat[path] = value
    return flat


def _load_streamlit_secrets():
    """Read `.streamlit/secrets.toml` from the working directory or repo root.

    Lets the bot read Streamlit Community Cloud secrets directly, even when a
    launcher script did not forward them as environment variables.
    """
    global _streamlit_secrets
    if _streamlit_secrets is not None:
        return _streamlit_secrets
    _streamlit_secrets = {}
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        path = base / ".streamlit" / "secrets.toml"
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        data = None
        try:
            import tomllib
            data = tomllib.loads(raw)
        except Exception:
            data = _simple_toml(raw)
        if isinstance(data, dict):
            _streamlit_secrets = _flatten_secrets(data)
        break
    return _streamlit_secrets


def _streamlit_get(name):
    secrets_map = _load_streamlit_secrets()
    if not secrets_map:
        return None
    if name in secrets_map:
        return secrets_map[name]
    lowered = name.lower()
    for key, value in secrets_map.items():
        if key.lower() == lowered or key.rsplit(".", 1)[-1].lower() == lowered:
            return value
    return None


def _colab_get(name):
    """Fetch a secret from Google Colab's Secrets storage when available."""
    global _colab_userdata
    if _colab_userdata is None:
        try:
            from google.colab import userdata  # type: ignore

            _colab_userdata = userdata
        except Exception:
            _colab_userdata = False
    if _colab_userdata is False:
        return None
    try:
        return _colab_userdata.get(name)
    except Exception:
        return None


def get_config(name: str, d_v=None, should_prompt=False):
    # Priority: real env var > Streamlit secrets > .env file > Colab secrets
    val = os.environ.get(name)
    if not val:
        val = _streamlit_get(name)
    if not val:
        _load_dotenv()
        val = os.environ.get(name)
    if not val:
        val = _colab_get(name)
    if not val:
        val = d_v
    if not val and should_prompt:
        try:
            val = input(f"enter {name}'s value: ")
        except EOFError:
            val = d_v
        print("\n")
    return val
