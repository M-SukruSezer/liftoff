"""Bir girdi için gösterilecek simge adaylarını üretir.

Amaç: uygulamanın ya da servisin kendi logosu varsa onu kullanmak.
Burada yalnızca *aday* adlar üretilir; hangisinin gerçekten var olduğuna
arayüz katmanı (``Gtk.IconTheme``) karar verir. Böylece bu modül GTK'ya
bağlı kalmaz ve arka plan iş parçacığından da çağrılabilir.
"""

from __future__ import annotations

import os
import shlex
import threading
from pathlib import Path

from .models import Item, Source

# Komut satırının başındaki bu adlar gerçek programı göstermez.
WRAPPERS = {
    "env", "sh", "bash", "dash", "zsh", "exec", "nohup", "setsid",
    "sudo", "pkexec", "systemd-run", "dbus-run-session", "dbus-launch",
    "python", "python2", "python3", "perl", "ruby", "node", "java",
    "flatpak", "snap", "xdg-open", "gtk-launch", "true", "sleep",
}

# "foo-daemon", "foo-applet" gibi adların sonundaki genel ekler: önce tam ad
# denenir, bulunamazsa bu ekler atılmış hâli denenir.
STRIP_SUFFIXES = (
    "-daemon", "-service", "-monitor", "-applet", "-autostart", "-agent",
    "-notification", "-notifier", "-helper", "-indicator", "-tray",
    "-launcher", "-session", "-manager", "-client", "-gui", "-server",
)

UNIT_SUFFIXES = (".service", ".socket", ".timer", ".path", ".target", ".mount")

# Simge temasında bu adlarda genel amaçlı görseller bulunur; bir programın
# adı bunlardan biriyse eşleşme logo değil, rastlantıdır (ör. netplan'ın
# "configure" yardımcısı).
GENERIC_NAMES = {
    "about", "agent", "application", "applications", "audio", "avatar",
    "battery", "boot", "browser", "client", "clock", "configure", "core",
    "daemon", "default", "desktop", "dialog", "display", "document",
    "emblem", "error", "file", "folder", "generic", "help", "image",
    "info", "init", "install", "launch", "launcher", "login", "logout",
    "mail", "main", "manager", "media", "monitor", "network", "package",
    "power", "preferences", "printer", "run", "scanner", "screen", "search",
    "server", "service", "session", "settings", "setup", "start", "stop",
    "system", "terminal", "text", "timer", "tool", "tools", "update",
    "updates", "user", "users", "utilities", "utility", "video", "warning",
    "web", "window",
}

_index: dict[str, str] | None = None
_index_lock = threading.Lock()


# --------------------------------------------------------------- .desktop dizini

def _application_dirs() -> list[Path]:
    """Kurulu uygulamaların .desktop dosyalarını barındıran dizinler."""
    home = Path(os.environ.get("XDG_DATA_HOME")
                or Path.home() / ".local" / "share")
    raw = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [home] + [Path(p) for p in raw.split(":") if p.strip()]
    # Flatpak ve snap dışarı aktarımları her zaman XDG_DATA_DIRS'te olmayabilir.
    dirs += [
        home / "flatpak" / "exports" / "share",
        Path("/var/lib/flatpak/exports/share"),
        Path("/var/lib/snapd/desktop"),
    ]
    out: list[Path] = []
    seen: set[Path] = set()
    for d in dirs:
        apps = d / "applications"
        if apps in seen:
            continue
        seen.add(apps)
        if apps.is_dir():
            out.append(apps)
    return out


def _read_entry(path: Path) -> tuple[str, str]:
    """Dosyadan (Icon, Exec) değerlerini okur; bulunamayan "" döner."""
    icon = exec_line = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            in_group = False
            for line in fh:
                line = line.strip()
                if line.startswith("["):
                    if in_group:
                        break
                    in_group = line == "[Desktop Entry]"
                    continue
                if not in_group:
                    continue
                if not icon and line.startswith("Icon="):
                    icon = line[5:].strip()
                elif not exec_line and line.startswith("Exec="):
                    exec_line = line[5:].strip()
                if icon and exec_line:
                    break
    except OSError:
        return "", ""
    return icon, exec_line


