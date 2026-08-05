# MoleditPy Slab Builder

A [MoleditPy](https://github.com/HiroYokoyama/python_molecular_editor) plugin that
cuts a **surface slab** from a bulk crystal and writes it back out as a CIF, ready
for any periodic DFT input generator.

## What it does

- **Bulk from two sources**
  - a `.cif` file loaded from disk (asymmetric unit expanded with the CIF's own
    symmetry operations)
  - the structure already open in the **CIF Viewer** plugin panel
- **Any (hkl) surface** — the surface basis is built from the Miller indices, so
  a/b lie in the surface plane and c stacks it. Hexagonal Miller-Bravais indices
  `(hkil)` are accepted and folded to `(hkl)` (i is fixed at −(h+k))
- **Layers and vacuum** — repeat the surface cell, then add vacuum along the
  surface normal, split evenly across both faces
- **Termination** — a shift slides the cut window through the bulk cell to expose
  a different plane. The window keeps a constant thickness, so the atom count
  never changes as you scan terminations
- **c along the surface normal** (default) so the cell is orthogonal in the
  vacuum direction, or keep the original stacking vector
- **Supercell** — a/b/c repeats of the finished slab
- **CIF output** — save or copy a P1 CIF; the geometry round-trips through the
  reader exactly

## Verification

The construction is checked against known geometry rather than assumed: for a
simple-cubic lattice the (001), (110) and (111) surfaces come out with areas
a², a²√2 and a²√3 and interlayer spacings a, a/√2 and a/√3, with the c axis
parallel to the (hkl) reciprocal vector in every case.

## Install

Plugin Manager → install from the MoleditPy plugin registry, or drop the
`slab_builder` folder into your MoleditPy plugins directory.

Requires `numpy` (already a MoleditPy dependency) — the surface construction is
plain linear algebra, with no ASE or pymatgen needed. `pymatgen` is used only if
a CIF Viewer structure holds nothing but the asymmetric unit; reading a `.cif`
file directly never needs it.

## Use

**Structure → Slab Builder...**

Load a bulk structure, set the Miller indices, layers and vacuum, check the
summary (atom count, cell, surface area, slab thickness), then **Save CIF...**.
Feed that CIF to the VASP, Quantum ESPRESSO or CP2K input generator plugins.

## Shared module

`cell_model.py` is shared byte-for-byte with the periodic input generator
plugins and carries its own `SHARED_MODULE_NAME` / `SHARED_MODULE_VERSION`,
independent of `PLUGIN_VERSION`: change it, bump its version, copy it to the
sibling plugins, and update the pin in each `tests/test_cell_model.py`.

The CIF reader, lattice construction and symmetry de-duplication are derived from
the [MoleditPy CIF Viewer](https://github.com/HiroYokoyama/moleditpy_cif_viewer)
plugin's parser. The surface basis follows the construction used by ASE's
`build.surface`, re-implemented on numpy.

## Tests

```bash
python -m pytest tests/ -v
```

## Licence

GNU General Public License v3.0 — see [LICENSE](LICENSE).
