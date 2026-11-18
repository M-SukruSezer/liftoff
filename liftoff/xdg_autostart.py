"""XDG autostart girdilerini listeleyen ve açıp kapatan arka uç.

Kurallar (freedesktop autostart spec + GNOME uyumu):
  * Kullanıcı dizini (~/.config/autostart) aynı dosya adını taşıyan sistem
    girdisini gölgeler.
  * ``Hidden=true`` girdiyi tamamen devre dışı bırakır. GNOME ayrıca
    ``X-GNOME-Autostart-enabled=false`` anahtarına bakar; ikisini birlikte
    yazıyoruz ki masaüstünden bağımsız çalışsın.
  * Sistem girdisini kapatmak için dosyayı kullanıcı dizinine kopyalayıp
    kapatma anahtarlarını ekliyoruz. Kendi oluşturduğumuz bu kopyaları
    ``X-Liftoff-Override`` ile işaretliyoruz; girdi yeniden
    açıldığında kopyayı silip sistem varsayılanına dönüyoruz.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import host
from .desktop import DesktopFile, is_true
from .i18n import gettext as _
from .models import Item, Note, Scope, Source

OVERRIDE_KEY = "X-Liftoff-Override"
# Uygulamanin eski adiyla yazilmis golge dosyalari da tanimaya devam et.
LEGACY_OVERRIDE_KEYS = ("X-Autostart-Manager-Override",)
GNOME_KEY = "X-GNOME-Autostart-enabled"


def user_dir() -> Path:
    """Kullanıcının autostart dizini.

    Flatpak, XDG_CONFIG_HOME'u uygulamanın kendi özel dizinine çevirir.
    Autostart girdilerini oraya yazmak işe yaramaz: oturum yöneticisi
    yalnızca gerçek ~/.config/autostart dizinini okur. Bu yüzden kumlama
    içinde değişkeni yok sayıyoruz.
    """
    if host.in_flatpak():
        return Path.home() / ".config" / "autostart"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart"


def system_dirs() -> list[Path]:
    """Sistem geneli autostart dizinleri.

    Flatpak içinde host'un /etc ağacı /run/host/etc altında görünür;
    ``host.host_path`` bunu çözer, kumlama dışında hiçbir şey değişmez.
    """
    raw = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    dirs = [host.host_path(Path(part) / "autostart")
            for part in raw.split(":") if part.strip()]
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def current_desktops() -> set[str]:
    raw = os.environ.get("XDG_CURRENT_DESKTOP") or ""
    return {part.strip().casefold() for part in raw.split(":") if part.strip()}


def _desktop_files(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        return {}
    out: dict[str, Path] = {}
    try:
        for entry in sorted(directory.iterdir()):
            if entry.is_file() and entry.name.endswith(".desktop"):
                out[entry.name] = entry
    except PermissionError:
        return {}
    return out


def _entry_enabled(df: DesktopFile) -> bool:
    if is_true(df.get("Hidden")):
        return False
    gnome = df.get(GNOME_KEY)
    if gnome is not None and not is_true(gnome):
        return False
    return True


def _tryexec_missing(df: DesktopFile) -> bool:
    """Girdinin çalıştırılabilir dosyası host üzerinde var mı?"""
    tryexec = df.get("TryExec")
    if not tryexec:
        return False
    if "/" in tryexec:
        return not os.access(host.host_path(tryexec), os.X_OK)
    return host.which(tryexec) is None


def _desktop_visibility_note(df: DesktopFile) -> Note | None:
    """Girdi bu masaüstü ortamında hiç çalışmıyorsa not döndürür."""
    current = current_desktops()
    if not current:
        return None
    only = {d.casefold() for d in df.get_list("OnlyShowIn")}
    not_in = {d.casefold() for d in df.get_list("NotShowIn")}
    if only and not (only & current):
        return Note(
            "Does not run in this desktop environment (only: %s)",
            (", ".join(sorted(df.get_list("OnlyShowIn"))),),
        )
    if not_in and (not_in & current):
        return Note("Does not run in this desktop environment (excluded)")
    return None


def _build_item(key: str, user_path: Path | None, system_path: Path | None) -> Item | None:
    effective = user_path or system_path
    if effective is None:
        return None
    try:
        df = DesktopFile.load(effective)
    except OSError:
        return None

    if (df.get("Type") or "Application").strip() != "Application":
        return None

    name = df.get("Name", localized=True) or key.removesuffix(".desktop")
    comment = df.get("Comment", localized=True) or ""
    command = df.get("Exec") or ""
    icon = df.get("Icon") or ""

    if user_path and system_path:
        scope = Scope.BOTH
    elif system_path:
        scope = Scope.SYSTEM
    else:
        scope = Scope.USER

    notes: list[Note] = []
    vis = _desktop_visibility_note(df)
    if vis:
        notes.append(vis)
    if _tryexec_missing(df):
        notes.append(Note("Executable not found (TryExec)", warn=True))
    if scope is Scope.BOTH:
        notes.append(Note("System entry, overridden by your setting"))
    elif scope is Scope.SYSTEM:
        notes.append(Note("System-wide entry (/etc/xdg)"))
    phase = df.get("X-GNOME-Autostart-Phase")
    if phase:
        notes.append(Note("Session startup component (phase: %s)", (phase,)))

    return Item(
        key=key,
        source=Source.AUTOSTART,
        name=name,
        enabled=_entry_enabled(df),
        description=comment,
        command=command,
        icon=icon,
        scope=scope,
        toggleable=True,
        needs_root=False,
        hidden_entry=is_true(df.get("NoDisplay")),
        notes=notes,
        user_path=str(user_path) if user_path else None,
        system_path=str(system_path) if system_path else None,
    )


def list_items() -> list[Item]:
    user_files = _desktop_files(user_dir())
    system_files: dict[str, Path] = {}
    for d in system_dirs():
        for fname, path in _desktop_files(d).items():
            system_files.setdefault(fname, path)

    items: list[Item] = []
    for key in sorted(set(user_files) | set(system_files)):
        item = _build_item(key, user_files.get(key), system_files.get(key))
        if item:
            items.append(item)
    return sorted(items, key=lambda i: i.sort_key)


def set_enabled(item: Item, enabled: bool) -> None:
    """Girdiyi açar/kapatır. Sistem girdileri için kullanıcı kopyası kullanır."""
    if enabled:
        _enable(item)
    else:
        _disable(item)


def _enable(item: Item) -> None:
    if not item.user_path:
        return  # yalnızca sistem girdisi: zaten etkin
    df = DesktopFile.load(item.user_path)
    is_ours = is_true(df.get(OVERRIDE_KEY)) or any(
        is_true(df.get(k)) for k in LEGACY_OVERRIDE_KEYS
    )
    if item.system_path and is_ours:
        # Bizim oluşturduğumuz gölge dosya: sil, sistem varsayılanına dön.
        Path(item.user_path).unlink(missing_ok=True)
        return
    df.unset("Hidden")
    df.set(GNOME_KEY, "true")
    df.save()


def _disable(item: Item) -> None:
    if item.user_path:
        df = DesktopFile.load(item.user_path)
        df.set("Hidden", "true")
        df.set(GNOME_KEY, "false")
        df.save()
        return
    if not item.system_path:
        return
    df = DesktopFile.load(item.system_path)
    df.set("Hidden", "true")
    df.set(GNOME_KEY, "false")
    df.set(OVERRIDE_KEY, "true")
    target = user_dir() / item.key
    df.save(target)
    item.user_path = str(target)
    item.scope = Scope.BOTH


def can_remove(item: Item) -> bool:
    return bool(item.user_path)


def remove(item: Item) -> str:
    """Kullanıcı girdisini siler.

    Sistem karşılığı varsa bu işlem 'varsayılana dön' anlamına gelir.
    """
    if not item.user_path:
        raise ValueError(_("A system entry cannot be deleted"))
    Path(item.user_path).unlink(missing_ok=True)
    return "restored" if item.system_path else "deleted"


def add_entry(name: str, command: str, comment: str = "") -> Path:
    """Yeni bir kullanıcı autostart girdisi oluşturur."""
    name = name.strip()
    command = command.strip()
    if not name:
        raise ValueError(_("Name cannot be empty"))
    if not command:
        raise ValueError(_("Command cannot be empty"))

    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.casefold())
    slug = "-".join(part for part in slug.split("-") if part) or "girdi"
    target = user_dir() / f"{slug}.desktop"
    counter = 2
    while target.exists():
        target = user_dir() / f"{slug}-{counter}.desktop"
        counter += 1

    df = DesktopFile(lines=["[Desktop Entry]"])
    df.set("Type", "Application")
    df.set("Name", name)
    if comment.strip():
        df.set("Comment", comment.strip())
    df.set("Exec", command)
    df.set("Terminal", "false")
    df.set(GNOME_KEY, "true")
    df.save(target)
    return target
