"""Surface basis, input validation and preview regressions."""

from dataclasses import replace
from unittest.mock import MagicMock

import numpy as np
import pytest

from slab_builder import cell_model as cm
from slab_builder import slab as sl
from slab_builder.main_dialog import SlabBuilderDialog, default_settings
from shared_fixtures import CUBIC_CIF


@pytest.mark.parametrize("indices", [(2, 2, 0), (6, 9, 3), (-2, -2, 0), (0, 0, -3)])
def test_equivalent_indices_have_a_primitive_oriented_basis(indices):
    lattice = np.eye(3) * 4
    matrix = sl.surface_transformation(lattice, indices)
    assert np.linalg.det(matrix) == pytest.approx(1)
    normal = np.cross(*(matrix @ lattice)[:2])
    assert np.dot(normal, indices) > 0
    assert np.cross(normal, indices) == pytest.approx(np.zeros(3))


def test_high_index_basis_uses_one_coordinate_transform_per_site(monkeypatch):
    cell = cm.parse_cif(CUBIC_CIF)
    transform = sl.surface_transformation(cell.lattice, (9, 8, 7))
    original = sl.wrap_fractional
    calls = []

    def wrap(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(sl, "wrap_fractional", wrap)
    tiled = sl._retile(cell, transform)
    assert len(calls) == len(cell.atoms)
    assert len(tiled.atoms) == len(cell.atoms)


def test_coincident_partial_sites_are_preserved():
    cell = cm.parse_cif(CUBIC_CIF)
    first = replace(cell.atoms[0], occupancy=0.5)
    second = replace(first, label="Ni1", element="Ni")
    cell = replace(cell, atoms=(first, second))
    built = sl.build_slab(cell, layers=2)
    assert len(built.atoms) == 4
    assert [a.element for a in built.atoms].count("Ni") == 2
    assert all(a.occupancy == 0.5 for a in built.atoms)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vacuum": np.nan},
        {"vacuum": -1},
        {"shift": np.inf},
        {"layers": 1.5},
        {"layers": np.inf},
    ],
)
def test_invalid_build_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        sl.build_slab(cm.parse_cif(CUBIC_CIF), **kwargs)


def test_oversize_slab_is_rejected_before_stacking(monkeypatch):
    stack = MagicMock()
    monkeypatch.setattr(sl, "make_supercell", stack)
    with pytest.raises(ValueError, match="atom limit"):
        sl.build_slab(cm.parse_cif(CUBIC_CIF), layers=100_000)
    stack.assert_not_called()


@pytest.mark.parametrize("indices", [(0.5, 0, 1), (np.nan, 0, 1)])
def test_noninteger_miller_indices_are_rejected(indices):
    with pytest.raises(ValueError, match="finite integers"):
        sl.normalize_miller(indices)


def test_termination_change_refreshes_preview(qapp, monkeypatch):
    from slab_builder import main_dialog

    window = SlabBuilderDialog(persistent_settings=default_settings())
    draw = MagicMock(return_value=[])
    monkeypatch.setattr(main_dialog.cell_preview, "show_cell", draw)
    bulk = cm.parse_cif(CUBIC_CIF)
    window.auto_preview(sl.build_slab(bulk, layers=2))
    window.auto_preview(sl.build_slab(bulk, layers=2, shift=0.25))
    assert draw.call_count == 2
    window.clear_3d_preview()
    window.auto_preview(sl.build_slab(bulk, layers=2, shift=0.25))
    assert draw.call_count == 3
    window.close()
