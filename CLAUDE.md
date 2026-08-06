# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

`moleditpy_slab_builder` — a MoleditPy plugin that cuts a surface slab from a
bulk crystal: Miller (or Miller-Bravais) indices, layer count, vacuum thickness
and termination shift, written out as a P1 CIF the input generators can read.
Entry point `slab_builder/__init__.py`, dialog in `main_dialog.py`, the surface
mathematics in `slab.py`.

It builds structures only. Parsing calculation output is deliberately out of
scope — do not add it.

## Shared modules — read this before editing

Some files in `slab_builder/` are **not owned by this repository**. A
byte-identical copy of each lives in every periodic plugin, because these
plugins ship independently and cannot import from one another:

| File | `SHARED_MODULE_NAME` | Version | Also in |
|---|---|---|---|
| `cell_model.py` | `periodic-cell-model` | 0.6.0 | VASP, Quantum ESPRESSO, CP2K |
| `elements.py` | `periodic-elements` | 0.1.0 | VASP, Quantum ESPRESSO, CP2K |

Sibling repositories under `DEV_MAIN/`:
`moleditpy_vasp_input_generator/vasp_input_generator/`,
`moleditpy_quantum_espresso_input_generator/qe_input_generator/`,
`moleditpy_cp2k_input_generator/cp2k_input_generator/`.

`slab.py` is **not** shared — the slab mathematics lives here alone, and the
generators consume its output as a CIF rather than importing it.

**The rule when you change one of these files:**

1. Bump its `SHARED_MODULE_VERSION` (the module's own version, independent of
   `PLUGIN_VERSION`).
2. Copy the file verbatim over every other copy listed above — the copies must
   stay byte-identical, so make the edit once and copy, never edit each in turn.
3. Update the pinned version in each repo's test suite
   (`tests/test_cell_model.py` here, `tests/test_structure_panel.py` in the
   three generators). The pin is what makes a stale copy fail loudly instead of
   drifting.
4. Run all four test suites, not just this one.

```bash
cd G:/DEV_MAIN
md5sum moleditpy_*/*/cell_model.py    # every hash must match
```

`cell_model.py` imports `elements.py` for its element-symbol table, so the two
always travel together. This repository has no `structure_panel.py`; it reaches
the CIF Viewer through its own `cif_viewer_link.py`.

## Testing

```bash
python -m pytest tests/ -v
```

Headless; PyQt6 and RDKit are stubbed where needed. `tests/test_api.py` runs
`plugin_api_checker.py` against the main app when
`../python_molecular_editor/` exists, and skips otherwise.

## Conventions

- No module-level `run()`. The host adds its own Plugins-menu entry for any
  module exposing `run`, which would duplicate the entry registered in
  `initialize()`; the dialog opens through `_open_dialog()` instead.
- Only hard dependency beyond the host is numpy. pymatgen is optional and
  imported inside a `try` (space-group expansion for CIFs with no symop loop).
- Files are written with `newline="\n"`.
