#!/usr/bin/env bash
# Uygulama kimliğini ve depo adresini tek seferde değiştirir.
#
#   ./build-aux/rename-app-id.sh io.github.ahmet.Liftoff ahmet/liftoff
#
# İlk argüman yeni uygulama kimliği (ters alan adı biçiminde).
# İkinci argüman isteğe bağlı: GitHub <kullanıcı>/<depo>, metainfo
# içindeki adresler ve ekran görüntüsü bağlantıları için.
set -euo pipefail

# Karakter aralıkları (A-Z, a-z) yerel ayarın harmanlama sırasına göre
# yorumlanır; Türkçe yerelde 'i' harfi bu aralıkların dışında kalabiliyor
# ve geçerli kimlikler reddediliyordu. Metin işlemenin tamamını C yerelinde
# yapıyoruz.
export LC_ALL=C

OLD_ID="io.github.m_sukrusezer.Liftoff"
OLD_REPO="M-SukruSezer/liftoff"

if [ $# -lt 1 ]; then
  echo "Kullanım: $0 <yeni-uygulama-kimliği> [<github-kullanıcı>/<depo>]" >&2
  exit 1
fi
NEW_ID="$1"
NEW_REPO="${2:-}"

# Doğrulamayı Bash'in kendi regex operatörüyle yap: harici grep
# uygulamaları (GNU grep / ugrep) arasında davranış farkı olabiliyor.
# En az üç parça, ör. io.github.kullanici.Liftoff
ID_RE='^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_-]*){2,}$'
if [[ ! "$NEW_ID" =~ $ID_RE ]]; then
  echo "HATA: '$NEW_ID' geçerli bir uygulama kimliği değil." >&2
  echo "      En az üç parça olmalı, ör. io.github.kullanici.Liftoff" >&2
  exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ "$NEW_ID" = "$OLD_ID" ]; then
  echo "Kimlik zaten $NEW_ID"
else
  # 1) Kimliği taşıyan dosyaları yeniden adlandır
  for f in data/"$OLD_ID"*.svg data/"$OLD_ID".desktop data/"$OLD_ID".metainfo.xml; do
    [ -e "$f" ] || continue
    mv "$f" "${f/$OLD_ID/$NEW_ID}"
  done
  [ -e "$OLD_ID.yaml" ] && mv "$OLD_ID.yaml" "$NEW_ID.yaml"

  # 2) İçerikleri güncelle
  grep -rl --binary-files=without-match "$OLD_ID" . \
    --exclude-dir=.git --exclude-dir=build --exclude-dir=.flatpak-builder \
    | while read -r f; do
        sed -i "s|$OLD_ID|$NEW_ID|g" "$f"
      done
  echo "Uygulama kimliği: $OLD_ID -> $NEW_ID"
fi

if [ -n "$NEW_REPO" ]; then
  grep -rl --binary-files=without-match "$OLD_REPO" . \
    --exclude-dir=.git --exclude-dir=build --exclude-dir=.flatpak-builder \
    | while read -r f; do
        sed -i "s|$OLD_REPO|$NEW_REPO|g" "$f"
      done
  echo "Depo adresi    : $OLD_REPO -> $NEW_REPO"
fi

echo
echo "Kontrol:"
command -v appstreamcli >/dev/null && \
  appstreamcli validate --no-net "data/$NEW_ID.metainfo.xml" >/dev/null 2>&1 \
  && echo "  metainfo geçerli" || echo "  metainfo DOĞRULANAMADI"
command -v desktop-file-validate >/dev/null && \
  desktop-file-validate "data/$NEW_ID.desktop" && echo "  desktop girdisi geçerli"
echo
echo "Sonraki adım: ./install.sh ile yeniden kurun."
