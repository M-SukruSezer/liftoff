"""Host sistemine erişim katmanı.

Uygulama normalde doğrudan host üzerinde çalışır ve bu modülün tamamı
etkisizdir. Flatpak kumlaması içinde çalışırken ise:

* host komutları (``systemctl``, ``pkexec``) ``flatpak-spawn --host`` ile
  çalıştırılır,
* host'un ``/etc`` ağacı kumlamada ``/run/host/etc`` altında görünür,
* bir programın var olup olmadığı kumlamada değil host'ta aranır.

Kumlama dışında hiçbir davranış değişmez.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

FLATPAK_INFO = Path("/.flatpak-info")
HOST_ROOT = Path("/run/host")

_which_cache: dict[str, str | None] = {}


def in_flatpak() -> bool:
    """Flatpak kumlaması içinde miyiz?"""
    return FLATPAK_INFO.exists()


def host_path(path: str | Path) -> Path:
    """Host dosya sistemindeki bir yolu, buradan okunabilecek yola çevirir.

    Ev dizini kumlamaya olduğu gibi bağlandığı için dokunulmaz; ``/etc``
    gibi sistem dizinleri ``/run/host`` altına haritalanır.
    """
    p = Path(path)
    if not in_flatpak() or not p.is_absolute():
        return p
    try:
        home = Path.home()
        if p == home or home in p.parents:
            return p
    except RuntimeError:
        pass
    mapped = HOST_ROOT / p.relative_to("/")
    # Host /etc bağlanmamışsa (izin verilmemişse) olduğu gibi bırak.
    return mapped if HOST_ROOT.is_dir() and mapped.exists() else p


def command(argv: list[str]) -> list[str]:
    """Komutu, gerekiyorsa host üzerinde çalışacak biçime sarar."""
    if in_flatpak():
        return ["flatpak-spawn", "--host", *argv]
    return list(argv)


def which(program: str) -> str | None:
    """``program`` host üzerinde var mı? Sonucu önbelleğe alır."""
    if program in _which_cache:
        return _which_cache[program]

    if not in_flatpak():
        result = shutil.which(program)
    else:
        try:
            proc = subprocess.run(
                ["flatpak-spawn", "--host", "sh", "-c",
                 'command -v "$1" || true', "sh", program],
                capture_output=True, text=True, timeout=15,
            )
            result = proc.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            result = None

    _which_cache[program] = result
    return result


def describe() -> str:
    """Günlüklerde işe yarayan kısa ortam özeti."""
    if not in_flatpak():
        return "host üzerinde çalışıyor"
    try:
        info = FLATPAK_INFO.read_text(encoding="utf-8", errors="replace")
        app = ""
        for line in info.splitlines():
            if line.startswith("name="):
                app = line.partition("=")[2].strip()
                break
    except OSError:
        app = ""
    return f"Flatpak kumlaması içinde çalışıyor ({app or 'bilinmeyen'})"
