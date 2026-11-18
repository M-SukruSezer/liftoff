"""Çeviri katmanı.

Kaynak metinler İngilizcedir; katalog İngilizce metni Türkçeye eşler.
``_()`` çağrı anındaki dili kullandığı için dil değişince arayüz
yeniden çizilerek anında güncellenebilir.
"""

from __future__ import annotations

import os

LANGUAGES: dict[str, str] = {
    "en": "English",
    "tr": "Türkçe",
}
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE

TR: dict[str, str] = {
    # --- kaynak adları -------------------------------------------------
    "Applications": "Uygulamalar",
    "User services": "Kullanıcı servisleri",
    "System services": "Sistem servisleri",
    # --- kapsam --------------------------------------------------------
    "Only this user": "Yalnızca bu kullanıcı",
    "System-wide": "Sistem geneli",
    "System entry + your setting": "Sistem girdisi + kullanıcı ayarı",
    # --- autostart notları ---------------------------------------------
    "Does not run in this desktop environment (only: %s)":
        "Bu masaüstü ortamında çalışmıyor (yalnızca: %s)",
    "Does not run in this desktop environment (excluded)":
        "Bu masaüstü ortamında çalışmıyor (hariç tutulmuş)",
    "Executable not found (TryExec)":
        "Çalıştırılabilir dosya bulunamadı (TryExec)",
    "System entry, overridden by your setting":
        "Sistem girdisi, kullanıcı ayarınızla geçersiz kılınmış",
    "System-wide entry (/etc/xdg)": "Sistem geneli girdi (/etc/xdg)",
    "Managed by the Flatpak background permission — turning it off here "
    "also withdraws that permission":
        "Flatpak arka plan izniyle yönetiliyor — buradan kapatmak bu izni "
        "de geri alır",
    "Session startup component (phase: %s)":
        "Oturum başlatma bileşeni (faz: %s)",
    # --- systemd notları -----------------------------------------------
    "Masked: completely blocked": "Maskelenmiş: tamamen engellenmiş durumda",
    "System service — changing it requires administrator rights":
        "Sistem servisi — değiştirmek için yönetici yetkisi gerekir",
    "Critical component: turning it off may break your session or system":
        "Kritik bileşen: kapatmak oturumu veya sistemi bozabilir",
    # --- hatalar --------------------------------------------------------
    "No path to save to": "Kaydedilecek yol belli değil",
    "Name cannot be empty": "İsim boş olamaz",
    "Command cannot be empty": "Komut boş olamaz",
    "A system entry cannot be deleted": "Sistem girdisi silinemez",
    "Command timed out: %s": "Komut zaman aşımına uğradı: %s",
    "Could not run command: %s (%s)": "Komut çalıştırılamadı: %s (%s)",
    "systemctl list-unit-files failed": "systemctl list-unit-files başarısız",
    "pkexec was not found. Administrator rights are required to change "
    "system services.":
        "pkexec bulunamadı. Sistem servislerini değiştirmek için yönetici "
        "yetkisi gerekiyor.",
    "Not authorized, nothing was changed.":
        "Yetki verilmedi, değişiklik yapılmadı.",
    "systemctl %s failed (code %d)": "systemctl %s başarısız (kod %d)",
    # --- satır ----------------------------------------------------------
    "Details": "Ayrıntılar",
    "Restore default": "Varsayılana dön",
    "Delete entry": "Girdiyi sil",
    "More actions": "Diğer işlemler",
    "This unit's state cannot be changed (%s)":
        "Bu birimin durumu değiştirilemez (%s)",
    "running now": "şu an çalışıyor",
    "not running now": "şu an çalışmıyor",
    # --- liste durumları --------------------------------------------------
    "Loading…": "Yükleniyor…",
    "No results": "Sonuç yok",
    "Could not load the list": "Liste alınamadı",
    "Showing %d entries · %d on · %d off":
        "%d girdi gösteriliyor · %d açık · %d kapalı",
    "Showing 1 entry · %d on · %d off":
        "1 girdi gösteriliyor · %d açık · %d kapalı",
    "%d hidden system components are not shown — show them":
        "%d gizli sistem bileşeni gizlendi — göster",
    "No matching entries": "Eşleşen girdi yok",
    "Nothing found for “%s”.": "“%s” aramasıyla bir şey bulunamadı.",
    "Nothing to show": "Gösterilecek girdi yok",
    "You can show hidden system components from the menu.":
        "Gizli sistem bileşenlerini görmek için menüden açabilirsiniz.",
    # --- onay pencereleri -------------------------------------------------
    "Turn off “%s”?": "“%s” kapatılsın mı?",
    "This may be a component your system or session needs. Turning it off "
    "can cause problems at startup.":
        "Bu, sistemin veya oturumun çalışması için önemli bir bileşen "
        "olabilir. Kapatmak açılışta sorun yaratabilir.",
    "You will be asked for your administrator password.":
        "Değişiklik için yönetici şifreniz istenecek.",
    "The change takes effect at the next startup.":
        "Değişiklik bir sonraki açılışta etkili olur.",
    "Stop the service now as well": "Servisi şimdi de durdur",
    "Cancel": "Vazgeç",
    "Turn off": "Kapat",
    "Restore default?": "Varsayılana dönülsün mü?",
    "Delete entry?": "Girdi silinsin mi?",
    "Your change to “%s” will be removed and the system default will come "
    "back.":
        "“%s” için yaptığınız değişiklik kaldırılacak ve sistem varsayılanı "
        "geri gelecek.",
    "The startup entry “%s” will be permanently deleted.":
        "“%s” başlangıç girdisi kalıcı olarak silinecek.",
    "Undo": "Geri al",
    "Delete": "Sil",
    # --- bildirimler -------------------------------------------------------
    "Could not change it: %s": "Değiştirilemedi: %s",
    "“%s” turned on": "“%s” açıldı",
    "“%s” turned off": "“%s” kapatıldı",
    "Could not delete it: %s": "Silinemedi: %s",
    "Restored to default": "Varsayılana dönüldü",
    "Entry deleted": "Girdi silindi",
    "Could not add it: %s": "Eklenemedi: %s",
    "“%s” added": "“%s” eklendi",
    # --- ayrıntılar penceresi ----------------------------------------------
    "Source": "Kaynak",
    "Identifier": "Kimlik",
    "State": "Durum",
    "On": "Açık",
    "Off": "Kapalı",
    "Unit state": "Birim durumu",
    "Right now": "Şu an",
    "running": "çalışıyor",
    "not running": "çalışmıyor",
    "Command": "Komut",
    "Unit file": "Birim dosyası",
    "User file": "Kullanıcı dosyası",
    "System file": "Sistem dosyası",
    "Scope": "Kapsam",
    "Notes": "Notlar",
    "Copy": "Kopyala",
    # --- ekleme penceresi ---------------------------------------------------
    "New startup entry": "Yeni başlangıç girdisi",
    "Display name": "Görünen ad",
    "Description (optional)": "Açıklama (isteğe bağlı)",
    "The entry is created in ~/.config/autostart and runs at your next "
    "login.":
        "Girdi ~/.config/autostart içinde oluşturulur ve bir sonraki oturum "
        "açılışında çalışır.",
    "Add": "Ekle",
    # --- ana pencere ---------------------------------------------------------
    "Search in name and command": "Ad veya komutta ara",
    "Add a new startup entry": "Yeni başlangıç girdisi ekle",
    "Search (Ctrl+F)": "Ara (Ctrl+F)",
    "Refresh (Ctrl+R)": "Yenile (Ctrl+R)",
    "Show hidden system components": "Gizli sistem bileşenlerini göster",
    "Only the enabled ones": "Yalnızca açık olanlar",
    "View": "Görünüm",
    "Language": "Dil",
    "Refresh": "Yenile",
    "About": "Hakkında",
    "Menu": "Menü",
    "Changes take effect at your next login.":
        "Değişiklikler bir sonraki oturum açılışında etkili olur.",
    # --- hakkında ------------------------------------------------------------
    "Shows the applications and services that start by themselves when you "
    "turn on your computer, and lets you turn them off.":
        "Bilgisayar açıldığında kendiliğinden başlayan uygulama ve servisleri "
        "gösterir, kapatmanızı sağlar.",
    "<p>The list is now split into what starts at login and what you have "
    "switched off.</p>"
    "<ul>"
    "<li>Each row carries a small state label</li>"
    "<li>Only genuine warnings are marked in the list</li>"
    "<li>Clicking a row opens the details, which now hold edit and delete</li>"
    "</ul>":
        "<p>Liste artık açılışta başlayanlar ile kapattıklarınız diye "
        "ayrılıyor.</p>"
        "<ul>"
        "<li>Her satır küçük bir durum etiketi taşıyor</li>"
        "<li>Listede yalnızca gerçek uyarılar işaretleniyor</li>"
        "<li>Satıra tıklamak düzenleme ve silmeyi de taşıyan ayrıntıları "
        "açıyor</li>"
        "</ul>",
    # --- liste grupları --------------------------------------------------
    "Starts at login": "Açılışta başlıyor",
    "Enabled": "Açık",
    "Off": "Kapalı",
    "turning one off applies at your next login":
        "kapatmak bir sonraki oturum açılışında geçerli olur",
    "changes apply at the next startup":
        "değişiklikler bir sonraki açılışta geçerli olur",
    "1 entry": "1 girdi",
    "%d entries": "%d girdi",
    "critical": "kritik",
    "running": "çalışıyor",
    # --- düzenleme ve ekleme ------------------------------------------------
    "Edit…": "Düzenle…",
    "Edit entry": "Girdiyi düzenle",
    "Entry": "Girdi",
    "Description": "Açıklama",
    "Icon": "Simge",
    "Change…": "Değiştir…",
    "Clear": "Temizle",
    "Not set": "Belirtilmemiş",
    "Run in a terminal": "Uçbirimde çalıştır",
    "Other keys": "Diğer anahtarlar",
    "Everything else in the .desktop file.":
        ".desktop dosyasındaki diğer her şey.",
    "Add a key": "Anahtar ekle",
    "Key name": "Anahtar adı",
    "For example Terminal, Path or Name[tr].":
        "Örneğin Terminal, Path ya da Name[tr].",
    "Remove this key": "Bu anahtarı kaldır",
    "Save": "Kaydet",
    "Could not open it: %s": "Açılamadı: %s",
    "Could not save it: %s": "Kaydedilemedi: %s",
    "“%s” saved": "“%s” kaydedildi",
    "This is a system entry": "Bu bir sistem girdisi",
    "Your changes are saved as a personal copy; the original file stays "
    "untouched.":
        "Değişiklikleriniz kişisel bir kopyaya yazılır; özgün dosyaya "
        "dokunulmaz.",
    # --- simge seçici --------------------------------------------------------
    "Choose an icon": "Simge seç",
    "Search icons": "Simgelerde ara",
    "No matching icons": "Eşleşen simge yok",
    "From a file…": "Dosyadan…",
    "Images": "Görseller",
    # --- uygulama seçici -----------------------------------------------------
    "From installed applications…": "Kurulu uygulamalardan…",
    "Enter a command…": "Komut gir…",
    "Choose an application": "Uygulama seç",
    "Search applications": "Uygulamalarda ara",
    "No matching applications": "Eşleşen uygulama yok",
    # --- kısayollar ----------------------------------------------------------
    "Keyboard Shortcuts": "Klavye Kısayolları",
    "General": "Genel",
    "Add a startup entry": "Başlangıç girdisi ekle",
    "Search": "Ara",
    "Close the window": "Pencereyi kapat",
    "Built with": "Kullanılan teknolojiler",
    "translator-credits": "Muhammed Şükrü SEZER",
}

CATALOG: dict[str, dict[str, str]] = {"tr": TR}


def available_languages() -> dict[str, str]:
    return dict(LANGUAGES)


def current_language() -> str:
    return _current


def set_language(code: str) -> str:
    """Etkin dili ayarlar. Bilinmeyen kod varsayılana düşer."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def detect_system_language() -> str:
    """Sistem dili Türkçe ise 'tr', diğer tüm durumlarda 'en'.

    gettext'in öncelik sırasını izler: LANGUAGE, LC_ALL, LC_MESSAGES, LANG.
    """
    raw = ""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (os.environ.get(var) or "").strip()
        if value and value.lower() not in ("c", "posix", "c.utf-8", "c.utf8"):
            raw = value
            break
    first = raw.split(":")[0].split(".")[0].split("@")[0]
    return "tr" if first.lower().startswith("tr") else DEFAULT_LANGUAGE


def gettext(text: str) -> str:
    """Etkin dile çevirir; karşılığı yoksa İngilizce kaynağı döndürür."""
    return CATALOG.get(_current, {}).get(text, text)


_ = gettext
