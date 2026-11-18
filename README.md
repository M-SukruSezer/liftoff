<p align="center">
  <img src="data/io.github.m_sukrusezer.Liftoff.svg" width="96" alt="Liftoff">
</p>

<h1 align="center">Liftoff</h1>

<p align="center">
  Linux'ta bilgisayar açıldığında <strong>kendiliğinden başlayan</strong> uygulama ve
  servisleri tek bir pencerede gösterir; istediklerinizi kapatmanızı sağlar.
</p>

GTK4 + libadwaita ile yazılmıştır, GNOME dışındaki masaüstlerinde de çalışır.

## Neleri gösterir

Linux'ta "açılışta çalışan şeyler" üç ayrı yere dağılmıştır; Liftoff üçünü tek
arayüzde toplar:

| Sekme | Kaynak | Yetki |
|---|---|---|
| **Uygulamalar** | `~/.config/autostart` ve `/etc/xdg/autostart` (`.desktop` girdileri) | Gerekmez |
| **Kullanıcı servisleri** | `systemctl --user` birimleri (service, socket, timer, path) | Gerekmez |
| **Sistem servisleri** | `systemctl` birimleri (sistem geneli) | `pkexec` ile yönetici |

Her satırda girdinin adı, açıklaması, çalıştırdığı komut, o anda çalışıp
çalışmadığı ve varsa uyarıları görünür. Sağdaki anahtarla açıp kapatırsınız.
Sekme başlıklarındaki rozetler o kaynakta kaç girdinin açık olduğunu gösterir.

## Kurulum

```bash
./install.sh
```

Root gerektirmez; her şeyi `~/.local` altına kurar ve uygulamalar menüsüne bir
girdi ekler. Kaldırmak için `./uninstall.sh`.

Kurmadan denemek isterseniz:

```bash
./liftoff.py
```

### Gereksinimler

Python 3.9+ ve GTK4/libadwaita Python bağlayıcıları:

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

# Fedora
sudo dnf install python3-gobject gtk4 libadwaita

