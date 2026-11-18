"""Flatpak arka plan (autostart) izinleri.

Flatpak uygulamaları kendiliğinden başlamak için ``~/.config/autostart``
dizinine doğrudan dosya yazmaz; bunu xdg-desktop-portal onlar adına yapar
ve izni kendi izin deposunda tutar. Dosyaya ``Hidden=true`` yazmak bu
yüzden tek başına yetmez: uygulama bir dahaki çalışmasında portaldan
arka planda çalışma izni ister, izin hâlâ "yes" olduğu için portal
autostart dosyasını yeniden yazar ve uygulama yine açılışta başlar.

Bu modül izin deposunu ``flatpak permission-set`` ile günceller; GNOME
Ayarlar'daki "Arka planda çalıştır" anahtarı da aynı kaydı değiştirir.
"""

from __future__ import annotations

import subprocess

from . import host

TABLE = "background"
PERMISSION_ID = "background"
TIMEOUT = 20

# Portalın yazdığı autostart dosyalarında uygulama kimliğini taşıyan
# anahtarlar.
APP_ID_KEYS = ("X-Flatpak", "X-XDP-Autostart")


def available() -> bool:
    return host.which("flatpak") is not None


def _run(args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            host.command(["flatpak", *args]),
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def background_permissions() -> dict[str, bool]:
    """{uygulama kimliği: arka planda çalışabilir mi}.

    Kayıt yoksa uygulama listede görünmez; bu "henüz sorulmadı" demektir
    ve kısıtlama sayılmaz.
    """
    if not available():
        return {}
    proc = _run(["permission-list", TABLE])
    if proc is None or proc.returncode != 0:
        return {}
    out: dict[str, bool] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        _table, perm_id, app_id, value = parts[0], parts[1], parts[2], parts[3]
        if perm_id != PERMISSION_ID or not app_id:
            continue
        out[app_id] = value.strip().casefold() not in ("no", "none", "")
    return out


def set_background(app_id: str, allowed: bool) -> bool:
    """Uygulamanın arka planda çalışma (ve autostart) iznini ayarlar."""
    if not app_id or not available():
        return False
    proc = _run([
        "permission-set", TABLE, PERMISSION_ID, app_id,
        "yes" if allowed else "no",
    ])
    return proc is not None and proc.returncode == 0
