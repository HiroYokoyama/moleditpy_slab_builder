"""Surface slab construction: (hkl) basis, layer stacking and vacuum.

The surface basis follows the construction used by ASE's ``build.surface``,
re-implemented here on numpy so the plugin needs no extra dependency.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

import numpy as np

from .cell_model import (
    Cell,
    CellAtom,
    cartesian_to_fractional,
    fractional_to_cartesian,
    lattice_parameters,
    make_supercell,
    wrap_fractional,
)


def normalize_miller(indices: Sequence[int]) -> Tuple[int, int, int]:
    """Accept 3-index (hkl) or hexagonal 4-index (hkil) Miller-Bravais input.

    The redundant third index of (hkil) satisfies i = -(h+k) and is dropped, so
    (1 0 -1 0) becomes (1 0 0).
    """
    values = [int(value) for value in indices]
    if len(values) == 4:
        h, k, i, l = values
        if i != -(h + k):
            raise ValueError(
                f"Invalid Miller-Bravais indices: i must equal -(h+k), got i={i} "
                f"for h={h}, k={k}."
            )
        values = [h, k, l]
    if len(values) != 3:
        raise ValueError("Miller indices must have three or four components.")
    if values == [0, 0, 0]:
        raise ValueError("Miller indices cannot all be zero.")
    return tuple(values)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# surface slabs
# --------------------------------------------------------------------------


def _ext_gcd(a: int, b: int) -> Tuple[int, int]:
    """Bezout coefficients (x, y) with a*x + b*y = gcd(a, b)."""
    if b == 0:
        return 1, 0
    if a % b == 0:
        return 0, 1
    x, y = _ext_gcd(b, a % b)
    return y, x - y * (a // b)


def surface_transformation(lattice: np.ndarray, miller: Sequence[int]) -> np.ndarray:
    """Integer matrix T whose rows span the (hkl) surface cell.

    Rows 0 and 1 lie in the (hkl) plane and row 2 crosses it, so ``T @ lattice``
    is a cell whose c axis stacks the surface.  Same construction as ASE's
    ``build.surface``.
    """
    h, k, l = (int(value) for value in miller)
    if (h, k, l) == (0, 0, 0):
        raise ValueError("Miller indices cannot all be zero.")

    h0, k0, l0 = h == 0, k == 0, l == 0
    if (h0 and k0) or (h0 and l0) or (k0 and l0):
        if not h0:
            rows = [(0, 1, 0), (0, 0, 1), (1, 0, 0)]
        elif not k0:
            rows = [(0, 0, 1), (1, 0, 0), (0, 1, 0)]
        else:
            rows = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        return np.array(rows, dtype=int)

    a1, a2, a3 = np.asarray(lattice, dtype=float)
    p, q = _ext_gcd(k, l)

    # Pick the p, q pair that makes the first two vectors as short as possible.
    k1 = np.dot(p * (k * a1 - h * a2) + q * (l * a1 - h * a3), l * a2 - k * a3)
    k2 = np.dot(l * (k * a1 - h * a2) - k * (l * a1 - h * a3), l * a2 - k * a3)
    if abs(k2) > 1e-10:
        shift = -int(round(k1 / k2))
        p, q = p + shift * l, q - shift * k

    a, b = _ext_gcd(p * k + q * l, h)
    divisor = math.gcd(l, k) or 1
    return np.array(
        [
            (p * k + q * l, -p * h, -q * h),
            (0, l // divisor, -k // divisor),
            (b, a * p, a * q),
        ],
        dtype=int,
    )


def _retile(cell: Cell, transformation: np.ndarray) -> Cell:
    """Re-express a cell on a new integer basis, refilling it with atoms."""
    transformation = np.asarray(transformation, dtype=int)
    multiplicity = int(round(abs(np.linalg.det(transformation))))
    if multiplicity == 0:
        raise ValueError("The surface basis is singular for this cell.")

    lattice = transformation @ np.asarray(cell.lattice, dtype=float)
    inverse = np.linalg.inv(transformation.astype(float))
    span = int(np.abs(transformation).sum()) + 1

    atoms: List[CellAtom] = []
    seen: List[np.ndarray] = []
    for atom in cell.atoms:
        base = np.asarray(atom.fract, dtype=float)
        for ia in range(-span, span + 1):
            for ib in range(-span, span + 1):
                for ic in range(-span, span + 1):
                    fract = (base + np.array([ia, ib, ic], dtype=float)) @ inverse
                    if np.any(fract < -1e-8) or np.any(fract > 1.0 - 1e-8):
                        continue
                    fract = wrap_fractional(fract)
                    if any(
                        np.allclose(fract, previous, atol=1e-6) for previous in seen
                    ):
                        continue
                    seen.append(fract)
                    atoms.append(
                        CellAtom(
                            label=atom.label,
                            element=atom.element,
                            fract=fract,
                            cart=fractional_to_cartesian(fract, lattice),
                            occupancy=atom.occupancy,
                        )
                    )

    expected = multiplicity * len(cell.atoms)
    if len(atoms) != expected:
        raise ValueError(
            f"Surface cell filling produced {len(atoms)} atoms, expected {expected}. "
            "The structure may have overlapping sites."
        )

    lengths, angles = lattice_parameters(lattice)
    return Cell(
        name=cell.name,
        lengths=lengths,
        angles=angles,
        lattice=lattice,
        atoms=tuple(atoms),
        space_group=None,
        source=cell.source,
    )


def build_slab(
    cell: Cell,
    miller: Sequence[int] = (0, 0, 1),
    layers: int = 3,
    vacuum: float = 15.0,
    shift: float = 0.0,
    orthogonal_c: bool = True,
) -> Cell:
    """Cut an (hkl) surface slab with vacuum along the surface normal.

    ``layers`` counts repeats of the surface unit cell.  ``shift`` (0-1) slides
    the cut window through the bulk in units of one surface cell, which is what
    changes the termination: the window keeps a constant thickness, so the atom
    count is unchanged while a different plane is exposed.  ``orthogonal_c``
    replaces the stacking vector with the surface normal, which is what a slab
    calculation normally wants.
    """
    layers = max(1, int(layers))
    vacuum = max(0.0, float(vacuum))
    shift = float(shift) % 1.0

    surface = _retile(cell, surface_transformation(cell.lattice, miller))

    # One extra repeat gives the cut window room to slide without running out
    # of atoms at the top.
    stacked = make_supercell(surface, [1, 1, layers + 1])

    lattice = np.array(surface.lattice, dtype=float)
    normal = np.cross(lattice[0], lattice[1])
    norm = np.linalg.norm(normal)
    if norm < 1e-12:
        raise ValueError("The surface cell is degenerate (a and b are parallel).")
    normal = normal / norm
    if np.dot(lattice[2], normal) < 0:
        normal = -normal

    unit_thickness = abs(float(np.dot(lattice[2], normal)))
    window = layers * unit_thickness
    lower = shift * unit_thickness

    kept = []
    for atom in stacked.atoms:
        height = float(np.dot(np.asarray(atom.cart, dtype=float), normal))
        if lower - 1e-9 <= height < lower + window - 1e-9:
            kept.append((atom, np.asarray(atom.cart, dtype=float)))

    expected = layers * len(surface.atoms)
    if len(kept) != expected:
        raise ValueError(
            f"The slab cut kept {len(kept)} atoms, expected {expected}. Try a "
            "slightly different termination shift."
        )

    slab_lattice = np.array(surface.lattice, dtype=float)
    if orthogonal_c:
        slab_lattice[2] = normal * (window + vacuum)
    else:
        direction = slab_lattice[2] / np.linalg.norm(slab_lattice[2])
        slab_lattice[2] = direction * (window + vacuum) / max(
            abs(float(np.dot(direction, normal))), 1e-12
        )

    heights = [float(np.dot(position, normal)) for _, position in kept]
    offset = normal * ((window + vacuum) / 2.0 - (max(heights) + min(heights)) / 2.0)

    atoms = []
    for atom, position in kept:
        moved = position + offset
        atoms.append(
            CellAtom(
                label=atom.label,
                element=atom.element,
                fract=cartesian_to_fractional(moved, slab_lattice),
                cart=moved,
                occupancy=atom.occupancy,
            )
        )

    lengths, angles = lattice_parameters(slab_lattice)
    return Cell(
        name=f"{cell.name}_{''.join(str(int(index)) for index in miller)}",
        lengths=lengths,
        angles=angles,
        lattice=slab_lattice,
        atoms=tuple(atoms),
        space_group=None,
        source="slab",
    )


def surface_area(cell: Cell) -> float:
    """Area of the a-b face in A^2 — the surface area of a slab cell."""
    lattice = np.asarray(cell.lattice, dtype=float)
    return float(np.linalg.norm(np.cross(lattice[0], lattice[1])))


def slab_thickness(cell: Cell) -> float:
    """Atom-to-atom extent along the surface normal, i.e. excluding the vacuum."""
    lattice = np.asarray(cell.lattice, dtype=float)
    normal = np.cross(lattice[0], lattice[1])
    norm = np.linalg.norm(normal)
    if norm < 1e-12 or not cell.atoms:
        return 0.0
    normal = normal / norm
    heights = [float(np.dot(np.asarray(atom.cart, dtype=float), normal)) for atom in cell.atoms]
    return max(heights) - min(heights)
