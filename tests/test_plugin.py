import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import slab_builder as plugin  # noqa: E402


class FakeContext:
    def __init__(self, main_window=None):
        self.main_window = main_window
        self.menu_actions = []
        self.save_handlers = []
        self.load_handlers = []
        self.reset_handlers = []
        self.windows = {}
        self.modified = 0

    def add_menu_action(self, path, callback):
        self.menu_actions.append((path, callback))

    def register_save_handler(self, callback):
        self.save_handlers.append(callback)

    def register_load_handler(self, callback):
        self.load_handlers.append(callback)

    def register_document_reset_handler(self, callback):
        self.reset_handlers.append(callback)

    def register_window(self, window_id, window):
        self.windows[window_id] = window

    def get_window(self, window_id):
        return self.windows.get(window_id)

    def get_main_window(self):
        return self.main_window

    def mark_project_modified(self):
        self.modified += 1


@pytest.fixture
def context():
    original = dict(plugin.current_settings)
    ctx = FakeContext()
    plugin.initialize(ctx)
    yield ctx
    plugin._context = None
    plugin._dialog_opened = False
    plugin.current_settings.clear()
    plugin.current_settings.update(original)


# -- metadata --------------------------------------------------------------


def test_plugin_metadata():
    assert plugin.PLUGIN_NAME == "Slab Builder"
    assert plugin.PLUGIN_VERSION == "0.4.0"
    assert plugin.PLUGIN_AUTHOR == "HiroYokoyama"
    assert plugin.PLUGIN_DEPENDENCIES == ["numpy", "pyvista", "rdkit"]
    assert plugin.PLUGIN_TAGS == ["Structure", "Utility"]
    assert plugin.PLUGIN_DESCRIPTION.strip()


def test_plugin_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin.PLUGIN_VERSION)


def test_supported_version_range():
    assert plugin.PLUGIN_SUPPORTED_MOLEDITPY_VERSION == ">=4.0.0, <5.0.0"


def test_default_settings_shape():
    settings = plugin.get_default_settings()
    for key in ("source", "miller", "layers", "vacuum", "shift", "supercell"):
        assert key in settings


def test_module_exposes_run_for_the_plugins_menu():
    """run() is what puts the plugin in the host's Plugins menu (manual 7.1).

    It does not duplicate the entry initialize() registers, because that one
    lands in the Structure menu instead.
    """
    assert callable(plugin.run)


def test_module_has_no_autorun_attribute():
    """autorun() executes at startup; this plugin has nothing to do there."""
    assert not hasattr(plugin, "autorun")


# -- registration ----------------------------------------------------------


def test_initialize_registers_one_menu_action(context):
    assert [path for path, _ in context.menu_actions] == ["Structure/Slab Builder..."]


def test_initialize_registers_persistence(context):
    assert len(context.save_handlers) == 1
    assert len(context.load_handlers) == 1
    assert len(context.reset_handlers) == 1


def test_save_handler_is_silent_until_the_dialog_opens(context):
    assert context.save_handlers[0]() == {}


def test_save_handler_emits_settings_after_use(context):
    plugin._dialog_opened = True
    plugin.current_settings["layers"] = 9
    assert context.save_handlers[0]()["settings"]["layers"] == 9


def test_load_handler_updates_settings(context):
    context.load_handlers[0]({"settings": {"vacuum": 22.0}})
    assert plugin.current_settings["vacuum"] == 22.0


def test_load_handler_ignores_junk(context):
    before = dict(plugin.current_settings)
    context.load_handlers[0](None)
    context.load_handlers[0]({})
    context.load_handlers[0]({"settings": "nope"})
    assert plugin.current_settings == before


def test_reset_handler_restores_defaults(context):
    plugin._dialog_opened = True
    plugin.current_settings["layers"] = 99
    context.reset_handlers[0]()
    assert plugin.current_settings["layers"] == plugin.get_default_settings()["layers"]
    assert plugin._dialog_opened is False


def test_reset_handler_leaves_an_open_dialog_alone(context):
    class _Dialog:
        def isVisible(self):
            return True

    context.windows[plugin.WINDOW_ID] = _Dialog()
    plugin.current_settings["layers"] = 99
    context.reset_handlers[0]()
    assert plugin.current_settings["layers"] == 99


def test_load_handler_pushes_into_an_open_dialog(context):
    applied = {}

    class _Dialog:
        def apply_settings(self, settings):
            applied.update(settings)

    context.windows[plugin.WINDOW_ID] = _Dialog()
    context.load_handlers[0]({"settings": {"vacuum": 18.0}})
    assert applied["vacuum"] == 18.0


def test_load_handler_survives_a_broken_dialog(context):
    class _Dialog:
        def apply_settings(self, settings):
            raise RuntimeError("wrapped C/C++ object deleted")

    context.windows[plugin.WINDOW_ID] = _Dialog()
    context.load_handlers[0]({"settings": {"vacuum": 18.0}})
    assert plugin.current_settings["vacuum"] == 18.0
