#!/usr/bin/env bash
# Liftoff'u geçerli kullanıcı için kurar (root gerekmez).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.m_sukrusezer.Liftoff"

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
LIBDIR="$PREFIX/liftoff"
BINDIR="$HOME/.local/bin"
APPDIR="$PREFIX/applications"
METADIR="$PREFIX/metainfo"
ICONDIR="$PREFIX/icons/hicolor/scalable/apps"
SYMDIR="$PREFIX/icons/hicolor/symbolic/apps"

echo "Kaynak : $SRC"
echo "Hedef  : $LIBDIR"
echo

# --- bağımlılık kontrolü -----------------------------------------------------
if ! python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' 2>/dev/null
then
  echo "HATA: GTK4 ve libadwaita Python bağlayıcıları bulunamadı." >&2
  echo "Debian/Ubuntu:  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" >&2
  echo "Fedora:         sudo dnf install python3-gobject gtk4 libadwaita" >&2
  echo "Arch:           sudo pacman -S python-gobject gtk4 libadwaita" >&2
  exit 1
fi

# --- uygulama paketi ---------------------------------------------------------
mkdir -p "$LIBDIR" "$BINDIR" "$APPDIR" "$METADIR" "$ICONDIR" "$SYMDIR"
rm -rf "$LIBDIR/liftoff"
cp -r "$SRC/liftoff" "$LIBDIR/liftoff"
find "$LIBDIR/liftoff" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# --- başlatıcı ---------------------------------------------------------------
cat > "$BINDIR/liftoff" <<WRAPPER
#!/bin/sh
# Liftoff başlatıcı — install.sh tarafından oluşturuldu.
PYTHONPATH="$LIBDIR\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m liftoff "\$@"
WRAPPER
chmod 755 "$BINDIR/liftoff"

# --- menü girdisi ve simge ---------------------------------------------------
install -m 644 "$SRC/data/$APP_ID.desktop" "$APPDIR/$APP_ID.desktop"
install -m 644 "$SRC/data/$APP_ID.metainfo.xml" "$METADIR/$APP_ID.metainfo.xml"
install -m 644 "$SRC/data/$APP_ID.svg" "$ICONDIR/$APP_ID.svg"
install -m 644 "$SRC/data/$APP_ID-symbolic.svg" "$SYMDIR/$APP_ID-symbolic.svg"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPDIR" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && \
  gtk-update-icon-cache -qtf "$PREFIX/icons/hicolor" 2>/dev/null || true

echo "Kurulum tamamlandı."
echo
echo "  Çalıştırmak için:  liftoff"
echo "  veya uygulamalar menüsünde “Liftoff”"
echo
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo "NOT: $BINDIR PATH içinde değil. Şu satırı ~/.bashrc dosyanıza ekleyin:"
     echo "     export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
