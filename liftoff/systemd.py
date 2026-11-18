"""systemd birimlerini (kullanıcı ve sistem) listeleyen/açıp kapatan arka uç.

Kullanıcı birimleri doğrudan ``systemctl --user`` ile yönetilir.
Sistem birimleri root gerektirir; ``pkexec`` üzerinden çalıştırılır.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from . import host
from .i18n import gettext as _
from .models import Item, Note, Scope, Source

# Başlangıçta kendiliğinden devreye giren birim tipleri.
UNIT_TYPES = ("service", "socket", "timer", "path")

# Devre dışı bırakılması oturumu/sistemi bozabilecek birimler.
CRITICAL_PREFIXES = (
    "systemd-",
    "dbus",
    "polkit",
    "gdm",
    "lightdm",
    "sddm",
    "display-manager",
    "apparmor",
    "networkmanager",
    "network-manager",
    "wpa_supplicant",
    "ssh",
    "sshd",
    "user@",
    "user-",
    "getty",
    "rc-local",
    "plymouth",
    "udisks",
    "accounts-daemon",
    "pipewire",
    "wireplumber",
    "gnome-keyring",
    "gcr-ssh-agent",
    "xdg-desktop-portal",
    "cryptsetup",
    "lvm2",
    "mdmonitor",
    "multipathd",
)

# Açık/kapalı anahtarıyla oynanamayacak durumlar.
FIXED_STATES = {"static", "generated", "transient", "alias", "indirect", "bad"}

TIMEOUT = 25


class SystemdError(RuntimeError):
    pass


def _base_cmd(user: bool) -> list[str]:
    return ["systemctl", "--user"] if user else ["systemctl"]


def available(user: bool) -> bool:
    if host.which("systemctl") is None:
        return False
    try:
        proc = subprocess.run(
            host.command(_base_cmd(user) + ["is-system-running"]),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # "degraded", "starting" vb. de geçerli; yalnızca tamamen erişilemezse hata.
    return bool(proc.stdout.strip()) or proc.returncode in (0, 1)


def _is_critical(unit: str) -> bool:
    low = unit.casefold()
    return any(low.startswith(p) for p in CRITICAL_PREFIXES)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Komutu çalıştırır; Flatpak içindeysek host üzerinde."""
    try:
        return subprocess.run(host.command(cmd), capture_output=True,
                              text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise SystemdError(_("Command timed out: %s") % " ".join(cmd)) from exc
    except OSError as exc:
        raise SystemdError(_("Could not run command: %s (%s)")
                          % (" ".join(cmd), exc)) from exc


def _list_unit_files(user: bool) -> dict[str, str]:
    """{birim adı: unit file state} döndürür."""
    type_arg = "--type=" + ",".join(UNIT_TYPES)
    cmd = _base_cmd(user) + [
        "list-unit-files",
        type_arg,
        "--all",
        "--no-pager",
        "--no-legend",
        "--plain",
        "--output=json",
    ]
    proc = _run(cmd)
    out: dict[str, str] = {}
    if proc.returncode == 0 and proc.stdout.strip().startswith("["):
        try:
            for row in json.loads(proc.stdout):
                name = row.get("unit_file") or row.get("unit_file_name") or ""
                state = row.get("state") or ""
                if name:
                    out[name.split("/")[-1]] = state
            return out
        except (json.JSONDecodeError, AttributeError):
            pass

    # JSON desteklenmiyorsa düz metne düş.
    cmd = [c for c in cmd if c != "--output=json"]
    proc = _run(cmd)
    if proc.returncode != 0 and not proc.stdout.strip():
        raise SystemdError(proc.stderr.strip()
                           or _("systemctl list-unit-files failed"))
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and "." in parts[0]:
            out[parts[0].split("/")[-1]] = parts[1]
    return out


def _exec_start_path(value: str) -> str:
    """``{ path=/usr/bin/foo ; argv[]=... }`` içinden program yolunu alır."""
    marker = "path="
    start = value.find(marker)
    if start == -1:
        return ""
    rest = value[start + len(marker):].lstrip()
    for stop in (" ;", " ", "}"):
        end = rest.find(stop)
        if end != -1:
            rest = rest[:end]
    return rest.strip()


def is_template(unit: str) -> bool:
    """``foo@.service`` gibi örneği olmayan şablon birim mi?

    Bunlar tek başlarına açılıp kapatılamaz ve ``systemctl show`` bunlara
    rastlayınca hata verip yığının geri kalanını hiç yazdırmaz.
    """
    name, _, _suffix = unit.rpartition(".")
    return name.endswith("@")


def _show_batch(user: bool, units: list[str], info: dict[str, dict[str, str]]) -> None:
    """Tek bir ``systemctl show`` çağrısının sonucunu ``info``ya ekler."""
    cmd = _base_cmd(user) + [
        "show",
        "--property=Id",
        "--property=Description",
        "--property=ActiveState",
        "--property=UnitFileState",
        "--property=FragmentPath",
        "--property=ExecStart",
        *units,
    ]
    proc = _run(cmd)
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current.get("Id"):
                info[current["Id"]] = current
            current = {}
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            current[key] = value
    if current.get("Id"):
        info[current["Id"]] = current


def _show_properties(user: bool, units: list[str]) -> dict[str, dict[str, str]]:
    """Birimler için Description / ActiveState / UnitFileState bilgisi.

    ``systemctl show`` geçersiz bir birim adına rastlarsa yığının tamamını
    iptal eder. Bu yüzden önce şablon birimleri ayıklıyor, sonra eksik
    kalanları giderek küçülen yığınlarla yeniden deniyoruz: tek bir bozuk
    ad yalnızca kendisini kaybettiriyor, komşularını değil.
    """
    info: dict[str, dict[str, str]] = {}
    pending = [u for u in units if not is_template(u)]
    if not pending:
        return info

    for chunk_size in (120, 20, 1):
        for start in range(0, len(pending), chunk_size):
            _show_batch(user, pending[start:start + chunk_size], info)
        pending = [u for u in pending if u not in info]
        if not pending:
            break
        # Tek tek denemeyi makul bir sayıyla sınırla.
        if chunk_size == 20 and len(pending) > 60:
            break
    return info


# Kullanıcının açıp kapatabileceği, başlangıçta devreye girebilen durumlar.
TOGGLEABLE_STATES = {
    "enabled", "enabled-runtime", "disabled", "masked", "masked-runtime",
}
# Bunlar bir hedefe bağlı değildir ya da tek tek yönetilemez; listeyi şişirir.
SKIPPED_STATES = {"static", "generated", "indirect", "alias", "transient", "bad"}


def list_items(user: bool) -> list[Item]:
    states = _list_unit_files(user)
    if not states:
        return []

    # Yalnızca gerçekten göstereceğimiz birimler için özellik sorgula:
    # tüm birimleri sormak hem yavaş hem de geçersiz adlara çarpma riski.
    wanted = {
        unit: state
        for unit, state in states.items()
        if not is_template(unit) and state in TOGGLEABLE_STATES
    }
    if not wanted:
        return []
    info = _show_properties(user, sorted(wanted))

    source = Source.USER_UNIT if user else Source.SYSTEM_UNIT
    items: list[Item] = []
    for unit, state in sorted(wanted.items()):
        props = info.get(unit, {})
        state = (props.get("UnitFileState") or state or "").strip()
        if state in SKIPPED_STATES:
            continue

        enabled = state.startswith("enabled")
        masked = state.startswith("masked")
        active = (props.get("ActiveState") or "").strip()
        description = (props.get("Description") or "").strip()
        if description == unit:
            description = ""

        notes: list[Note] = []
        if masked:
            notes.append(Note("Masked: completely blocked"))
        if not user:
            notes.append(
                Note("System service — changing it requires administrator rights")
            )
        if _is_critical(unit):
            notes.append(Note(
                "Critical component: turning it off may break your session "
                "or system", warn=True))
        frag = (props.get("FragmentPath") or "").strip()
        exec_path = _exec_start_path(props.get("ExecStart") or "")

        items.append(
            Item(
                key=unit,
                source=source,
                name=unit,
                enabled=enabled,
                description=description,
                command=frag,
                exec_path=exec_path,
                scope=Scope.USER if user else Scope.SYSTEM,
                toggleable=state not in FIXED_STATES,
                needs_root=not user,
                hidden_entry=False,
                running=active == "active" if active else None,
                notes=notes,
                unit_state=state,
                system_path=frag or None,
                critical=_is_critical(unit),
            )
        )
    return sorted(items, key=lambda i: (i.name.casefold(), i.key))


def set_enabled(item: Item, enabled: bool, stop_now: bool = False) -> str:
    """Birimi etkinleştirir/devre dışı bırakır. Çıktı mesajını döndürür."""
    user = item.source is Source.USER_UNIT
    action = "enable" if enabled else "disable"

    outputs: list[str] = []
    if item.unit_state.startswith("masked") and enabled:
        outputs.append(_exec(user, ["unmask", item.key]))
    outputs.append(_exec(user, [action, item.key]))
    if stop_now and not enabled:
        outputs.append(_exec(user, ["stop", item.key]))
    elif stop_now and enabled:
        outputs.append(_exec(user, ["start", item.key]))
    return "\n".join(o for o in outputs if o)


def _exec(user: bool, args: list[str]) -> str:
    if user:
        cmd = ["systemctl", "--user", *args]
    else:
        if host.which("pkexec") is None:
            raise SystemdError(_(
                "pkexec was not found. Administrator rights are required to "
                "change system services."
            ))
        cmd = ["pkexec", "systemctl", *args]
    proc = _run(cmd)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if proc.returncode == 126 or "not authorized" in stderr.casefold():
            raise SystemdError(_("Not authorized, nothing was changed."))
        raise SystemdError(stderr or _("systemctl %s failed (code %d)")
                           % (" ".join(args), proc.returncode))
    return (proc.stdout + proc.stderr).strip()
