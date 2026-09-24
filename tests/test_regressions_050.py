"""Regressions fixed in 0.5.0; each test fails on 0.4.4."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slab_builder import cell_model as cm  # noqa: E402
from slab_builder import slab as sl  # noqa: E402


def _fcc(a=3.61):
    lengths, angles = (a, a, a), (90.0, 90.0, 90.0)
    lattice = cm.cell_vectors(lengths, angles)
    atoms = tuple(
        cm.CellAtom(f"Cu{i}", "Cu", np.array(f), np.array(f) @ lattice)
        for i, f in enumerate([[0, 0, 0], [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]])
    )
    return cm.Cell("cu", lengths, angles, lattice, atoms, source="cif")


def test_orthogonal_slab_keeps_atoms_inside_the_ab_faces():
    """Straightening c slid the upper layers of a (111) slab out past a and b."""
    slab = sl.build_slab(_fcc(), (1, 1, 1), layers=4, vacuum=10.0, orthogonal_c=True)
    fract = np.array([atom.fract for atom in slab.atoms])
    assert fract[:, :2].min() >= -1e-9
    assert fract[:, :2].max() < 1.0


def test_folding_moves_atoms_by_whole_lattice_vectors_only():
    slab = sl.build_slab(_fcc(), (1, 1, 1), layers=4, vacuum=10.0, orthogonal_c=True)
    lattice = np.asarray(slab.lattice)
    for atom in slab.atoms:
        assert np.allclose(np.asarray(atom.fract) @ lattice, atom.cart, atol=1e-8)
    assert cm.looks_like_slab(slab)
    assert not cm.close_contacts(slab)
