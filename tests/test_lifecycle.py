"""The entry points the host itself calls, plus the CIF Viewer lookup.

Both are host-integration code with fallback branches, and neither had any
coverage: exactly the code that breaks the app rather than the output.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QWidget  # noqa: E402

import slab_builder as plugin  # noqa: E402
from slab_builder.cif_viewer_link import find_cif_viewer_widget  # noqa: E402

from test_plugin import FakeContext  # noqa: E402


class _HostWindow(QWidget):
    """Stands in for MoleditPy's main window (a real widget, so it can parent)."""

    def __init__(self, plugin_manager=None):
        super().__init__()
        self.plugin_manager = plugin_manager


class _LifecycleContext(FakeContext):
    def get_main_window(self):
        return self.main_window


@pytest.fixture
def clean_plugin(qapp):
    context, opened = plugin._context, plugin._dialog_opened
    settings = dict(plugin.current_settings)
    yield
    plugin._context = context
    plugin._dialog_opened = opened
    plugin.current_settings.clear()
    plugin.current_settings.update(settings)


def _close(context):
    dialog = context.windows.get(plugin.WINDOW_ID)
    if dialog is not None:
        dialog.close()
        dialog.deleteLater()


# -- opening ----------------------------------------------------------------


def test_open_dialog_without_a_context_still_opens(clean_plugin):
    plugin._context = None
    plugin._dialog_opened = False
    plugin._open_dialog(_HostWindow())
    assert plugin._dialog_opened is True


def test_open_dialog_registers_the_window(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin._open_dialog(None)
    assert plugin.WINDOW_ID in context.windows
    _close(context)


def test_open_dialog_reuses_a_visible_window(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin._open_dialog(None)
    first = context.windows[plugin.WINDOW_ID]
    first.show()
    plugin._open_dialog(None)
    assert context.windows[plugin.WINDOW_ID] is first
    _close(context)


def test_open_dialog_replaces_a_closed_window(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin._open_dialog(None)
    first = context.windows[plugin.WINDOW_ID]
    first.hide()
    plugin._open_dialog(None)
    assert context.windows[plugin.WINDOW_ID] is not first
    _close(context)


def test_run_opens_the_dialog(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin.run(context.main_window)
    assert plugin.WINDOW_ID in context.windows
    _close(context)


def test_editing_marks_the_project_modified(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin._open_dialog(None)
    dialog = context.windows[plugin.WINDOW_ID]
    before = context.modified
    dialog.layers_spin.setValue(9)
    assert context.modified > before
    _close(context)


def test_initialize_wires_the_menu_action(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin.initialize(context)
    assert len(context.menu_actions) == 1
    path, callback = context.menu_actions[0]
    assert path.startswith("Structure/")
    callback()
    assert plugin.WINDOW_ID in context.windows
    _close(context)


# -- CIF Viewer lookup ------------------------------------------------------


def _panel(name="CifViewerWidget"):
    widget = type(name, (), {"structure": object()})()
    return widget


def test_lookup_returns_none_without_a_window():
    assert find_cif_viewer_widget(None) is None


def test_lookup_finds_the_panel_through_the_plugin_manager(qapp):
    panel = _panel()
    manager = types.SimpleNamespace(
        plugin_windows={"CIF Viewer": {"cif_viewer_panel": panel}}
    )
    assert find_cif_viewer_widget(_HostWindow(manager)) is panel


def test_lookup_unwraps_a_dock_widget(qapp):
    """The registered object is the dock; the structure lives on its widget."""
    panel = _panel()
    dock = types.SimpleNamespace(structure=None, widget=lambda: panel)
    manager = types.SimpleNamespace(plugin_windows={"CIF Viewer": {"panel": dock}})
    assert find_cif_viewer_widget(_HostWindow(manager)) is panel


def test_lookup_ignores_other_plugins_windows(qapp):
    manager = types.SimpleNamespace(
        plugin_windows={"Something Else": {"panel": _panel()}}
    )
    assert find_cif_viewer_widget(_HostWindow(manager)) is None


def test_lookup_survives_a_hostile_registry(qapp):
    """Host internals are not ours to trust; a bad registry must not raise."""
    manager = types.SimpleNamespace(plugin_windows="not a dict")
    assert find_cif_viewer_widget(_HostWindow(manager)) is None
    manager = types.SimpleNamespace(plugin_windows={"CIF Viewer": "not a dict"})
    assert find_cif_viewer_widget(_HostWindow(manager)) is None


def test_lookup_falls_back_to_a_widget_scan(qapp):
    """No plugin manager, so the panel can only be found by scanning children."""
    window = _HostWindow(None)

    class CifViewerWidget(QWidget):
        structure = object()

    child = CifViewerWidget(window)
    assert find_cif_viewer_widget(window) is child
    child.deleteLater()


def test_the_cif_viewer_lookup_is_wired_into_the_dialog(clean_plugin):
    context = _LifecycleContext(main_window=_HostWindow())
    plugin._context = context
    plugin._open_dialog(None)
    dialog = context.windows[plugin.WINDOW_ID]
    assert dialog.get_cif_viewer() is None  # none open, but callable
    _close(context)


def test_lookup_skips_a_window_holding_no_structure(qapp):
    bare = types.SimpleNamespace(structure=None, widget=lambda: None)
    manager = types.SimpleNamespace(plugin_windows={"CIF Viewer": {"p": bare}})
    assert find_cif_viewer_widget(_HostWindow(manager)) is None


def test_lookup_skips_a_none_window(qapp):
    manager = types.SimpleNamespace(plugin_windows={"CIF Viewer": {"p": None}})
    assert find_cif_viewer_widget(_HostWindow(manager)) is None
