"""Satır bazlı .desktop dosyası okuyucu/yazıcı.

Yorumları, boş satırları ve anahtar sırasını koruyarak düzenleme yapar;
böylece bir girdiyi devre dışı bırakıp geri açtığımızda dosya bozulmaz.
"""

from __future__ import annotations

import locale
import os
import re
from pathlib import Path

GROUP = "Desktop Entry"

_GROUP_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z0-9-]+)(?P<loc>\[[^\]]+\])?\s*=\s*(?P<value>.*)$")

TRUE_VALUES = {"true", "1", "yes", "on"}


def is_true(value: str | None) -> bool:
    return value is not None and value.strip().lower() in TRUE_VALUES


def _locale_candidates() -> list[str]:
    """Mevcut yerel ayar için [tr_TR.UTF-8] -> [tr_TR] -> [tr] sırası."""
    lang = os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    if not lang:
        try:
            lang = locale.getdefaultlocale()[0] or ""
        except Exception:
            lang = ""
    lang = lang.split(":")[0].split(".")[0]
    out: list[str] = []
    if lang:
        out.append(lang)
        if "_" in lang:
            out.append(lang.split("_")[0])
    return out


class DesktopFile:
    """Tek bir .desktop dosyası."""

    def __init__(self, path: Path | None = None, lines: list[str] | None = None):
        self.path = Path(path) if path else None
        self.lines: list[str] = lines if lines is not None else []

    # ------------------------------------------------------------------ okuma

    @classmethod
    def load(cls, path: Path | str) -> "DesktopFile":
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        return cls(path=path, lines=text.splitlines())

    def _group_bounds(self) -> tuple[int, int]:
        """[Desktop Entry] grubunun (başlangıç, bitiş) satır aralığı."""
        start = -1
        for i, line in enumerate(self.lines):
            m = _GROUP_RE.match(line)
            if not m:
                continue
            if start == -1 and m.group("name") == GROUP:
                start = i + 1
            elif start != -1:
                return start, i
        if start == -1:
            return -1, -1
        return start, len(self.lines)

    def get(self, key: str, localized: bool = False) -> str | None:
        start, end = self._group_bounds()
        if start == -1:
            return None
        plain: str | None = None
        by_locale: dict[str, str] = {}
        for line in self.lines[start:end]:
            m = _KEY_RE.match(line)
            if not m or m.group("key") != key:
                continue
            loc = m.group("loc")
            value = m.group("value").strip()
            if loc is None:
                plain = value
            else:
                by_locale[loc[1:-1]] = value
        if localized:
            for cand in _locale_candidates():
                if cand in by_locale:
                    return by_locale[cand]
        return plain

    def entries(self) -> list[tuple[str, str]]:
        """Gruptaki tüm anahtarlar: [("Name", "..."), ("Name[tr]", "..."), ...].

        Anahtar adı yerel ek dâhil, dosyadaki sırayla döner.
        """
        start, end = self._group_bounds()
        if start == -1:
            return []
        out: list[tuple[str, str]] = []
        for line in self.lines[start:end]:
            m = _KEY_RE.match(line)
            if not m:
                continue
            raw = m.group("key") + (m.group("loc") or "")
            out.append((raw, m.group("value").strip()))
        return out

    def set_raw(self, raw_key: str, value: str) -> None:
        """``Name[tr]`` gibi yerel ekli anahtarları da yazar."""
        key, _, loc = raw_key.partition("[")
        loc = "[" + loc if loc else None
        start, end = self._group_bounds()
        if start == -1:
            self.lines.insert(0, f"[{GROUP}]")
            self.lines.insert(1, f"{raw_key}={value}")
            return
        for i in range(start, end):
            m = _KEY_RE.match(self.lines[i])
            if m and m.group("key") == key and (m.group("loc") or None) == loc:
                self.lines[i] = f"{raw_key}={value}"
                return
        insert_at = end
        while insert_at > start and not self.lines[insert_at - 1].strip():
            insert_at -= 1
        self.lines.insert(insert_at, f"{raw_key}={value}")

    def unset_raw(self, raw_key: str) -> None:
        key, _, loc = raw_key.partition("[")
        loc = "[" + loc if loc else None
        start, end = self._group_bounds()
        if start == -1:
            return
        keep = []
        for i, line in enumerate(self.lines):
            if start <= i < end:
                m = _KEY_RE.match(line)
                if m and m.group("key") == key and (m.group("loc") or None) == loc:
                    continue
            keep.append(line)
        self.lines = keep

    def get_list(self, key: str) -> list[str]:
        raw = self.get(key)
        if not raw:
            return []
        return [part.strip() for part in raw.split(";") if part.strip()]

    # ------------------------------------------------------------------ yazma

    def set(self, key: str, value: str) -> None:
        """Anahtarı grup içinde günceller, yoksa grubun sonuna ekler."""
        start, end = self._group_bounds()
        if start == -1:
            self.lines.insert(0, f"[{GROUP}]")
            self.lines.insert(1, f"{key}={value}")
            return
        for i in range(start, end):
            m = _KEY_RE.match(self.lines[i])
            if m and m.group("key") == key and m.group("loc") is None:
                self.lines[i] = f"{key}={value}"
                return
        insert_at = end
        while insert_at > start and not self.lines[insert_at - 1].strip():
            insert_at -= 1
        self.lines.insert(insert_at, f"{key}={value}")

    def unset(self, key: str) -> None:
        start, end = self._group_bounds()
        if start == -1:
            return
        keep = []
        for i, line in enumerate(self.lines):
            if start <= i < end:
                m = _KEY_RE.match(line)
                if m and m.group("key") == key and m.group("loc") is None:
                    continue
            keep.append(line)
        self.lines = keep

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("Kaydedilecek yol belli değil")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".liftoff-tmp")
        body = "\n".join(self.lines).rstrip("\n") + "\n"
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
        self.path = target
        return target

    def clone(self) -> "DesktopFile":
        return DesktopFile(path=self.path, lines=list(self.lines))
