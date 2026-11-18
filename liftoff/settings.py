"""Kullanıcı tercihlerini ~/.config/liftoff/settings.json içinde saklar."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import i18n


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "liftoff"


def config_file() -> Path:
    return config_dir() / "settings.json"


def load() -> dict:
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def stored_language() -> str | None:
    """Kullanıcının daha önce seçtiği dil; hiç seçmediyse None."""
    value = load().get("language")
    return value if value in i18n.LANGUAGES else None


def set_language(code: str) -> None:
    data = load()
    data["language"] = code
    save(data)


def resolve_language() -> str:
    """Açılışta kullanılacak dil.

    Kullanıcı bir kez seçtiyse o kalır. Hiç seçmediyse (ilk kurulum)
    sistem dili Türkçe ise Türkçe, diğer her durumda İngilizce.
    """
    return stored_language() or i18n.detect_system_language()