# Arch
sudo pacman -S python-gobject gtk4 libadwaita
```

## Kullanım

- **Arama** — `Ctrl+F`, ad ve komut içinde arar.
- **Yenile** — `Ctrl+R`.
- **Gizli sistem bileşenlerini göster** — menüden. `NoDisplay=true` işaretli
  arka plan bileşenleri varsayılan olarak gizlidir (GNOME'un kendi
  "Başlangıç Uygulamaları" aracı da böyle davranır). Listenin üstündeki
  "*N* gizli sistem bileşeni gizlendi — göster" bağlantısı da aynı işi yapar.
- **Yalnızca açık olanlar** — menüden, yalnızca etkin girdileri listeler.
- **Yeni girdi ekle** — sol üstteki `+` düğmesi; ad ve komut yeter.
- **Ayrıntılar** — satır sonundaki `⋯` menüsü; dosya yolları, birim durumu
  gibi her alanı kopyalayabilirsiniz.
- **Dil** — menüdeki `Dil` / `Language` alt menüsünden Türkçe ile İngilizce
  arasında geçersiniz; değişiklik anında uygulanır.

## Dil

Arayüz Türkçe ve İngilizce destekler.

**İlk açılışta** hiçbir tercih kayıtlı değilken dil sistem diline göre
belirlenir: sistem dili Türkçe ise **Türkçe**, diğer her durumda
**İngilizce**. Sıralama `gettext` ile aynıdır — `LANGUAGE`, `LC_ALL`,
`LC_MESSAGES`, `LANG`.

Menüden başka bir dil seçtiğinizde tercih
`~/.config/liftoff/settings.json` içine yazılır ve bundan sonra sistem
dilinden bağımsız olarak hep o dil kullanılır. Dosyayı silerseniz uygulama
yeniden ilk açılış davranışına döner.

Çeviriler `liftoff/i18n.py` içinde düz bir sözlükte durur; kaynak metinler
İngilizcedir. Yeni bir dil eklemek için `LANGUAGES` sözlüğüne kodu ve adını,
`CATALOG` sözlüğüne de İngilizce metinleri o dile eşleyen bir sözlük eklemek
yeterlidir — ek bir araç ya da derleme adımı gerekmez.

## Flatpak ve Flathub

Depoda başvuru için gereken iki dosya hazır:

- `io.github.m_sukrusezer.Liftoff.yaml` — Flatpak manifesti
- `data/io.github.m_sukrusezer.Liftoff.metainfo.xml` — mağaza metaverisi
  (`appstreamcli validate` ile doğrulanmıştır)

Flathub'da yayınlanan her uygulama Bazaar'da da listelenir; Bazaar doğrudan
Flathub altyapısını kullanır, ayrı bir başvuru gerekmez.

### Yerel derleme

```bash
flatpak install flathub org.gnome.Platform//51 org.gnome.Sdk//51 org.flatpak.Builder
```

```bash
flatpak run org.flatpak.Builder --user --install --force-clean build io.github.m_sukrusezer.Liftoff.yaml
```

### Kumlamanın bu uygulamaya etkisi

Liftoff host sistemini yöneten bir araç, Flatpak ise uygulamayı host'tan
ayırmak için var. Bu gerilim ölçüldü — aynı kod, aynı makinede:

| | İzinsiz kumlama | Manifestteki izinlerle | Host (yerel kurulum) |
|---|---|---|---|
| Autostart girdisi | 2 | **18** | 18 |
| Kullanıcı servisi | çalışmıyor | **45** | 45 |
| Sistem servisi | çalışmıyor | **173** | 173 |

Üç izin bunun için gerekli:

- `--filesystem=xdg-config/autostart:create` — girdileri gerçek
  `~/.config/autostart` dizinine yazmak için. Flatpak `XDG_CONFIG_HOME`
  değişkenini uygulamanın özel dizinine çevirir; oturum yöneticisi orayı
  hiç okumaz, bu yüzden kod kumlama içinde o değişkeni yok sayar.
- `--filesystem=host-etc:ro` — `/etc/xdg/autostart` kumlamada görünmez,
  host'taki hâli `/run/host/etc` altından okunur.
- `--talk-name=org.freedesktop.Flatpak` — GNOME runtime'ı systemd
  içermez; `systemctl` ve `pkexec` `flatpak-spawn --host` ile host
  üzerinde çalıştırılır.

Bu mantığın tamamı `liftoff/host.py` içinde ve yalnızca kumlama içinde
devreye girer; yerel kurulumda davranış hiç değişmez.

### Flathub incelemesi — başvurmadan önce bilin

`--talk-name=org.freedesktop.Flatpak` host'ta herhangi bir komut
çalıştırmaya izin verir, yani kumlamayı pratikte kaldırır. Flathub bunu
geniş bir izin sayar, gerekçe ister ve çoğu başvuruda kaldırılmasını
önerir. Liftoff'ta kaldırmak mümkün değil: servis sekmelerinin ikisi de
tamamen host'a bağlı. Bu yüzden başvurunun tartışmaya açılması ya da
reddedilmesi gerçek bir olasılıktır — manifest teknik olarak doğru olsa da.

Gerçekçi seçenekler:

1. **Flathub'a başvurmak** — izinleri yukarıdaki gerekçelerle açıklayın.
2. **Yerel paket olarak dağıtmak** — `install.sh` zaten bunu yapıyor;
   AUR, `.deb` veya `.rpm` bu tür sistem araçları için alışılmış yol ve
   hiçbir izin kısıtı yok.

### Başvurudan önce yapılması gerekenler

Tamamlananlar:

- ✅ **Uygulama kimliği** `io.github.m_sukrusezer.Liftoff` — Flathub
  kimliğin sizin denetiminizdeki bir adrese karşılık gelmesini ister.
- ✅ **Ekran görüntüleri** `data/screenshots/` içinde ve metainfo'daki
  adresler herkese açık depodan erişilebilir durumda.

- ✅ **Sürüm etiketi** `v1.0.1` ve manifestteki kaynak `type: git` +
  `tag` + `commit` — Flathub yerel dizinden derlemeyi kabul etmez.

Kalan tek adım:

1. [flathub/flathub](https://github.com/flathub/flathub) deposuna
   `io.github.m_sukrusezer.Liftoff.yaml` dosyasını içeren bir Pull
   Request açın. İncelemede en çok sorulacak nokta
   `--talk-name=org.freedesktop.Flatpak` izni olacak; gerekçesi ve
   ölçümleri yukarıdaki **Kumlamanın bu uygulamaya etkisi** bölümünde.

### Yeni sürüm çıkarırken

`liftoff/__init__.py` içindeki `__version__`, metaverideki `<release>`
girdisi, etiket ve manifestteki `tag`/`commit` birlikte güncellenmeli.
Etiketi attıktan sonra manifestteki `commit` değerini etiketin işaret
ettiği commit'e ayarlayın — imzalı etiket nesnesinin SHA'sına değil.

> Kimliği ileride yeniden değiştirmek gerekirse
> `./build-aux/rename-app-id.sh <yeni-kimlik> <kullanıcı>/<depo>` tek
> komutla dosya adlarını, `APP_ID` değerini, menü girdisini, metaveriyi,
> manifesti ve kurulum betiklerini birlikte günceller.

## Değişiklikler nereye yazılır

Hiçbir şey kalıcı olarak bozulmaz; her işlem geri alınabilir.

**Uygulama girdileri.** Kullanıcıya ait bir girdiyi kapatırken dosyaya
`Hidden=true` ve `X-GNOME-Autostart-enabled=false` yazılır — dosyanın geri
kalanı, yorumları dahil, olduğu gibi korunur.

Bir **sistem girdisini** (`/etc/xdg/autostart`) kapattığınızda sistem dosyasına
dokunulmaz: dosya `~/.config/autostart` içine kopyalanır, kapatma anahtarları
bu kopyaya eklenir ve kopya `X-Liftoff-Override=true` ile işaretlenir. Girdiyi
tekrar açtığınızda bu kopya silinir, yani sistem varsayılanına tam olarak
dönülür. `⋯ → Varsayılana dön` aynı işi doğrudan yapar.

**Servisler.** `systemctl enable` / `disable` çağrılır; sistem servisleri için
`pkexec` üzerinden. Maskelenmiş bir birimi açarken önce `unmask` uygulanır.
Onay penceresindeki "Servisi şimdi de durdur" kutusu işaretlenmezse servis
çalışmaya devam eder ve değişiklik bir sonraki açılışta etkili olur.

## Güvenlik önlemleri

- Oturumu veya sistemi bozabilecek birimler (`systemd-*`, `gdm`, `dbus`,
  `polkit`, `pipewire`, `NetworkManager`, `apparmor` ve benzerleri) **kritik**
  olarak işaretlenir; kapatmadan önce uyarı penceresi çıkar.
- `static`, `generated` ve `indirect` durumdaki birimler listelenmez —
  bunlar zaten tek tek açılıp kapatılamaz.
- Durumu değiştirilemeyen birimlerin anahtarı pasif görünür, nedeni ipucunda
  yazar.
- Hiçbir işlem sessizce başarısız olmaz: hata ya da yetki reddi durumunda
  anahtar eski konumuna döner ve alt kısımda bildirim çıkar.

## Yapı

```
liftoff.py                 # kaynak ağacından çalıştırmak için başlatıcı
io.github.m_sukrusezer.Liftoff.yaml   # Flatpak manifesti
build-aux/
  liftoff-launcher               # Flatpak içindeki başlatıcı
  rename-app-id.sh               # uygulama kimliğini toptan değiştirir
liftoff/
  __main__.py              # python3 -m liftoff
  host.py                  # Flatpak kumlamasında host erişimi
  i18n.py                  # Türkçe/İngilizce çeviri kataloğu
  settings.py              # ~/.config/liftoff/settings.json (dil tercihi)
  desktop.py               # .desktop ayrıştırıcı/yazıcı (yorumları korur)
  xdg_autostart.py         # autostart girdileri: listele / aç / kapat / ekle / sil
  systemd.py               # systemd kullanıcı ve sistem birimleri
  models.py                # arayüzün gördüğü ortak veri modeli
  ui.py                    # GTK4 / libadwaita arayüzü
data/
  io.github.m_sukrusezer.Liftoff.desktop   # menü girdisi
  io.github.m_sukrusezer.Liftoff.svg       # uygulama simgesi
  io.github.m_sukrusezer.Liftoff-symbolic.svg
  io.github.m_sukrusezer.Liftoff.metainfo.xml  # mağaza metaverisi
  screenshots/                        # mağaza ekran görüntüleri
install.sh / uninstall.sh
```

Arka uçların tamamı ayrı iş parçacığında çalışır; `pkexec` şifre beklerken
bile pencere donmaz.

## Lisans

MIT
