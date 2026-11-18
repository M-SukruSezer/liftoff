"""Kurulu uygulamaları listeler.

Başlangıca yeni bir girdi eklerken komutu elle yazmak yerine kurulu
uygulamalardan birini seçebilmek için kullanılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .desktop import DesktopFile, is_true
from .icons import _application_dirs

# Exec satırındaki %f, %U gibi alan kodları autostart girdisinde anlamsızdır.
_FIELD_CODE = re.compile(r"\s*%[fFuUdDnNickvm]")


@dataclass(frozen=True)
class App:
    """Kurulu bir uygulama."""

    app_id: str          # .desktop dosyasının adı (uzantısız)
    name: str
    comment: str
    icon: str
    command: str
    terminal: bool
    path: Path

    @property
    def search_blob(self) -> str:
        return " ".join([self.name, self.app_id, self.comment,
                         self.command]).casefold()


def clean_command(exec_line: str) -> str:
    """Exec satırından alan kodlarını atar."""
    return _FIELD_CODE.sub("", exec_line).strip()


def installed() -> list[App]:
    """Menüde görünen kurulu uygulamalar, ada göre sıralı."""
    found: dict[str, App] = {}
    for directory in _application_dirs():
        try:
            paths = sorted(directory.glob("*.desktop"))
        except OSError:
            continue
        for path in paths:
            app_id = path.name.removesuffix(".desktop")
            if app_id in found:
                continue  # önce gelen dizin (kullanıcı) kazanır
            try:
                df = DesktopFile.load(path)
            except OSError:
                continue
            if (df.get("Type") or "Application").strip() != "Application":
                continue
            if is_true(df.get("NoDisplay")) or is_true(df.get("Hidden")):
                continue
            name = (df.get("Name", localized=True) or "").strip()
            command = clean_command(df.get("Exec") or "")
            if not name or not command:
                continue
            found[app_id] = App(
                app_id=app_id,
                name=name,
                comment=(df.get("Comment", localized=True) or "").strip(),
                icon=(df.get("Icon") or "").strip(),
                command=command,
                terminal=is_true(df.get("Terminal")),
                path=path,
            )
    return sorted(found.values(), key=lambda a: a.name.casefold())
