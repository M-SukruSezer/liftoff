"""GTK4 / libadwaita arayüzü."""

from __future__ import annotations

import platform
import re
import threading
import traceback
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

gi.require_version("Pango", "1.0")

from gi.repository import (  # noqa: E402
    Adw, Gdk, Gio, GLib, GObject, Gtk, Pango,
)

from . import (  # noqa: E402
    APP_DEVELOPER,
    APP_DEVELOPER_HANDLE,
    APP_ID,
    APP_NAME,
    COPYRIGHT_YEAR,
    ISSUE_URL,
    PROJECT_URL,
    __version__,
    i18n,
    settings,
)
from . import apps, icons, systemd, xdg_autostart  # noqa: E402
from .i18n import gettext as _  # noqa: E402
from .models import Item, Source  # noqa: E402


# .desktop anahtar adı: Ad, Ad[tr], X-Ozel-Anahtar...
KEY_NAME_RE = re.compile(r"^[A-Za-z0-9-]+(\[[A-Za-z0-9_@.-]+\])?$")


def apply_icon(image: Gtk.Image, candidates, fallback: str) -> None:
    """İlk bulunabilen simgeyi görsele yerleştirir, yoksa genel görseli."""
    display = Gdk.Display.get_default()
    theme = Gtk.IconTheme.get_for_display(display) if display else None
    for name in candidates:
        if not name:
            continue
        if name.startswith("/"):
            if Path(name).exists():
                image.set_from_file(name)
                return
            continue
        if theme is not None and theme.has_icon(name):
            image.set_from_icon_name(name)
            return
    image.set_from_icon_name(fallback)


def run_in_thread(work, on_done):
    """``work()`` fonksiyonunu ayrı iş parçacığında çalıştırır.

    Sonuç ana döngüde ``on_done(result, error)`` olarak teslim edilir.
    """

    def target():
        try:
            result = work()
            error = None
        except Exception as exc:  # noqa: BLE001 - arayüze taşıyoruz
            result = None
            error = exc
            traceback.print_exc()
        GLib.idle_add(on_done, result, error, priority=GLib.PRIORITY_DEFAULT)

    threading.Thread(target=target, daemon=True).start()


class ItemRow(Adw.ActionRow):
    """Tek bir başlangıç girdisini gösteren satır."""

    def __init__(self, item: Item, page: "ItemsPage"):
        super().__init__()
        self.item = item
        self.page = page

        self.set_title(GLib.markup_escape_text(item.name))
        self.set_title_lines(2)
        subtitle = self._subtitle()
        if subtitle:
            self.set_subtitle(GLib.markup_escape_text(subtitle))
            self.set_subtitle_lines(2)

        self.add_prefix(self._build_icon())

        pill = self._state_pill()
        if pill is not None:
            self.add_suffix(pill)

        warn = self._warning_icon()
        if warn is not None:
            self.add_suffix(warn)

        self.switch = Gtk.Switch(
            active=item.enabled,
            valign=Gtk.Align.CENTER,
            sensitive=item.toggleable,
        )
        if not item.toggleable:
            self.switch.set_tooltip_text(
                _("This unit's state cannot be changed (%s)") % item.unit_state
            )
        self._handler = self.switch.connect("notify::active", self._on_toggled)
        self.add_suffix(self.switch)

        # Satıra tıklamak anahtarı değil ayrıntıları açar: anahtar küçük bir
        # hedef, ayrıntılar ise her eylemin (düzenle, sil) bulunduğu yer.
        self.set_activatable(True)
        self.connect("activated", self._on_activated)

    # ------------------------------------------------------------- görünüm

    def _subtitle(self) -> str:
        parts: list[str] = []
        if self.item.description:
            parts.append(self.item.description)
        if self.item.source is Source.AUTOSTART and self.item.command:
            parts.append(self.item.command)
        return " · ".join(parts)

    def _state_pill(self) -> Gtk.Widget | None:
        """Satırın sağındaki küçük durum etiketi."""
        if self.item.critical:
            text, css = _("critical"), "warning"
        elif self.item.running is True:
            text, css = _("running"), "dim-label"
        elif not self.item.toggleable:
            text, css = self.item.unit_state, "dim-label"
        else:
            return None
        label = Gtk.Label(label=text, valign=Gtk.Align.CENTER)
        label.add_css_class("caption")
        label.add_css_class(css)
        if self.item.notes:
            label.set_tooltip_text(self._notes_text())
        return label

    def _notes_text(self) -> str:
        return "\n".join("• " + n.render() for n in self.item.notes)

    def _build_icon(self) -> Gtk.Widget:
        """Uygulamanın/servisin kendi logosu varsa onu, yoksa genel görseli."""
        image = Gtk.Image(pixel_size=36, valign=Gtk.Align.CENTER)
        apply_icon(image, icons.candidates(self.item), icons.fallback(self.item))
        if self.item.hidden_entry:
            image.add_css_class("dim-label")
        return image

    def _warning_icon(self) -> Gtk.Widget | None:
        """Yalnızca uyarı niteliğindeki notlar satırda işaretlenir.

        Bilgi niteliğindeki notlar listeyi kalabalıklaştırmasın diye
        ayrıntılar penceresinde kalır; kritik girdilerde zaten rozet var.
        """
        if self.item.critical or not any(n.warn for n in self.item.notes):
            return None
        icon = Gtk.Image(icon_name="dialog-warning-symbolic",
                         valign=Gtk.Align.CENTER)
        icon.set_tooltip_text(self._notes_text())
        icon.add_css_class("warning")
        return icon

    def _on_activated(self, *_args) -> None:
        self.activate_action("row.details", GLib.Variant.new_string(self.item.key))

    # ------------------------------------------------------------- eylemler

    def set_active_silently(self, active: bool) -> None:
        self.switch.handler_block(self._handler)
        self.switch.set_active(active)
        self.switch.handler_unblock(self._handler)

    def _on_toggled(self, switch: Gtk.Switch, _param) -> None:
        self.page.request_toggle(self, switch.get_active())


