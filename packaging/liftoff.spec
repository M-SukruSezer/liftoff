Name:           liftoff
Version:        1.2.1
Release:        1%{?dist}
Summary:        See and disable the applications and services that start automatically

License:        MIT
URL:            https://github.com/M-SukruSezer/liftoff
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  make
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Recommends:     polkit

%description
Liftoff shows the applications and services that start by themselves when
you turn on your computer, and lets you turn off the ones you do not want.
It brings together the three places these live on Linux: autostart entries,
systemd user units and system-wide systemd units.

Turning a system entry off writes a personal override instead of touching
the system file, so every change is reversible. Units that your session
depends on are flagged before they can be disabled.

The interface is available in Turkish and English.

%prep
%autosetup

%build
# Saf Python; derleme adımı yok.

%install
%make_install PREFIX=%{_prefix}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.m_sukrusezer.Liftoff.desktop
appstream-util validate-relax --nonet \
    %{buildroot}%{_datadir}/metainfo/io.github.m_sukrusezer.Liftoff.metainfo.xml

%files
%license LICENSE
%doc README.md README.tr.md
%{_bindir}/liftoff
%{_datadir}/liftoff/
%{_datadir}/applications/io.github.m_sukrusezer.Liftoff.desktop
%{_datadir}/metainfo/io.github.m_sukrusezer.Liftoff.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.m_sukrusezer.Liftoff.svg
%{_datadir}/icons/hicolor/symbolic/apps/io.github.m_sukrusezer.Liftoff-symbolic.svg

%changelog
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.2.1-1
- New application icon, with a matching symbolic icon
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.2.0-1
- Group the list into what starts at login and what does not
- Move the per-row menu into the details dialog
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.1.0-1
- Keep Flatpak apps off by also withdrawing their background permission
- Show the icon of each application and service
- Edit startup entries and add them from the installed applications
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.0.3-1
- Rewrite the documentation and publish installable packages
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.0.2-1
- Add native packaging: Makefile, Debian package, AUR and RPM definitions
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.0.1-1
- Fix the Flatpak install path so the package builds from the tag
* Wed Nov 18 2026 Muhammed Şükrü SEZER <61243521+M-SukruSezer@users.noreply.github.com> - 1.0.0-1
- First release
