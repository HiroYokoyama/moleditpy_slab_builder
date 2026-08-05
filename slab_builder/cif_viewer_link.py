"""Locate the CIF Viewer plugin's panel so its structure can be reused.

Plugin windows are namespaced per plugin, so ``context.get_window()`` cannot
reach another plugin's dock.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QWidget


def find_cif_viewer_widget(main_window):
    """Locate the CIF Viewer plugin's panel widget, or None.

    Plugin windows are namespaced per plugin, so ``context.get_window()`` cannot
    reach another plugin's dock — go through the plugin manager's registry and
    fall back to a widget scan.
    """
    if main_window is None:
        return None

    def _holder(window):
        if window is None:
            return None
        if getattr(window, "structure", None) is not None:
            return window
        inner = window.widget() if hasattr(window, "widget") else None
        if inner is not None and hasattr(inner, "structure"):
            return inner
        return None

    try:
        registry = getattr(getattr(main_window, "plugin_manager", None), "plugin_windows", None)
        if isinstance(registry, dict):
            for plugin_name, windows in registry.items():
                if not isinstance(windows, dict):
                    continue
                for window_id, window in windows.items():
                    key = f"{plugin_name} {window_id}".lower()
                    if "cif" not in key or "viewer" not in key:
                        continue
                    holder = _holder(window)
                    if holder is not None:
                        return holder
    except Exception as exc:  # pragma: no cover - host internals guard
        logging.debug("CIF Viewer lookup via the plugin manager failed: %s", exc)

    try:
        for child in main_window.findChildren(QWidget):
            if type(child).__name__ == "CifViewerWidget" and hasattr(child, "structure"):
                return child
    except Exception as exc:  # pragma: no cover - host internals guard
        logging.debug("CIF Viewer widget scan failed: %s", exc)
    return None