class ItemsPage(Gtk.Box):
    """Bir kaynağa ait girdi listesi."""

    def __init__(self, window: "MainWindow", source: Source):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.source = source
        self.items: list[Item] = []
        self.error: Exception | None = None
        self.loaded = False

        self.spinner_page = Adw.StatusPage(
            title=_("Loading…"),
            child=Adw.Spinner(width_request=48, height_request=48),
            vexpand=True,
        )
        self.empty_page = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title=_("No results"),
            vexpand=True,
        )

        # Girdiler iki gruba ayrılır: açılışta başlayanlar ve kapatılanlar.
        self.on_group = Adw.PreferencesGroup()
        self.off_group = Adw.PreferencesGroup()
        # (eklendiği grup, satır): girdinin durumu değişse de doğru gruptan
        # kaldırabilmek için satırın nereye konduğunu saklıyoruz.
        self._rows: list[tuple[Adw.PreferencesGroup, "ItemRow"]] = []

        # Gizlenmiş sistem bileşenleri varsa kullanıcıya tek tıkla göster.
        self.hint = Gtk.Button(has_frame=False, valign=Gtk.Align.CENTER, visible=False)
        self.hint.add_css_class("flat")
        self.hint.connect("clicked", self._on_hint_clicked)
        hint_label = Gtk.Label()
        hint_label.add_css_class("caption")
        hint_label.add_css_class("accent")
        self.hint.set_child(hint_label)
        self._hint_label = hint_label

        hint_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                           halign=Gtk.Align.START)
        hint_box.append(self.hint)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.append(hint_box)
        content.append(self.on_group)
        content.append(self.off_group)

        clamp = Adw.Clamp(maximum_size=760, child=content, margin_top=12,
                          margin_bottom=24, margin_start=12, margin_end=12)
        self.scroller = Gtk.ScrolledWindow(
            child=clamp, vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )

        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(self.spinner_page, "loading")
        self.stack.add_named(self.scroller, "list")
        self.stack.add_named(self.empty_page, "empty")
        self.append(self.stack)

        self._install_actions()

    def _install_actions(self) -> None:
        group = Gio.SimpleActionGroup()

        details = Gio.SimpleAction.new("details", GLib.VariantType.new("s"))
        details.connect("activate", self._on_details)
        group.add_action(details)

        edit = Gio.SimpleAction.new("edit", GLib.VariantType.new("s"))
        edit.connect("activate", self._on_edit)
        group.add_action(edit)

        remove = Gio.SimpleAction.new("remove", GLib.VariantType.new("s"))
        remove.connect("activate", self._on_remove)
        group.add_action(remove)

        self.insert_action_group("row", group)

    # ------------------------------------------------------------ yükleme

    def _loader(self):
        # Simge dizinini de arka planda hazırla; satırlar çizilirken
        # ana döngü dosya taramasıyla uğraşmasın.
        icons.index()
        if self.source is Source.AUTOSTART:
            return xdg_autostart.list_items()
        return systemd.list_items(user=self.source is Source.USER_UNIT)

    def reload(self, show_spinner: bool = True) -> None:
        if show_spinner and not self.loaded:
            self.stack.set_visible_child_name("loading")

        def done(result, error):
            self.loaded = True
            self.error = error
            self.items = result or []
            self.rebuild()
            return False

        run_in_thread(self._loader, done)

    def _find_item(self, key: str) -> Item | None:
        for item in self.items:
            if item.key == key:
                return item
        return None

    # ------------------------------------------------------------ çizim

    def visible_items(self) -> list[Item]:
        query = self.window.search_text().casefold()
        show_hidden = self.window.show_hidden
        only_enabled = self.window.only_enabled
        out = []
        for item in self.items:
            if item.hidden_entry and not show_hidden:
                continue
            if only_enabled and not item.enabled:
                continue
            if query and query not in item.search_blob:
                continue
            out.append(item)
        return out

    def retranslate(self) -> None:
        self.spinner_page.set_title(_("Loading…"))
        self.rebuild()

    def _on_hint_clicked(self, _button) -> None:
        action = self.window.lookup_action("show-hidden")
        if action is not None:
            action.change_state(GLib.Variant.new_boolean(True))

    def _update_hint(self) -> None:
        hidden_count = sum(1 for i in self.items if i.hidden_entry)
        show = hidden_count > 0 and not self.window.show_hidden
        self.hint.set_visible(show)
        if show:
            self._hint_label.set_label(
                _("%d hidden system components are not shown — show them")
                % hidden_count
            )

    def _clear_rows(self) -> None:
        for group, row in self._rows:
            group.remove(row)
        self._rows = []

    def rebuild(self) -> None:
        self._clear_rows()
        self._update_hint()

        if self.error is not None:
            self.empty_page.set_icon_name("dialog-error-symbolic")
            self.empty_page.set_title(_("Could not load the list"))
            self.empty_page.set_description(str(self.error))
            self.stack.set_visible_child_name("empty")
            self.window.update_counts()
            return

        items = self.visible_items()
        if not items:
            self.empty_page.set_icon_name("system-search-symbolic")
            if self.window.search_text():
                self.empty_page.set_title(_("No matching entries"))
                self.empty_page.set_description(
                    _("Nothing found for “%s”.") % self.window.search_text()
                )
            else:
                self.empty_page.set_title(_("Nothing to show"))
                self.empty_page.set_description(
                    _("You can show hidden system components from the menu.")
                )
            self.stack.set_visible_child_name("empty")
            self.window.update_counts()
            return

        on_items = [i for i in items if i.enabled]
        off_items = [i for i in items if not i.enabled]

        for group, group_items in ((self.on_group, on_items),
                                   (self.off_group, off_items)):
            for item in group_items:
                row = ItemRow(item, self)
                group.add(row)
                self._rows.append((group, row))

        self.on_group.set_visible(bool(on_items))
        self.off_group.set_visible(bool(off_items))
        self.on_group.set_title(self._on_title())
        self.on_group.set_description(
            "%s · %s" % (self._count_label(len(on_items)), self._effect_note())
        )
        self.off_group.set_title(_("Off"))
        self.off_group.set_description(self._count_label(len(off_items)))
        self.stack.set_visible_child_name("list")
        self.window.update_counts()

    def _on_title(self) -> str:
        if self.source is Source.AUTOSTART:
            return _("Starts at login")
        return _("Enabled")

    def _effect_note(self) -> str:
        if self.source is Source.AUTOSTART:
            return _("turning one off applies at your next login")
        return _("changes apply at the next startup")

    @staticmethod
    def _count_label(count: int) -> str:
        return _("1 entry") if count == 1 else _("%d entries") % count

    # ------------------------------------------------------------ açma/kapama

    def request_toggle(self, row: ItemRow, enabled: bool) -> None:
        item = row.item
        needs_confirm = not enabled and (item.critical or item.needs_root)
        if needs_confirm:
            self._confirm_then_apply(row, enabled)
        else:
            self._apply(row, enabled, stop_now=False)

    def _confirm_then_apply(self, row: ItemRow, enabled: bool) -> None:
        item = row.item
        dialog = Adw.AlertDialog(
            heading=_("Turn off “%s”?") % item.name,
            body_use_markup=False,
        )
        body = []
        if item.critical:
            body.append(_(
                "This may be a component your system or session needs. "
                "Turning it off can cause problems at startup."
            ))
        if item.needs_root:
            body.append(_("You will be asked for your administrator password."))
        body.append(_("The change takes effect at the next startup."))
        dialog.set_body("\n\n".join(body))

        check = Gtk.CheckButton(label=_("Stop the service now as well"))
        dialog.set_extra_child(check)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("confirm", _("Turn off"))
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response):
            if response == "confirm":
                self._apply(row, enabled, stop_now=check.get_active())
            else:
                row.set_active_silently(item.enabled)

        dialog.connect("response", on_response)
        dialog.present(self.window)

    def _apply(self, row: ItemRow, enabled: bool, stop_now: bool) -> None:
        item = row.item
        row.switch.set_sensitive(False)

        def work():
            if item.source is Source.AUTOSTART:
                xdg_autostart.set_enabled(item, enabled)
                return ""
            return systemd.set_enabled(item, enabled, stop_now=stop_now)

        def done(_result, error):
            row.switch.set_sensitive(item.toggleable)
            if error is not None:
                row.set_active_silently(item.enabled)
                self.window.toast(_("Could not change it: %s") % error, timeout=6)
            else:
                item.enabled = enabled
                message = _("“%s” turned on") if enabled else _("“%s” turned off")
                self.window.toast(message % item.name)
                self.reload(show_spinner=False)
            return False

        run_in_thread(work, done)

    # ------------------------------------------------------------ satır menüsü

    def _on_details(self, _action, param) -> None:
        item = self._find_item(param.get_string())
        if item:
            DetailsDialog(item, self).present(self.window)

    def _on_edit(self, _action, param) -> None:
        item = self._find_item(param.get_string())
        if item is not None and xdg_autostart.is_editable(item):
            EditEntryDialog(self.window, item).present(self.window)

    def _on_remove(self, _action, param) -> None:
        item = self._find_item(param.get_string())
        if item is None:
            return
        restoring = bool(item.system_path)
        dialog = Adw.AlertDialog(
            heading=_("Restore default?") if restoring else _("Delete entry?"),
            body=(
                _("Your change to “%s” will be removed and the system default "
                  "will come back.") % item.name
                if restoring
                else _("The startup entry “%s” will be permanently deleted.")
                % item.name
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("ok", _("Undo") if restoring else _("Delete"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response):
            if response != "ok":
                return

            def done(result, error):
                if error is not None:
                    self.window.toast(_("Could not delete it: %s") % error, timeout=6)
                else:
                    self.window.toast(
                        _("Restored to default") if result == "restored"
                        else _("Entry deleted")
                    )
                    self.reload(show_spinner=False)
                return False

            run_in_thread(lambda: xdg_autostart.remove(item), done)

        dialog.connect("response", on_response)
        dialog.present(self.window)


class DetailsDialog(Adw.Dialog):
    """Bir girdinin ayrıntıları ve ona uygulanabilecek eylemler."""

    def __init__(self, item: Item, page: "ItemsPage" | None = None):
        super().__init__(title=_("Details"), content_width=520, content_height=600)
        self.item = item
        self.page = page

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=item.name, description=item.description or None)
        page.add(group)

        rows = [
            (_("Source"), item.source.title),
            (_("Identifier"), item.key),
            (_("State"), _("On") if item.enabled else _("Off")),
        ]
        if item.unit_state:
            rows.append((_("Unit state"), item.unit_state))
        if item.running is not None:
            rows.append((_("Right now"),
                         _("running") if item.running else _("not running")))
        if item.command:
            rows.append((
                _("Command") if item.source is Source.AUTOSTART else _("Unit file"),
                item.command,
            ))
        if item.user_path:
            rows.append((_("User file"), item.user_path))
        if item.system_path and item.source is Source.AUTOSTART:
            rows.append((_("System file"), item.system_path))
        rows.append((_("Scope"), item.scope.title))

        for label, value in rows:
            row = Adw.ActionRow(title=label, subtitle=value or "—")
            row.set_subtitle_selectable(True)
            row.set_subtitle_lines(0)
            copy = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
            copy.add_css_class("flat")
            copy.set_tooltip_text(_("Copy"))
            copy.connect("clicked", self._copy, value)
            row.add_suffix(copy)
            group.add(row)

        if item.notes:
            notes = Adw.PreferencesGroup(title=_("Notes"))
            for note in item.notes:
                notes.add(Adw.ActionRow(title=note.render(), title_lines=0))
            page.add(notes)

        removable = (item.source is Source.AUTOSTART
                     and xdg_autostart.can_remove(item))
        if removable and self.page is not None:
            actions = Adw.PreferencesGroup()
            label = (_("Restore default") if item.system_path
                     else _("Delete entry"))
            button = Gtk.Button(label=label, halign=Gtk.Align.CENTER,
                                margin_top=6)
            button.add_css_class("destructive-action")
            button.add_css_class("pill")
            button.connect("clicked", self._on_remove)
            actions.add(button)
            page.add(actions)

        header = Adw.HeaderBar()
        if xdg_autostart.is_editable(item) and self.page is not None:
            edit = Gtk.Button(label=_("Edit…"))
            edit.connect("clicked", self._on_edit)
            header.pack_end(edit)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)

    def _on_edit(self, _button) -> None:
        window = self.page.window
        self.close()
        EditEntryDialog(window, self.item).present(window)

    def _on_remove(self, _button) -> None:
        page = self.page
        self.close()
        page.activate_action("row.remove", GLib.Variant.new_string(self.item.key))

    def _copy(self, _button, value: str) -> None:
        display = Gdk.Display.get_default()
        if display and value:
            display.get_clipboard().set(value)


class AddEntryDialog(Adw.Dialog):
    """Yeni autostart girdisi oluşturma formu."""

    def __init__(self, window: "MainWindow"):
        super().__init__(title=_("New startup entry"), content_width=460)
        self.window = window

        self.name_row = Adw.EntryRow(title=_("Display name"))
        self.cmd_row = Adw.EntryRow(title=_("Command"))
        self.comment_row = Adw.EntryRow(title=_("Description (optional)"))

        group = Adw.PreferencesGroup(
            description=_("The entry is created in ~/.config/autostart and "
                          "runs at your next login.")
        )
        for row in (self.name_row, self.cmd_row, self.comment_row):
            group.add(row)

        page = Adw.PreferencesPage()
        page.add(group)

        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_a: self.close())
        save = Gtk.Button(label=_("Add"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)

        header = Adw.HeaderBar(show_end_title_buttons=False,
                               show_start_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(save)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self.set_default_widget(save)

        for row in (self.name_row, self.cmd_row):
            row.connect("entry-activated", self._on_save)

    def _on_save(self, *_args) -> None:
        name = self.name_row.get_text().strip()
        command = self.cmd_row.get_text().strip()
        comment = self.comment_row.get_text().strip()

        self.name_row.remove_css_class("error")
        self.cmd_row.remove_css_class("error")
        if not name:
            self.name_row.add_css_class("error")
            return
        if not command:
            self.cmd_row.add_css_class("error")
            return

        try:
            xdg_autostart.add_entry(name, command, comment)
        except (OSError, ValueError) as exc:
            self.window.toast(_("Could not add it: %s") % exc, timeout=6)
            return

        self.close()
        self.window.toast(_("“%s” added") % name)
        self.window.pages[Source.AUTOSTART].reload(show_spinner=False)



class IconPickerDialog(Adw.Dialog):
    """Simge temasındaki görsellerden birini seçmek için arama penceresi."""

    MAX_RESULTS = 240

    def __init__(self, current: str, on_pick):
        super().__init__(title=_("Choose an icon"),
                         content_width=560, content_height=560)
        self.on_pick = on_pick
        self._names: list[str] = []

        display = Gdk.Display.get_default()
        self.theme = Gtk.IconTheme.get_for_display(display) if display else None

        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.set_placeholder_text(_("Search icons"))
        self.search.set_text(current if current and not current.startswith("/") else "")
        self.search.connect("search-changed", lambda *_a: self._refresh())

        self.flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=4,
            max_children_per_line=8,
            row_spacing=6,
            column_spacing=6,
            margin_start=12, margin_end=12, margin_top=6, margin_bottom=12,
        )

        self.status = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title=_("No matching icons"),
        )
        self.stack = Gtk.Stack(vexpand=True)
        scroller = Gtk.ScrolledWindow(child=self.flow, vexpand=True)
        self.stack.add_named(scroller, "list")
        self.stack.add_named(self.status, "empty")

        from_file = Gtk.Button(label=_("From a file…"))
        from_file.connect("clicked", self._on_from_file)

        header = Adw.HeaderBar()
        header.pack_end(from_file)

        search_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                             margin_start=12, margin_end=12,
                             margin_top=6, margin_bottom=6)
        search_bar.append(self.search)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(search_bar)
        box.append(self.stack)

        view = Adw.ToolbarView(content=box)
        view.add_top_bar(header)
        self.set_child(view)

        self._refresh()

    def _all_names(self) -> list[str]:
        if self._names:
            return self._names
        if self.theme is None:
            return []
        self._names = sorted(self.theme.get_icon_names())
        return self._names

    def _refresh(self) -> None:
        query = self.search.get_text().strip().casefold()
        self.flow.remove_all()

        names = self._all_names()
        if query:
            exact = [n for n in names if n.casefold() == query]
            starts = [n for n in names if n.casefold().startswith(query)
                      and n.casefold() != query]
            contains = [n for n in names if query in n.casefold()
                        and not n.casefold().startswith(query)]
            names = exact + starts + contains
        shown = names[: self.MAX_RESULTS]

        if not shown:
            self.stack.set_visible_child_name("empty")
            return
        self.stack.set_visible_child_name("list")
        for name in shown:
            self.flow.append(self._tile(name))

    def _tile(self, name: str) -> Gtk.Widget:
        button = Gtk.Button(has_frame=False, tooltip_text=name)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                          margin_top=6, margin_bottom=6)
        content.append(Gtk.Image(icon_name=name, pixel_size=40))
        label = Gtk.Label(label=name, ellipsize=Pango.EllipsizeMode.MIDDLE,
                          max_width_chars=12)
        label.add_css_class("caption")
        content.append(label)
        button.set_child(content)
        button.connect("clicked", lambda *_a: self._pick(name))
        return button

    def _pick(self, value: str) -> None:
        self.on_pick(value)
        self.close()

    def _on_from_file(self, _button) -> None:
        chooser = Gtk.FileDialog(title=_("Choose an icon"))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        image_filter = Gtk.FileFilter()
        image_filter.set_name(_("Images"))
        for pattern in ("*.png", "*.svg", "*.xpm", "*.jpg", "*.jpeg"):
            image_filter.add_pattern(pattern)
        filters.append(image_filter)
        chooser.set_filters(filters)

        def done(dialog, result):
            try:
                gfile = dialog.open_finish(result)
            except GLib.Error:
                return
            if gfile is not None and gfile.get_path():
                self._pick(gfile.get_path())

        chooser.open(self.get_root(), None, done)


