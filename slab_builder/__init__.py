"""Surface Slab Builder plugin for MoleditPy."""

import logging
import os

PLUGIN_NAME = "Slab Builder"
PLUGIN_VERSION = "0.2.2"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Cut a surface slab from a bulk crystal: (hkl) Miller indices, layer count, "
    "vacuum thickness and termination, written back out as a CIF for any "
    "periodic input generator."
)
PLUGIN_CATEGORY = "Structure"
PLUGIN_TAGS = ["Structure", "Utility"]
PLUGIN_DEPENDENCIES = ["numpy", "pyvista", "rdkit"]
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=4.0.0, <5.0.0"

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
WINDOW_ID = "slab_builder_dialog"

_context = None
_dialog_opened = False


def get_default_settings():
    from .main_dialog import default_settings

    return default_settings()


current_settings = get_default_settings()


def _open_dialog(mw):
    """Open the dialog."""
    global _dialog_opened

    if _context is not None:
        mw = _context.get_main_window()

    from .main_dialog import SlabBuilderDialog

    if _context is not None:
        existing = _context.get_window(WINDOW_ID)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

    def _mark_modified():
        if _context is not None:
            try:
                _context.mark_project_modified()
            except Exception:  # pragma: no cover - host API guard
                pass

    def _get_cif_viewer():
        from .cif_viewer_link import find_cif_viewer_widget

        return find_cif_viewer_widget(mw)

    _dialog_opened = True
    dlg = SlabBuilderDialog(
        parent=mw,
        persistent_settings=current_settings,
        get_cif_viewer=_get_cif_viewer,
        mark_modified=_mark_modified,
        context=_context,
    )
    if _context is not None:
        _context.register_window(WINDOW_ID, dlg)
    dlg.show()



def run(main_window):
    """Entry point for the host's automatic Plugins-menu item (manual 7.1).

    Safe alongside the entry registered in initialize(): that one goes to
    the Structure menu, while a module exposing ``run`` is listed under Plugins, so the
    two do not collide.
    """
    _open_dialog(main_window)

def initialize(context):
    global _context
    _context = context

    def show_dialog():
        _open_dialog(context.get_main_window())

    context.add_menu_action("Structure/Slab Builder...", show_dialog)

    def save_state():
        if not _dialog_opened:
            return {}
        return {"settings": dict(current_settings)}

    def load_state(data):
        if not isinstance(data, dict):
            return
        saved = data.get("settings")
        if isinstance(saved, dict):
            current_settings.update(saved)
            dlg = context.get_window(WINDOW_ID)
            if dlg is not None:
                try:
                    dlg.apply_settings(current_settings)
                except Exception as exc:  # pragma: no cover - host API guard
                    logging.warning("%s: could not apply loaded state: %s", PLUGIN_NAME, exc)

    def handle_reset():
        global _dialog_opened
        dlg = context.get_window(WINDOW_ID)
        if dlg is not None and dlg.isVisible():
            # Leave an open dialog alone: the user may still be editing.
            return
        current_settings.clear()
        current_settings.update(get_default_settings())
        _dialog_opened = False

    context.register_save_handler(save_state)
    context.register_load_handler(load_state)
    context.register_document_reset_handler(handle_reset)
