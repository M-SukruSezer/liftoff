"""GTK4 / libadwaita arayüzü."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, __version__, i18n, settings  # noqa: E402
from . import systemd, xdg_autostart  # noqa: E402
from .i18n import gettext as _  # noqa: E402
from .models import Item, Source  # noqa: E402


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
        self.set_activatable_widget(self.switch)

        self.add_suffix(self._build_menu())

    # ------------------------------------------------------------- görünüm

    def _subtitle(self) -> str:
        parts: list[str] = []
        if self.item.description:
            parts.append(self.item.description)
        if self.item.source is Source.AUTOSTART:
            if self.item.command:
                parts.append(self.item.command)
        elif self.item.running is True:
            parts.append(_("running now"))
        elif self.item.running is False:
            parts.append(_("not running now"))
        return " · ".join(parts)

    def _build_icon(self) -> Gtk.Widget:
        name = self.item.icon
        if self.item.source is not Source.AUTOSTART:
            name = "system-run-symbolic"
        image = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)
        display = Gdk.Display.get_default()
        theme = Gtk.IconTheme.get_for_display(display) if display else None
        if name and name.startswith("/") and Path(name).exists():
            image.set_from_file(name)
        elif name and theme is not None and theme.has_icon(name):
            image.set_from_icon_name(name)
        else:
            image.set_from_icon_name("application-x-executable-symbolic")
        if self.item.hidden_entry:
            image.add_css_class("dim-label")
        return image

    def _warning_icon(self) -> Gtk.Widget | None:
        if not self.item.notes:
            return None
        critical = self.item.critical or any(n.warn for n in self.item.notes)
        icon = Gtk.Image(
            icon_name="dialog-warning-symbolic" if critical
            else "dialog-information-symbolic",
            valign=Gtk.Align.CENTER,
        )
        icon.set_tooltip_text("\n".join("• " + n.render() for n in self.item.notes))
        icon.add_css_class("warning" if critical else "dim-label")
        return icon

    def _build_menu(self) -> Gtk.Widget:
        menu = Gio.Menu()
        menu.append(_("Details"), f"row.details::{self.item.key}")
        if self.item.source is Source.AUTOSTART and xdg_autostart.can_remove(self.item):
            label = _("Restore default") if self.item.system_path else _("Delete entry")
            menu.append(label, f"row.remove::{self.item.key}")

        button = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            valign=Gtk.Align.CENTER,
            menu_model=menu,
        )
        button.add_css_class("flat")
        button.set_tooltip_text(_("More actions"))
        return button

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

        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")

        self.counter = Gtk.Label(xalign=0)
        self.counter.add_css_class("dim-label")
        self.counter.add_css_class("caption")

        # Gizlenmiş sistem bileşenleri varsa kullanıcıya tek tıkla göster.
        self.hint = Gtk.Button(has_frame=False, valign=Gtk.Align.CENTER, visible=False)
        self.hint.add_css_class("flat")
        self.hint.connect("clicked", self._on_hint_clicked)
        hint_label = Gtk.Label()
        hint_label.add_css_class("caption")
        hint_label.add_css_class("accent")
        self.hint.set_child(hint_label)
        self._hint_label = hint_label

        counter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        counter_box.append(self.counter)
        counter_box.append(self.hint)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.append(counter_box)
        content.append(self.list_box)

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

        remove = Gio.SimpleAction.new("remove", GLib.VariantType.new("s"))
        remove.connect("activate", self._on_remove)
        group.add_action(remove)

        self.insert_action_group("row", group)

    # ------------------------------------------------------------ yükleme

    def _loader(self):
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

    def rebuild(self) -> None:
        self.list_box.remove_all()
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

        for item in items:
            self.list_box.append(ItemRow(item, self))

        enabled = sum(1 for i in items if i.enabled)
        if len(items) == 1:
            label = _("Showing 1 entry · %d on · %d off") % (
                enabled, 1 - enabled)
        else:
            label = _("Showing %d entries · %d on · %d off") % (
                len(items), enabled, len(items) - enabled)
        self.counter.set_label(label)
        self.stack.set_visible_child_name("list")
        self.window.update_counts()

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
            DetailsDialog(item).present(self.window)

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
    """Bir girdinin tüm teknik ayrıntıları."""

    def __init__(self, item: Item):
        super().__init__(title=_("Details"), content_width=520, content_height=520)

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

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)

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

        self.add_button = Gtk.Button(icon_name="list-add-symbolic")
        self.add_button.set_tooltip_text(_("Add a new startup entry"))
        self.add_button.connect("clicked", lambda *_a: AddEntryDialog(self).present(self))

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

        self.banner = Adw.Banner(title=_("Changes take effect at your next login."))
        self.banner.set_revealed(False)

        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack, reveal=False)

        self.toolbar = Adw.ToolbarView(content=self.view_stack)
        self.toolbar.add_top_bar(header)
        self.toolbar.add_top_bar(self.search_bar)
        self.toolbar.add_top_bar(self.banner)
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
        self.banner.set_revealed(page.source is not Source.AUTOSTART)

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
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
            license_type=Gtk.License.MIT_X11,
        )
        about.present(self)

    # ------------------------------------------------------------- yardımcı

    def retranslate(self) -> None:
        """Dil değişince tüm görünür metinleri yeniden yazar."""
        self.search_entry.set_placeholder_text(_("Search in name and command"))
        self.add_button.set_tooltip_text(_("Add a new startup entry"))
        self.search_toggle.set_tooltip_text(_("Search (Ctrl+F)"))
        self.refresh_button.set_tooltip_text(_("Refresh (Ctrl+R)"))
        self.menu_button.set_tooltip_text(_("Menu"))
        self.menu_button.set_menu_model(self._build_menu())
        self.banner.set_title(_("Changes take effect at your next login."))
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