class KeyNameDialog(Adw.Dialog):
    """Gelişmiş bölümde yeni bir .desktop anahtarı eklemek için küçük form."""

    def __init__(self, on_add):
        super().__init__(title=_("Add a key"), content_width=400)
        self.on_add = on_add

        self.key_row = Adw.EntryRow(title=_("Key name"))
        group = Adw.PreferencesGroup(
            description=_("For example Terminal, Path or Name[tr].")
        )
        group.add(self.key_row)
        page = Adw.PreferencesPage()
        page.add(group)

        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_a: self.close())
        add = Gtk.Button(label=_("Add"))
        add.add_css_class("suggested-action")
        add.connect("clicked", self._on_add)

        header = Adw.HeaderBar(show_end_title_buttons=False,
                               show_start_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(add)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self.set_default_widget(add)
        self.key_row.connect("entry-activated", self._on_add)

    def _on_add(self, *_args) -> None:
        name = self.key_row.get_text().strip()
        self.key_row.remove_css_class("error")
        if not name or not KEY_NAME_RE.match(name):
            self.key_row.add_css_class("error")
            return
        self.close()
        self.on_add(name)


class EditEntryDialog(Adw.Dialog):
    """Bir autostart girdisinin .desktop içeriğini düzenler."""

    def __init__(self, window: "MainWindow", item: Item):
        super().__init__(title=_("Edit entry"),
                         content_width=560, content_height=640)
        self.window = window
        self.item = item
        self.removed: list[str] = []
        self.extra_rows: dict[str, Adw.EntryRow] = {}

        try:
            self.df = xdg_autostart.read_entry(item)
        except (OSError, ValueError) as exc:
            self.df = None
            self.window.toast(_("Could not open it: %s") % exc, timeout=6)

        entries = dict(self.df.entries()) if self.df else {}

        self.name_row = Adw.EntryRow(title=_("Display name"))
        self.name_row.set_text(entries.get("Name", item.name))
        self.comment_row = Adw.EntryRow(title=_("Description"))
        self.comment_row.set_text(entries.get("Comment", ""))
        self.cmd_row = Adw.EntryRow(title=_("Command"))
        self.cmd_row.set_text(entries.get("Exec", ""))

        self.icon_value = entries.get("Icon", "")
        self.icon_row = Adw.ActionRow(title=_("Icon"))
        self.icon_preview = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)
        self.icon_row.add_prefix(self.icon_preview)
        pick = Gtk.Button(label=_("Change…"), valign=Gtk.Align.CENTER)
        pick.connect("clicked", self._on_pick_icon)
        self.icon_row.add_suffix(pick)
        clear = Gtk.Button(icon_name="edit-clear-symbolic",
                           valign=Gtk.Align.CENTER, tooltip_text=_("Clear"))
        clear.add_css_class("flat")
        clear.connect("clicked", lambda *_a: self._set_icon(""))
        self.icon_row.add_suffix(clear)
        self._set_icon(self.icon_value)

        self.terminal_row = Adw.SwitchRow(
            title=_("Run in a terminal"),
            active=entries.get("Terminal", "").strip().casefold()
            in ("true", "1", "yes", "on"),
        )

        basic = Adw.PreferencesGroup(title=_("Entry"))
        for row in (self.name_row, self.comment_row, self.cmd_row,
                    self.icon_row, self.terminal_row):
            basic.add(row)

        self.advanced = Adw.PreferencesGroup(
            title=_("Other keys"),
            description=_("Everything else in the .desktop file."),
        )
        add_button = Gtk.Button(icon_name="list-add-symbolic",
                                valign=Gtk.Align.CENTER,
                                tooltip_text=_("Add a key"))
        add_button.add_css_class("flat")
        add_button.connect("clicked", self._on_add_key)
        self.advanced.set_header_suffix(add_button)

        handled = set(xdg_autostart.BASIC_KEYS) | set(xdg_autostart.PROTECTED_KEYS)
        for key, value in (self.df.entries() if self.df else []):
            if key in handled:
                continue
            self._add_extra_row(key, value)

        page = Adw.PreferencesPage()
        page.add(basic)
        page.add(self.advanced)

        if item.system_path and not item.user_path:
            page.add(self._copy_hint())

        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_a: self.close())
        save = Gtk.Button(label=_("Save"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)

        header = Adw.HeaderBar(show_end_title_buttons=False,
                               show_start_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(save)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self.set_default_widget(save)

    # ----------------------------------------------------------- yardımcılar

    def _copy_hint(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(
            title=_("This is a system entry"),
            subtitle=_("Your changes are saved as a personal copy; the "
                       "original file stays untouched."),
            subtitle_lines=0,
        )
        row.add_prefix(Gtk.Image(icon_name="dialog-information-symbolic"))
        group.add(row)
        return group

    def _set_icon(self, value: str) -> None:
        self.icon_value = value
        candidates = [value] if value else icons.candidates(self.item)
        apply_icon(self.icon_preview, candidates, icons.fallback(self.item))
        self.icon_row.set_subtitle(value or _("Not set"))

    def _on_pick_icon(self, _button) -> None:
        IconPickerDialog(self.icon_value, self._set_icon).present(self)

    def _add_extra_row(self, key: str, value: str) -> None:
        row = Adw.EntryRow(title=key)
        row.set_text(value)
        delete = Gtk.Button(icon_name="user-trash-symbolic",
                            valign=Gtk.Align.CENTER,
                            tooltip_text=_("Remove this key"))
        delete.add_css_class("flat")
        delete.connect("clicked", lambda *_a, k=key: self._remove_extra(k))
        row.add_suffix(delete)
        self.advanced.add(row)
        self.extra_rows[key] = row

    def _remove_extra(self, key: str) -> None:
        row = self.extra_rows.pop(key, None)
        if row is not None:
            self.advanced.remove(row)
            self.removed.append(key)

    def _on_add_key(self, _button) -> None:
        def add(name: str) -> None:
            if name in self.extra_rows:
                self.extra_rows[name].grab_focus()
                return
            if name in self.removed:
                self.removed.remove(name)
            self._add_extra_row(name, "")
            self.extra_rows[name].grab_focus()

        KeyNameDialog(add).present(self)

    # ---------------------------------------------------------------- kayıt

    def _on_save(self, *_args) -> None:
        name = self.name_row.get_text().strip()
        command = self.cmd_row.get_text().strip()
        self.name_row.remove_css_class("error")
        self.cmd_row.remove_css_class("error")
        if not name:
            self.name_row.add_css_class("error")
            return
        if not command:
            self.cmd_row.add_css_class("error")
            return

        values = {
            "Name": name,
            "Comment": self.comment_row.get_text().strip(),
            "Exec": command,
            "Icon": self.icon_value.strip(),
            "Terminal": "true" if self.terminal_row.get_active() else "false",
        }
        for key, row in self.extra_rows.items():
            values[key] = row.get_text().strip()

        try:
            xdg_autostart.save_entry(self.item, values, tuple(self.removed))
        except (OSError, ValueError) as exc:
            self.window.toast(_("Could not save it: %s") % exc, timeout=6)
            return

        self.close()
        self.window.toast(_("“%s” saved") % name)
        self.window.pages[Source.AUTOSTART].reload(show_spinner=False)


class AppPickerDialog(Adw.Dialog):
    """Kurulu uygulamalardan birini başlangıca ekler."""

    def __init__(self, window: "MainWindow"):
        super().__init__(title=_("Choose an application"),
                         content_width=520, content_height=620)
        self.window = window
        self.apps: list[apps.App] = []

        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.set_placeholder_text(_("Search applications"))
        self.search.connect("search-changed", lambda *_a: self._rebuild())

        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                    margin_start=12, margin_end=12,
                                    margin_top=6, margin_bottom=12)
        self.list_box.add_css_class("boxed-list")

        self.status = Adw.StatusPage(icon_name="system-search-symbolic",
                                     title=_("No matching applications"))
        spinner = Adw.StatusPage(title=_("Loading…"))
        spinner.set_child(Adw.Spinner())

        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(Gtk.ScrolledWindow(child=self.list_box,
                                                vexpand=True), "list")
        self.stack.add_named(self.status, "empty")
        self.stack.add_named(spinner, "loading")
        self.stack.set_visible_child_name("loading")

        search_box = Gtk.Box(margin_start=12, margin_end=12,
                             margin_top=6, margin_bottom=6)
        search_box.append(self.search)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(search_box)
        box.append(self.stack)

        view = Adw.ToolbarView(content=box)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)

        def done(result, error):
            self.apps = result or []
            self._rebuild()
            return False

        run_in_thread(apps.installed, done)

    def _rebuild(self) -> None:
        query = self.search.get_text().strip().casefold()
        self.list_box.remove_all()
        shown = [a for a in self.apps if not query or query in a.search_blob]
        if not shown:
            self.stack.set_visible_child_name("empty")
            return
        self.stack.set_visible_child_name("list")
        for app in shown:
            self.list_box.append(self._row(app))

    def _row(self, app: "apps.App") -> Gtk.Widget:
        row = Adw.ActionRow(title=GLib.markup_escape_text(app.name),
                            activatable=True)
        if app.comment:
            row.set_subtitle(GLib.markup_escape_text(app.comment))
        image = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)
        apply_icon(image, [app.icon, app.app_id, Path(app.command.split()[0]).name
                           if app.command else ""],
                   "application-x-executable-symbolic")
        row.add_prefix(image)
        row.connect("activated", lambda *_a, a=app: self._choose(a))
        return row

    def _choose(self, app: "apps.App") -> None:
        try:
            xdg_autostart.add_entry(
                name=app.name,
                command=app.command,
                comment=app.comment,
                icon=app.icon,
                terminal=app.terminal,
                app_id=app.app_id,
            )
        except (OSError, ValueError) as exc:
            self.window.toast(_("Could not add it: %s") % exc, timeout=6)
            return
        self.close()
        self.window.toast(_("“%s” added") % app.name)
        self.window.pages[Source.AUTOSTART].reload(show_spinner=False)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(820, 680)
        self.set_size_request(360, 360)

        self.show_hidden = False
        self.only_enabled = False

        self.view_stack = Adw.ViewStack()
        self.pages: dict[Source, ItemsPage] = {}
        for source, icon in (
            (Source.AUTOSTART, "view-grid-symbolic"),
            (Source.USER_UNIT, "avatar-default-symbolic"),
            (Source.SYSTEM_UNIT, "emblem-system-symbolic"),
        ):
            page = ItemsPage(self, source)
            self.pages[source] = page
            self.view_stack.add_titled_with_icon(page, source.value, source.title, icon)

        self.search_entry = Gtk.SearchEntry(
            placeholder_text=_("Search in name and command"), hexpand=True
        )
        self.search_entry.connect("search-changed", lambda *_a: self.rebuild_all())
        self.search_bar = Gtk.SearchBar(child=self.search_entry)
        self.search_bar.set_key_capture_widget(self)
        self.search_bar.connect_entry(self.search_entry)

        self.add_button = Gtk.MenuButton(icon_name="list-add-symbolic",
                                         menu_model=self._build_add_menu())
        self.add_button.set_tooltip_text(_("Add a new startup entry"))

        self.search_toggle = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self.search_toggle.set_tooltip_text(_("Search (Ctrl+F)"))
        self.search_toggle.bind_property(
            "active", self.search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text(_("Refresh (Ctrl+R)"))
        self.refresh_button.connect("clicked", lambda *_a: self.reload_all())

        self.menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.menu_button.set_tooltip_text(_("Menu"))

        self.switcher = Adw.ViewSwitcher(
            stack=self.view_stack, policy=Adw.ViewSwitcherPolicy.WIDE
        )
        header = Adw.HeaderBar(title_widget=self.switcher)
        header.pack_start(self.add_button)
        header.pack_end(self.menu_button)
        header.pack_end(self.refresh_button)
        header.pack_end(self.search_toggle)


        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack, reveal=False)

        self.toolbar = Adw.ToolbarView(content=self.view_stack)
        self.toolbar.add_top_bar(header)
        self.toolbar.add_top_bar(self.search_bar)
        self.toolbar.add_bottom_bar(self.switcher_bar)

        self.toasts = Adw.ToastOverlay(child=self.toolbar)
        self.set_content(self.toasts)

        # Dar pencerede üstteki geniş sekme seçici yerine alt çubuğu kullan.
        breakpoint_ = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 560px")
        )
        breakpoint_.add_setter(self.switcher_bar, "reveal", True)
        breakpoint_.connect("apply", lambda *_a: header.set_title_widget(None))
        breakpoint_.connect(
            "unapply", lambda *_a: header.set_title_widget(self.switcher)
        )
        self.add_breakpoint(breakpoint_)

        self.view_stack.connect("notify::visible-child", self._on_page_changed)
        self._install_actions(app)
        self.menu_button.set_menu_model(self._build_menu())
        self.reload_all()

    # ------------------------------------------------------------- menü

    def _build_add_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append(_("From installed applications…"), "win.add-app")
        menu.append(_("Enter a command…"), "win.add-custom")
        return menu

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()

        view_section = Gio.Menu()
        view_section.append(_("Show hidden system components"), "win.show-hidden")
        view_section.append(_("Only the enabled ones"), "win.only-enabled")
        menu.append_section(_("View"), view_section)

        language_menu = Gio.Menu()
        for code, label in i18n.available_languages().items():
            language_menu.append(label, f"win.language::{code}")
        menu.append_submenu(_("Language"), language_menu)

        other = Gio.Menu()
        other.append(_("Refresh"), "win.refresh")
        other.append(_("Keyboard Shortcuts"), "win.shortcuts")
        other.append(_("About"), "win.about")
        menu.append_section(None, other)
        return menu

    # ------------------------------------------------------------- eylemler

    def _install_actions(self, app: Adw.Application) -> None:
        hidden = Gio.SimpleAction.new_stateful(
            "show-hidden", None, GLib.Variant.new_boolean(False)
        )
        hidden.connect("change-state", self._on_show_hidden)
        self.add_action(hidden)

        only_enabled = Gio.SimpleAction.new_stateful(
            "only-enabled", None, GLib.Variant.new_boolean(False)
        )
        only_enabled.connect("change-state", self._on_only_enabled)
        self.add_action(only_enabled)

        language = Gio.SimpleAction.new_stateful(
            "language",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(i18n.current_language()),
        )
        language.connect("change-state", self._on_language)
        self.add_action(language)

        refresh = Gio.SimpleAction.new("refresh", None)
        refresh.connect("activate", lambda *_a: self.reload_all())
        self.add_action(refresh)

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *_a: self._show_about())
        self.add_action(about)

        add_app = Gio.SimpleAction.new("add-app", None)
        add_app.connect("activate", lambda *_a: AppPickerDialog(self).present(self))
        self.add_action(add_app)

        add_custom = Gio.SimpleAction.new("add-custom", None)
        add_custom.connect("activate",
                           lambda *_a: AddEntryDialog(self).present(self))
        self.add_action(add_custom)

        shortcuts = Gio.SimpleAction.new("shortcuts", None)
        shortcuts.connect("activate", lambda *_a: self._show_shortcuts())
        self.add_action(shortcuts)

        app.set_accels_for_action("win.add-app", ["<Primary>n"])
        app.set_accels_for_action("win.shortcuts", ["<Primary>question"])
        app.set_accels_for_action("win.refresh", ["<Primary>r"])
        app.set_accels_for_action("window.close", ["<Primary>w", "<Primary>q"])

    def _on_show_hidden(self, action, value) -> None:
        action.set_state(value)
        self.show_hidden = value.get_boolean()
        self.rebuild_all()

    def _on_only_enabled(self, action, value) -> None:
        action.set_state(value)
        self.only_enabled = value.get_boolean()
        self.rebuild_all()

    def _on_language(self, action, value) -> None:
        code = value.get_string()
        if code not in i18n.available_languages():
            return
        action.set_state(value)
        i18n.set_language(code)
        try:
            settings.set_language(code)
        except OSError as exc:
            self.toast(_("Could not change it: %s") % exc, timeout=6)
        self.retranslate()

    def _on_page_changed(self, *_args) -> None:
        page = self.current_page()
        self.add_button.set_visible(page.source is Source.AUTOSTART)

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            developer_name=APP_DEVELOPER,
            version=__version__,
            comments=(
                _("Shows the applications and services that start by "
                  "themselves when you turn on your computer, and lets you "
                  "turn them off.")
                + "\n\n"
                + "• %s: ~/.config/autostart, /etc/xdg/autostart\n"
                % Source.AUTOSTART.title
                + "• %s: systemctl --user\n" % Source.USER_UNIT.title
                + "• %s: systemctl (pkexec)" % Source.SYSTEM_UNIT.title
            ),
            website=PROJECT_URL,
            issue_url=ISSUE_URL,
            copyright="© %s %s" % (COPYRIGHT_YEAR, APP_DEVELOPER),
            license_type=Gtk.License.MIT_X11,
            release_notes_version=__version__,
            release_notes=_(
                "<p>Flatpak applications now stay off once you turn them "
                "off.</p>"
                "<ul>"
                "<li>Every row shows the application's or service's own "
                "icon</li>"
                "<li>Startup entries can be edited, icon included</li>"
                "<li>New entries can be picked from the installed "
                "applications</li>"
                "<li>Added a keyboard shortcuts window</li>"
                "</ul>"
            ),
            debug_info=self._debug_info(),
            debug_info_filename="liftoff-debug.txt",
        )
        about.set_developers([
            "%s https://github.com/%s" % (APP_DEVELOPER, APP_DEVELOPER_HANDLE)
        ])
        about.set_designers([APP_DEVELOPER])
        credits_line = _("translator-credits")
        if credits_line != "translator-credits":
            about.set_translator_credits(credits_line)
        about.add_acknowledgement_section(
            _("Built with"),
            [
                "GTK https://www.gtk.org",
                "libadwaita https://gnome.pages.gitlab.gnome.org/libadwaita/",
                "PyGObject https://pygobject.gnome.org",
            ],
        )
        about.present(self)

    def _show_shortcuts(self) -> None:
        dialog = Adw.ShortcutsDialog()

        general = Adw.ShortcutsSection(title=_("General"))
        for title, accel in (
            (_("Add a startup entry"), "<Control>n"),
            (_("Search"), "<Control>f"),
            (_("Refresh"), "<Control>r"),
            (_("Keyboard Shortcuts"), "<Control>question"),
            (_("Close the window"), "<Control>w"),
        ):
            general.add(Adw.ShortcutsItem(title=title, accelerator=accel))
        dialog.add(general)
        dialog.present(self)

    def _debug_info(self) -> str:
        """Sorun bildirimine eklenecek ortam bilgisi."""
        lines = [
            "%s %s" % (APP_NAME, __version__),
            "App ID: %s" % APP_ID,
            "Python: %s" % platform.python_version(),
            "GTK: %d.%d.%d" % (
                Gtk.get_major_version(),
                Gtk.get_minor_version(),
                Gtk.get_micro_version(),
            ),
            "libadwaita: %d.%d.%d" % (
                Adw.get_major_version(),
                Adw.get_minor_version(),
                Adw.get_micro_version(),
            ),
            "OS: %s" % platform.platform(),
            "Desktop: %s" % (
                GLib.getenv("XDG_CURRENT_DESKTOP") or "unknown"
            ),
            "Session: %s" % (GLib.getenv("XDG_SESSION_TYPE") or "unknown"),
            "Language: %s" % i18n.current_language(),
            "Flatpak: %s" % (
                "yes" if Path("/.flatpak-info").exists() else "no"
            ),
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------- yardımcı

    def retranslate(self) -> None:
        """Dil değişince tüm görünür metinleri yeniden yazar."""
        self.search_entry.set_placeholder_text(_("Search in name and command"))
        self.add_button.set_tooltip_text(_("Add a new startup entry"))
        self.search_toggle.set_tooltip_text(_("Search (Ctrl+F)"))
        self.refresh_button.set_tooltip_text(_("Refresh (Ctrl+R)"))
        self.menu_button.set_tooltip_text(_("Menu"))
        self.menu_button.set_menu_model(self._build_menu())
        self.add_button.set_menu_model(self._build_add_menu())
        for source, page in self.pages.items():
            self.view_stack.get_page(page).set_title(source.title)
            page.retranslate()

    def current_page(self) -> ItemsPage:
        child = self.view_stack.get_visible_child()
        return child if isinstance(child, ItemsPage) else self.pages[Source.AUTOSTART]

    def search_text(self) -> str:
        if not self.search_bar.get_search_mode():
            return ""
        return self.search_entry.get_text().strip()

    def reload_all(self) -> None:
        icons.invalidate()
        for page in self.pages.values():
            page.reload()

    def rebuild_all(self) -> None:
        for page in self.pages.values():
            if page.loaded:
                page.rebuild()

    def update_counts(self) -> None:
        for page in self.pages.values():
            stack_page = self.view_stack.get_page(page)
            count = sum(1 for i in page.visible_items() if i.enabled)
            stack_page.set_badge_number(count)
            stack_page.set_needs_attention(False)

    def toast(self, message: str, timeout: int = 3) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=timeout))


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        # Kayıtlı tercih yoksa sistem dili Türkçeyse Türkçe, değilse İngilizce.
        i18n.set_language(settings.resolve_language())
        self.window: MainWindow | None = None

    def do_activate(self) -> None:
        if self.window is None:
            self.window = MainWindow(self)
        self.window.present()


def main(argv: list[str] | None = None) -> int:
    import sys

    return Application().run(argv if argv is not None else sys.argv)
