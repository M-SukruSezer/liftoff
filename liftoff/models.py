"""Arayüzün gösterdiği ortak veri modeli."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .i18n import gettext as _


@dataclass(frozen=True)
class Note:
    """Bir girdi hakkında kullanıcıya gösterilecek açıklama.

    Metin İngilizce *kaynak* olarak saklanır ve ekrana basılırken çevrilir;
    böylece dil değişince mevcut notlar da anında dile uyar.
    """

    text: str
    args: tuple = ()
    warn: bool = False

    def render(self) -> str:
        translated = _(self.text)
        return translated % self.args if self.args else translated


class Source(str, Enum):
    """Girdinin nereden geldiği."""

    AUTOSTART = "autostart"       # ~/.config/autostart ve /etc/xdg/autostart
    USER_UNIT = "user-unit"       # systemctl --user
    SYSTEM_UNIT = "system-unit"   # systemctl (root gerekir)

    @property
    def title(self) -> str:
        return _({
            Source.AUTOSTART: "Applications",
            Source.USER_UNIT: "User services",
            Source.SYSTEM_UNIT: "System services",
        }[self])


class Scope(str, Enum):
    USER = "user"      # kullanıcıya ait, serbestçe düzenlenebilir
    SYSTEM = "system"  # sistem geneli, kullanıcı kopyası ile gölgelenir
    BOTH = "both"      # sistem girdisinin kullanıcı kopyası var

    @property
    def title(self) -> str:
        return _({
            Scope.USER: "Only this user",
            Scope.SYSTEM: "System-wide",
            Scope.BOTH: "System entry + your setting",
        }[self])


@dataclass
class Item:
    """Başlangıçta çalışan tek bir şey."""

    key: str                      # kaynak içinde tekil kimlik (dosya / unit adı)
    source: Source
    name: str
    enabled: bool
    description: str = ""
    command: str = ""
    icon: str = ""
    scope: Scope = Scope.USER
    toggleable: bool = True
    needs_root: bool = False
    hidden_entry: bool = False    # NoDisplay=true -> arka plan bileşeni
    running: bool | None = None
    notes: list[Note] = field(default_factory=list)
    user_path: str | None = None
    system_path: str | None = None
    unit_state: str = ""
    critical: bool = False

    @property
    def sort_key(self) -> tuple:
        return (self.hidden_entry, self.name.casefold(), self.key)

    @property
    def search_blob(self) -> str:
        return " ".join(
            [self.name, self.key, self.description, self.command]
        ).casefold()