def index() -> dict[str, str]:
    """{arama anahtarı: simge adı} — kurulu uygulamaların simge dizini.

    Anahtarlar: .desktop dosyasının adı (uzantısız) ve komutun temel adı.
    Böylece ``syncthing.service`` için ``syncthing.desktop``un simgesi,
    Flatpak autostart girdileri için de uygulama kimliği bulunabilir.
    """
    global _index
    with _index_lock:
        if _index is not None:
            return _index

    found: dict[str, str] = {}
    for directory in _application_dirs():
        try:
            entries = sorted(directory.glob("*.desktop"))
        except OSError:
            continue
        for path in entries:
            icon, exec_line = _read_entry(path)
            if not icon:
                continue
            stem = path.name.removesuffix(".desktop")
            found.setdefault(stem.casefold(), icon)
            last = stem.rpartition(".")[2]
            if last and last != stem:
                found.setdefault(last.casefold(), icon)
            binary = _binary_name(exec_line)
            if binary:
                found.setdefault(binary.casefold(), icon)
    with _index_lock:
        if _index is None:
            _index = found
        return _index


def invalidate() -> None:
    """Listeyi yenilerken dizini de tazele."""
    global _index
    with _index_lock:
        _index = None


# ------------------------------------------------------------------- yardımcılar

def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _binary_name(command: str) -> str:
    """Komut satırından çalıştırılan programın temel adını çıkarır."""
    for token in _tokens(command):
        if "=" in token and not token.startswith("/"):
            continue  # VAR=deger biçimindeki ön ekler
        if token.startswith("-"):
            continue
        name = Path(token).name
        if name.casefold() in WRAPPERS:
            continue
        return name
    return ""


def flatpak_id(command: str) -> str:
    """``flatpak run --command=x org.ornek.Uygulama`` -> uygulama kimliği."""
    tokens = _tokens(command)
    if not tokens or Path(tokens[0]).name != "flatpak":
        return ""
    after_run = False
    for token in tokens[1:]:
        if not after_run:
            after_run = token == "run"
            continue
        if token.startswith("-"):
            continue
        if "." in token and "/" not in token:
            return token
        return ""
    return ""


def _with_stripped_suffix(name: str) -> str:
    low = name.casefold()
    for suffix in STRIP_SUFFIXES:
        if low.endswith(suffix) and len(low) > len(suffix) + 2:
            return name[: -len(suffix)]
    return ""


def unit_base(unit: str) -> str:
    """``foo@bar.service`` -> ``foo``."""
    name = unit
    for suffix in UNIT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.partition("@")[0]


def _add(out: list[str], value: str) -> None:
    if value and value not in out:
        out.append(value)


def _add_name(out: list[str], name: str) -> None:
    """Adın kendisini, kısaltılmışını ve dizindeki karşılığını ekler.

    Dizinden gelen değer kurulu bir uygulamanın kendi simgesidir, olduğu
    gibi alınır. Çıplak ad ise yalnızca genel bir tema adı değilse denenir.
    """
    if not name:
        return
    if name.casefold() not in GENERIC_NAMES:
        _add(out, name)
    _add(out, index().get(name.casefold(), ""))
    short = _with_stripped_suffix(name)
    if short:
        if short.casefold() not in GENERIC_NAMES:
            _add(out, short)
        _add(out, index().get(short.casefold(), ""))


# ----------------------------------------------------------------------- genel

def candidates(item: Item) -> list[str]:
    """Girdi için denenecek simgeler — ilk bulunan kullanılır."""
    out: list[str] = []

    # 1) Girdinin kendi bildirdiği simge her zaman önce gelir.
    _add(out, item.icon)

    if item.source is Source.AUTOSTART:
        # 2) Flatpak/snap uygulamasının kimliği.
        _add_name(out, flatpak_id(item.command))
        # 3) .desktop dosyasının adı (çoğu uygulamada simge adıyla aynıdır).
        stem = item.key.removesuffix(".desktop")
        _add_name(out, stem)
        last = stem.rpartition(".")[2]
        if last != stem:
            _add_name(out, last)
    else:
        # 2) Birim adı: pipewire.service -> pipewire
        _add_name(out, unit_base(item.key))

    # 4) Çalıştırılan programın adı.
    _add_name(out, _binary_name(item.exec_path or item.command))

    return [c for c in out if c]


def fallback(item: Item) -> str:
    """Hiçbir simge bulunamazsa kullanılacak genel görsel."""
    if item.source is Source.AUTOSTART:
        return "application-x-executable-symbolic"
    return "system-run-symbolic"
