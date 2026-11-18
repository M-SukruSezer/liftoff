# Liftoff — sistem geneli kurulum ve paketleme.
#
#   make install                 -> /usr/local altına kurar
#   sudo make install PREFIX=/usr
#   make install DESTDIR=/tmp/x  -> paketleme için sahte köke kurar
#   make deb                     -> dist/ altında .deb üretir
#   make check                   -> veri dosyalarını doğrular
#
# Kullanıcıya özel, root gerektirmeyen kurulum için ./install.sh kullanın.

# GNU make'in örtük kuralları kapatılır: depoda install.sh bulunduğu için
# ".sh -> çalıştırılabilir" kuralı "make install"i sessizce ele geçirebiliyor.
MAKEFLAGS += --no-builtin-rules
.SUFFIXES:

APP_ID  := io.github.m_sukrusezer.Liftoff
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' liftoff/__init__.py)

PREFIX  ?= /usr/local
DESTDIR ?=

BINDIR  := $(PREFIX)/bin
DATADIR := $(PREFIX)/share
PKGDIR  := $(DATADIR)/liftoff

INSTALL ?= install

.PHONY: all install uninstall check deb clean version

all:
	@echo "Liftoff $(VERSION) — 'make install' ya da 'make deb'"

version:
	@echo $(VERSION)

install:
	@test -n "$(VERSION)" || { echo "HATA: sürüm okunamadı" >&2; exit 1; }
	# Python paketi
	$(INSTALL) -d $(DESTDIR)$(PKGDIR)/liftoff
	$(INSTALL) -m 644 liftoff/*.py $(DESTDIR)$(PKGDIR)/liftoff/
	# Başlatıcı (PYTHONPATH kurulum yoluna göre yazılır)
	$(INSTALL) -d $(DESTDIR)$(BINDIR)
	sed 's|@PKGDIR@|$(PKGDIR)|g' build-aux/liftoff.in > $(DESTDIR)$(BINDIR)/liftoff
	chmod 755 $(DESTDIR)$(BINDIR)/liftoff
	# Menü girdisi, mağaza metaverisi ve simgeler
	$(INSTALL) -D -m 644 data/$(APP_ID).desktop \
	    $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	$(INSTALL) -D -m 644 data/$(APP_ID).metainfo.xml \
	    $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	$(INSTALL) -D -m 644 data/$(APP_ID).svg \
	    $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	$(INSTALL) -D -m 644 data/$(APP_ID)-symbolic.svg \
	    $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	@echo "Kuruldu: $(DESTDIR)$(PREFIX) (sürüm $(VERSION))"

uninstall:
	rm -rf $(DESTDIR)$(PKGDIR)
	rm -f  $(DESTDIR)$(BINDIR)/liftoff
	rm -f  $(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop
	rm -f  $(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml
	rm -f  $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg
	rm -f  $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
	@echo "Kaldırıldı: $(DESTDIR)$(PREFIX)"

check:
	@desktop-file-validate data/$(APP_ID).desktop && echo "desktop girdisi geçerli"
	@appstreamcli validate --no-net data/$(APP_ID).metainfo.xml >/dev/null \
	  && echo "metaveri geçerli"
	@python3 -c "import ast,glob,sys; [ast.parse(open(f).read()) for f in glob.glob('liftoff/*.py')]" \
	  && echo "python kaynakları ayrıştırılıyor"

deb:
	@build-aux/make-deb.sh "$(VERSION)"

clean:
	rm -rf dist build .flatpak-builder
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
