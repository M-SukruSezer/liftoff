#!/usr/bin/env bash
# Liftoff'u kaldırır. Yaptığınız başlangıç ayarlarına dokunmaz.
set -euo pipefail

APP_ID="io.github.m_sukrusezer.Liftoff"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"

rm -rf "$PREFIX/liftoff"
rm -f  "$HOME/.local/bin/liftoff"
rm -f  "$PREFIX/applications/$APP_ID.desktop"
rm -f  "$PREFIX/metainfo/$APP_ID.metainfo.xml"
rm -f  "$PREFIX/icons/hicolor/scalable/apps/$APP_ID.svg"
rm -f  "$PREFIX/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"

command -v update-desktop-database >/dev/null && \
  update-desktop-database "$PREFIX/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && \
  gtk-update-icon-cache -qtf "$PREFIX/icons/hicolor" 2>/dev/null || true

echo "Kaldırıldı."
echo "Not: Uygulamayla yaptığınız açma/kapatma ayarları olduğu gibi kaldı"
echo "     (~/.config/autostart ve systemd birim durumları)."
