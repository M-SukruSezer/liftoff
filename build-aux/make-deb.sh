#!/usr/bin/env bash
# Liftoff için .deb paketi üretir. Kök yetkisi gerektirmez (fakeroot kullanır).
set -euo pipefail
export LC_ALL=C

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' liftoff/__init__.py)}"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı" >&2; exit 1; }

PKG=liftoff
ARCH=all
MAINTAINER="Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com>"
STAGE="dist/${PKG}_${VERSION}_${ARCH}"
OUT="dist/${PKG}_${VERSION}_${ARCH}.deb"

for t in dpkg-deb fakeroot make; do
  command -v "$t" >/dev/null || { echo "HATA: $t bulunamadı" >&2; exit 1; }
done

rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE/DEBIAN" dist

# --- dosyalar ---------------------------------------------------------------
make --no-print-directory install DESTDIR="$STAGE" PREFIX=/usr >/dev/null

# --- belgeler ---------------------------------------------------------------
DOC="$STAGE/usr/share/doc/$PKG"
mkdir -p "$DOC"
cp LICENSE "$DOC/copyright"
printf '%s (%s) unstable; urgency=medium\n\n  * Liftoff %s\n\n -- %s  %s\n' \
  "$PKG" "$VERSION" "$VERSION" "$MAINTAINER" "$(date -R)" \
  | gzip -9n > "$DOC/changelog.Debian.gz"

# --- kurulum sonrası kancalar ----------------------------------------------
cat > "$STAGE/DEBIAN/postinst" <<'HOOK'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
fi
exit 0
HOOK
cat > "$STAGE/DEBIAN/postrm" <<'HOOK'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -qtf /usr/share/icons/hicolor || true
fi
exit 0
HOOK
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# --- izinler ----------------------------------------------------------------
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE/usr" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/liftoff"

# --- md5sums ----------------------------------------------------------------
( cd "$STAGE" && find usr -type f -print0 | sort -z \
    | xargs -0 md5sum > DEBIAN/md5sums )

# --- control ----------------------------------------------------------------
SIZE=$(du -ks "$STAGE/usr" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.9), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: pkexec
Installed-Size: $SIZE
Maintainer: $MAINTAINER
Homepage: https://github.com/M-SukruSezer/liftoff
Description: See and disable what starts automatically
 Liftoff shows the applications and services that start by themselves
 when you turn on your computer, and lets you turn off the ones you do
 not want. It brings together the three places these live on Linux:
 autostart entries, systemd user units and system-wide systemd units.
 .
 Turning a system entry off writes a personal override instead of
 touching the system file, so every change is reversible. Units that
 your session depends on are flagged before they can be disabled.
 .
 The interface is available in Turkish and English.
CTRL

# --- paketle ----------------------------------------------------------------
fakeroot dpkg-deb --root-owner-group --build "$STAGE" "$OUT" >/dev/null
echo "Üretildi: $OUT ($(du -h "$OUT" | cut -f1))"
