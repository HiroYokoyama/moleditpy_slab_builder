import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slab_builder import cell_model as cm  # noqa: E402
from slab_builder import slab as sl  # noqa: E402
from slab_builder.main_dialog import (  # noqa: E402
    SOURCE_CIF,
    SOURCE_VIEWER,
    SlabBuilderDialog,
    default_settings,
)

from test_cell_model import CUBIC_CIF  # noqa: E402


def _viewer_structure():
    lengths, angles = (4.0, 4.0, 4.0), (90.0, 90.0, 90.0)
    lattice = cm.cell_vectors(lengths, angles)
    atoms = [
        types.SimpleNamespace(
            label="Fe1", element="Fe", fract=np.zeros(3), occupancy=1.0
        )
    ]
    return types.SimpleNamespace(
        name="bulk",
        cell_lengths=lengths,
        cell_angles=angles,
        lattice=lattice,
        atoms=atoms,
        space_group="P 1",
        is_asymmetric_unit_only=False,
    )


@pytest.fixture
def dialog(qapp, tmp_path):
    cif = tmp_path / "bulk.cif"
    cif.write_text(CUBIC_CIF, encoding="utf-8")
    viewer = types.SimpleNamespace(structure=_viewer_structure())
    dlg = SlabBuilderDialog(
        persistent_settings=default_settings(), get_cif_viewer=lambda: viewer
    )
    dlg.cif_edit.setText(str(cif))
    yield dlg
    dlg.deleteLater()


def test_dialog_builds_a_slab_from_a_cif(dialog):
    assert dialog._slab is not None
    assert dialog._slab.source == "slab"
    assert dialog.save_button.isEnabled()
    assert "data_" in dialog.preview.toPlainText()


def test_preview_is_valid_cif(dialog):
    reparsed = cm.parse_cif(dialog.preview.toPlainText(), expand=False)
    assert len(reparsed.atoms) == len(dialog._slab.atoms)


def test_summary_reports_area_and_thickness(dialog):
    text = dialog.summary_label.text()
    assert "surface area" in text
    assert "slab thickness" in text


def test_layers_change_the_atom_count(dialog):
    before = len(dialog._slab.atoms)
    dialog.layers_spin.setValue(dialog.layers_spin.value() + 2)
    assert len(dialog._slab.atoms) > before


def test_vacuum_changes_the_c_axis(dialog):
    before = dialog._slab.lengths[2]
    dialog.vacuum_spin.setValue(dialog.vacuum_spin.value() + 10.0)
    assert dialog._slab.lengths[2] == pytest.approx(before + 10.0)


def test_supercell_multiplies_the_slab(dialog):
    before = len(dialog._slab.atoms)
    dialog.repeat_spins[0].setValue(2)
    assert len(dialog._slab.atoms) == 2 * before


def test_miller_indices_change_the_surface(dialog):
    area_001 = sl.surface_area(dialog._slab)
    dialog.miller_spins[0].setValue(1)  # (1 0 1)
    assert sl.surface_area(dialog._slab) != pytest.approx(area_001)


def test_four_index_mode_shows_i_and_folds_to_three(dialog):
    dialog.four_index_check.setChecked(True)
    dialog.miller_spins[0].setValue(1)
    dialog.miller_spins[1].setValue(0)
    assert dialog.i_label.text() == "i: -1"
    assert dialog.miller() == (1, 0, 1)


def test_three_index_mode_ignores_i(dialog):
    dialog.four_index_check.setChecked(False)
    dialog.miller_spins[0].setValue(1)
    assert dialog.miller() == (1, 0, 1)


def test_viewer_source(dialog):
    dialog.source_combo.setCurrentText(SOURCE_VIEWER)
    assert dialog._slab is not None
    assert dialog._slab.source == "slab"


def test_viewer_source_without_a_panel(qapp):
    dlg = SlabBuilderDialog(persistent_settings={}, get_cif_viewer=lambda: None)
    dlg.source_combo.setCurrentText(SOURCE_VIEWER)
    assert dlg._slab is None
    assert "not open" in dlg.preview.toPlainText()
    assert not dlg.save_button.isEnabled()
    dlg.deleteLater()


def test_missing_cif_path_is_reported(qapp):
    dlg = SlabBuilderDialog(persistent_settings={})
    assert "Choose a CIF file" in dlg.preview.toPlainText()
    dlg.deleteLater()


def test_missing_cif_file_is_reported(dialog, tmp_path):
    dialog.cif_edit.setText(str(tmp_path / "nope.cif"))
    assert "not found" in dialog.preview.toPlainText()
    assert dialog._slab is None


def test_settings_roundtrip(dialog, tmp_path):
    settings = {
        "source": SOURCE_CIF,
        "cif_path": dialog.cif_edit.text(),
        "expand_symmetry": False,
        "miller": [1, 1, 0],
        "miller_four_index": False,
        "layers": 4,
        "vacuum": 12.5,
        "shift": 0.25,
        "orthogonal_c": False,
        "supercell": [2, 1, 1],
    }
    dialog.apply_settings(settings)
    assert dialog.read_settings() == settings


def test_settings_reach_the_persistent_dict(dialog):
    dialog.layers_spin.setValue(3)
    assert dialog.persistent_settings["layers"] == 3


def test_marks_the_project_modified(qapp, tmp_path):
    cif = tmp_path / "bulk.cif"
    cif.write_text(CUBIC_CIF, encoding="utf-8")
    seen = []
    dlg = SlabBuilderDialog(persistent_settings={}, mark_modified=lambda: seen.append(1))
    dlg.cif_edit.setText(str(cif))
    assert seen
    dlg.deleteLater()


def test_save_writes_a_cif(dialog, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    target = tmp_path / "slab.cif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dialog.save_cif()
    text = target.read_text(encoding="utf-8")
    assert text.startswith("data_")
    assert "\r" not in text
    assert len(cm.parse_cif(text, expand=False).atoms) == len(dialog._slab.atoms)


def test_save_is_cancellable(dialog, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    before = sorted(path.name for path in tmp_path.iterdir())
    dialog.save_cif()
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_save_without_a_slab_warns(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a))
    dlg = SlabBuilderDialog(persistent_settings={})
    dlg.save_cif()
    assert seen
    dlg.deleteLater()


def test_copy_cif(dialog, qapp):
    dialog.copy_cif()
    assert "data_" in qapp.clipboard().text()


def test_source_switch_toggles_the_widgets(dialog):
    dialog.source_combo.setCurrentText(SOURCE_VIEWER)
    assert dialog.viewer_widget.isVisibleTo(dialog)
    assert not dialog.cif_widget.isVisibleTo(dialog)
    dialog.source_combo.setCurrentText(SOURCE_CIF)
    assert dialog.cif_widget.isVisibleTo(dialog)
