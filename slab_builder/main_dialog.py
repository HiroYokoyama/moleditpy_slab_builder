"""Slab builder dialog."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import slab as slab_module
from .cell_model import (
    cell_from_viewer_structure,
    make_supercell,
    parse_cif_file,
    write_cif,
)

SOURCE_CIF = "CIF file"
SOURCE_VIEWER = "CIF Viewer panel (currently loaded)"
SOURCES = (SOURCE_CIF, SOURCE_VIEWER)


def default_settings() -> dict:
    return {
        "source": SOURCE_CIF,
        "cif_path": "",
        "expand_symmetry": True,
        "miller": [0, 0, 1],
        "miller_four_index": False,
        "layers": 6,
        "vacuum": 15.0,
        "shift": 0.0,
        "orthogonal_c": True,
        "supercell": [1, 1, 1],
    }


class SlabBuilderDialog(QDialog):
    def __init__(
        self,
        parent=None,
        persistent_settings=None,
        get_cif_viewer=None,
        mark_modified=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Slab Builder")
        self.resize(860, 700)

        self.persistent_settings = persistent_settings if persistent_settings is not None else {}
        self.get_cif_viewer = get_cif_viewer
        self.mark_modified = mark_modified
        self._updating = False
        self._slab = None

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_source_box())
        layout.addWidget(self._build_slab_box())
        layout.addWidget(self._build_supercell_box())

        self.summary_label = QLabel("No structure yet.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary_label)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Courier New", 9))
        layout.addWidget(self.preview, 1)

        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("Save CIF...", QDialogButtonBox.ButtonRole.AcceptRole)
        self.copy_button = buttons.addButton("Copy CIF", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.save_button.clicked.connect(self.save_cif)
        self.copy_button.clicked.connect(self.copy_cif)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self.apply_settings(self.persistent_settings)
        self.update_preview()

    # -- widgets ----------------------------------------------------------

    def _build_source_box(self) -> QGroupBox:
        box = QGroupBox("Bulk structure")
        form = QFormLayout(box)

        self.source_combo = QComboBox()
        self.source_combo.addItems(list(SOURCES))
        form.addRow("Source:", self.source_combo)

        self.cif_widget = QWidget()
        row = QHBoxLayout(self.cif_widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.cif_edit = QLineEdit()
        self.cif_edit.setPlaceholderText("Path to a .cif file")
        load_button = QPushButton("Load CIF...")
        load_button.clicked.connect(self._browse_cif)
        row.addWidget(self.cif_edit, 1)
        row.addWidget(load_button)
        form.addRow("File:", self.cif_widget)

        self.viewer_widget = QWidget()
        viewer_row = QHBoxLayout(self.viewer_widget)
        viewer_row.setContentsMargins(0, 0, 0, 0)
        self.viewer_label = QLabel("Uses the structure currently open in the CIF Viewer panel.")
        self.viewer_label.setWordWrap(True)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self.update_preview)
        viewer_row.addWidget(self.viewer_label, 1)
        viewer_row.addWidget(reload_button)
        form.addRow("", self.viewer_widget)

        self.expand_check = QCheckBox("Expand the asymmetric unit with the symmetry operations")
        self.expand_check.setChecked(True)
        form.addRow("", self.expand_check)

        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        self.cif_edit.textChanged.connect(self.update_preview)
        self.expand_check.toggled.connect(self.update_preview)
        return box

    def _build_slab_box(self) -> QGroupBox:
        box = QGroupBox("Surface")
        form = QFormLayout(box)

        miller_widget = QWidget()
        miller_layout = QHBoxLayout(miller_widget)
        miller_layout.setContentsMargins(0, 0, 0, 0)
        self.miller_spins = []
        for label in ("h", "k", "l"):
            spin = QSpinBox()
            spin.setRange(-9, 9)
            spin.setValue(1 if label == "l" else 0)
            miller_layout.addWidget(QLabel(f"{label}:"))
            miller_layout.addWidget(spin)
            self.miller_spins.append(spin)
        self.four_index_check = QCheckBox("(hkil)")
        self.four_index_check.setToolTip(
            "Hexagonal Miller-Bravais indices. i is fixed at -(h+k) and dropped, "
            "so (1 0 -1 0) is the same surface as (1 0 0)."
        )
        miller_layout.addWidget(self.four_index_check)
        self.i_label = QLabel("i: 0")
        miller_layout.addWidget(self.i_label)
        miller_layout.addStretch(1)
        form.addRow("Miller indices:", miller_widget)

        self.layers_spin = QSpinBox()
        self.layers_spin.setRange(1, 100)
        self.layers_spin.setValue(6)
        form.addRow("Layers:", self.layers_spin)

        self.vacuum_spin = QDoubleSpinBox()
        self.vacuum_spin.setRange(0.0, 100.0)
        self.vacuum_spin.setSingleStep(1.0)
        self.vacuum_spin.setValue(15.0)
        self.vacuum_spin.setSuffix(" A")
        form.addRow("Vacuum:", self.vacuum_spin)

        self.shift_spin = QDoubleSpinBox()
        self.shift_spin.setRange(0.0, 1.0)
        self.shift_spin.setSingleStep(0.05)
        self.shift_spin.setDecimals(3)
        self.shift_spin.setToolTip(
            "Slides the cut window through the bulk cell to expose a different termination."
        )
        form.addRow("Termination shift:", self.shift_spin)

        self.orthogonal_check = QCheckBox("Put c along the surface normal")
        self.orthogonal_check.setChecked(True)
        form.addRow("", self.orthogonal_check)

        for spin in self.miller_spins:
            spin.valueChanged.connect(self._on_miller_changed)
        self.four_index_check.toggled.connect(self._on_miller_changed)
        for widget in (self.layers_spin, self.vacuum_spin, self.shift_spin):
            widget.valueChanged.connect(self.update_preview)
        self.orthogonal_check.toggled.connect(self.update_preview)
        return box

    def _build_supercell_box(self) -> QGroupBox:
        box = QGroupBox("Supercell")
        grid = QGridLayout(box)
        self.repeat_spins = []
        for column, axis in enumerate("abc"):
            spin = QSpinBox()
            spin.setRange(1, 20)
            spin.setValue(1)
            grid.addWidget(QLabel(f"{axis}:"), 0, column * 2)
            grid.addWidget(spin, 0, column * 2 + 1)
            spin.valueChanged.connect(self.update_preview)
            self.repeat_spins.append(spin)
        return box

    # -- settings ---------------------------------------------------------

    def apply_settings(self, settings) -> None:
        settings = {**default_settings(), **(settings or {})}
        self._updating = True
        try:
            if settings.get("source") in SOURCES:
                self.source_combo.setCurrentText(settings["source"])
            self.cif_edit.setText(str(settings.get("cif_path", "") or ""))
            self.expand_check.setChecked(bool(settings.get("expand_symmetry", True)))
            for spin, value in zip(self.miller_spins, settings.get("miller") or [0, 0, 1]):
                spin.setValue(int(value))
            self.four_index_check.setChecked(bool(settings.get("miller_four_index", False)))
            self.layers_spin.setValue(max(1, int(settings.get("layers", 6))))
            self.vacuum_spin.setValue(float(settings.get("vacuum", 15.0)))
            self.shift_spin.setValue(float(settings.get("shift", 0.0)))
            self.orthogonal_check.setChecked(bool(settings.get("orthogonal_c", True)))
            for spin, value in zip(self.repeat_spins, settings.get("supercell") or [1, 1, 1]):
                spin.setValue(max(1, int(value)))
        finally:
            self._updating = False
        self._on_source_changed(self.source_combo.currentText())

    def read_settings(self) -> dict:
        return {
            "source": self.source_combo.currentText(),
            "cif_path": self.cif_edit.text(),
            "expand_symmetry": self.expand_check.isChecked(),
            "miller": [spin.value() for spin in self.miller_spins],
            "miller_four_index": self.four_index_check.isChecked(),
            "layers": self.layers_spin.value(),
            "vacuum": self.vacuum_spin.value(),
            "shift": self.shift_spin.value(),
            "orthogonal_c": self.orthogonal_check.isChecked(),
            "supercell": [spin.value() for spin in self.repeat_spins],
        }

    def miller(self):
        """The (hkl) triple, folding a hexagonal (hkil) entry down to three indices."""
        h, k, l = (spin.value() for spin in self.miller_spins)
        if self.four_index_check.isChecked():
            return slab_module.normalize_miller([h, k, -(h + k), l])
        return slab_module.normalize_miller([h, k, l])

    # -- building ---------------------------------------------------------

    def load_bulk(self):
        """The bulk cell for the current source. Raises ValueError on failure."""
        if self.source_combo.currentText() == SOURCE_VIEWER:
            dock = self.get_cif_viewer() if self.get_cif_viewer is not None else None
            if dock is None:
                raise ValueError(
                    "The CIF Viewer panel is not open. Open it from View > CIF Viewer "
                    "Panel, or choose the CIF file source."
                )
            return cell_from_viewer_structure(
                getattr(dock, "structure", None),
                expand_asymmetric=self.expand_check.isChecked(),
            )

        path = self.cif_edit.text().strip()
        if not path:
            raise ValueError("Choose a CIF file first.")
        if not os.path.isfile(path):
            raise ValueError(f"CIF file not found:\n{path}")
        return parse_cif_file(path, expand=self.expand_check.isChecked())

    def build_slab(self):
        bulk = self.load_bulk()
        built = slab_module.build_slab(
            bulk,
            miller=self.miller(),
            layers=self.layers_spin.value(),
            vacuum=self.vacuum_spin.value(),
            shift=self.shift_spin.value(),
            orthogonal_c=self.orthogonal_check.isChecked(),
        )
        return make_supercell(built, [spin.value() for spin in self.repeat_spins])

    def update_preview(self, *_args) -> None:
        if self._updating:
            return
        self.persistent_settings.update(self.read_settings())
        if self.mark_modified is not None:
            try:
                self.mark_modified()
            except Exception:  # pragma: no cover - host API guard
                pass

        try:
            self._slab = self.build_slab()
        except (ValueError, OSError) as exc:
            self._slab = None
            self.summary_label.setText(f"<b>{exc}</b>")
            self.preview.setPlainText(f"# {exc}")
            self.save_button.setEnabled(False)
            return

        self.summary_label.setText(self._describe(self._slab))
        self.preview.setPlainText(write_cif(self._slab))
        self.save_button.setEnabled(True)

    def _describe(self, cell) -> str:
        a, b, c = cell.lengths
        alpha, beta, gamma = cell.angles
        area = slab_module.surface_area(cell)
        return (
            f"{len(cell.atoms)} atoms<br>"
            f"a={a:.4f} b={b:.4f} c={c:.4f} A, "
            f"alpha={alpha:.2f} beta={beta:.2f} gamma={gamma:.2f} deg<br>"
            f"surface area = {area:.4f} A<sup>2</sup>, "
            f"slab thickness = {slab_module.slab_thickness(cell):.4f} A"
        )

    # -- output -----------------------------------------------------------

    def _browse_cif(self) -> None:  # pragma: no cover - file dialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CIF", self.cif_edit.text(), "CIF files (*.cif);;All files (*)"
        )
        if path:
            self.cif_edit.setText(path)

    def copy_cif(self) -> None:
        from PyQt6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.preview.toPlainText())

    def save_cif(self) -> None:
        if self._slab is None:
            QMessageBox.warning(self, "Slab Builder", "There is no valid slab to write.")
            return
        suggested = f"{self._slab.name}.cif"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the slab as CIF", suggested, "CIF files (*.cif);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(write_cif(self._slab))
        except OSError as exc:
            QMessageBox.critical(self, "Slab Builder", f"Could not write the file:\n{exc}")
            return
        QMessageBox.information(self, "Slab Builder", f"Wrote\n{os.path.abspath(path)}")

    # -- internals --------------------------------------------------------

    def _on_source_changed(self, text: str) -> None:
        self.cif_widget.setVisible(text == SOURCE_CIF)
        self.viewer_widget.setVisible(text == SOURCE_VIEWER)
        self.update_preview()

    def _on_miller_changed(self, *_args) -> None:
        h, k = self.miller_spins[0].value(), self.miller_spins[1].value()
        self.i_label.setText(f"i: {-(h + k)}")
        self.i_label.setVisible(self.four_index_check.isChecked())
        self.update_preview()
