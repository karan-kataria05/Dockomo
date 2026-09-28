"""
Ligand and receptor preparation.

Ligands:  RDKit (load .sdf/.pdbqt, add Hs, MMFF94 minimize) + Meeko (PDBQT write)
Receptor: text-based waters/hetero strip + mk_prepare_receptor.py (Meeko console
          script, installed automatically by `pip install meeko`) for PDBQT write

Nothing here shells out to WSL or Open Babel. `mk_prepare_receptor.py` is a pure
pip-installed Python console script, so calling it via subprocess is still 100%
native Windows Python -- no bash, no WSL, no separate binary download.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from rdkit import Chem
from rdkit.Chem import AllChem

from meeko import MoleculePreparation, PDBQTWriterLegacy


# --------------------------------------------------------------------------- #
# Ligands
# --------------------------------------------------------------------------- #

@dataclass
class Ligand:
    name: str
    mol: "Chem.Mol"
    source_path: str
    minimized: bool = False
    min_energy: float | None = None
    min_forcefield: str | None = None
    pdbqt_path: str | None = None
    error: str | None = None


def load_ligands(path: str) -> list[Ligand]:
    """Load one or many ligands from a .sdf library or a single .pdbqt/.mol2/.pdb file."""
    ext = os.path.splitext(path)[1].lower()
    ligands: list[Ligand] = []

    if ext == ".sdf":
        supplier = Chem.SDMolSupplier(path, removeHs=False)
        for i, mol in enumerate(supplier):
            if mol is None:
                ligands.append(Ligand(name=f"invalid_{i}", mol=None, source_path=path,
                                       error="RDKit could not parse this record"))
                continue
            name = mol.GetProp("_Name") if mol.HasProp("_Name") and mol.GetProp("_Name") else f"ligand_{i+1}"
            mol = Chem.AddHs(mol, addCoords=True)
            ligands.append(Ligand(name=name, mol=mol, source_path=path))

    elif ext in (".mol2", ".pdb"):
        mol = Chem.MolFromMol2File(path, removeHs=False) if ext == ".mol2" else Chem.MolFromPDBFile(path, removeHs=False)
        if mol is None:
            raise ValueError(f"RDKit could not parse {path}")
        mol = Chem.AddHs(mol, addCoords=True)
        name = os.path.splitext(os.path.basename(path))[0]
        ligands.append(Ligand(name=name, mol=mol, source_path=path))

    elif ext == ".pdbqt":
        # Already-prepared ligand: skip minimize/convert, just register the path.
        name = os.path.splitext(os.path.basename(path))[0]
        lig = Ligand(name=name, mol=None, source_path=path, minimized=True)
        lig.pdbqt_path = path
        ligands.append(lig)

    else:
        raise ValueError(f"Unsupported ligand format: {ext}")

    return ligands


def minimize_ligand(ligand: Ligand, max_iters: int = 2000) -> Ligand:
    """MMFF94 minimize in place; falls back to UFF if MMFF params are missing."""
    if ligand.mol is None:
        return ligand
    try:
        if AllChem.MMFFHasAllMoleculeParams(ligand.mol):
            props = AllChem.MMFFGetMoleculeProperties(ligand.mol)
            ff = AllChem.MMFFGetMoleculeForceField(ligand.mol, props)
            ligand.min_forcefield = "mmff"
        else:
            ff = AllChem.UFFGetMoleculeForceField(ligand.mol)
            ligand.min_forcefield = "uff"
        ff.Initialize()
        ff.Minimize(maxIts=max_iters)
        ligand.min_energy = ff.CalcEnergy()
        ligand.minimized = True
    except Exception as exc:  # noqa: BLE001 - report, don't crash the batch
        ligand.error = f"minimize failed: {exc}"
    return ligand


def minimize_all(ligands: list[Ligand], progress_cb=None) -> list[Ligand]:
    total = len(ligands)
    for i, lig in enumerate(ligands):
        if lig.mol is not None:
            minimize_ligand(lig)
        if progress_cb:
            progress_cb(i + 1, total, lig.name)
    return ligands


def ligand_to_pdbqt(ligand: Ligand, output_dir: str) -> Ligand:
    """Write one ligand's PDBQT using Meeko (v0.5+ API)."""
    if ligand.pdbqt_path and ligand.mol is None:
        return ligand  # already a .pdbqt input, nothing to do

    os.makedirs(output_dir, exist_ok=True)
    try:
        preparator = MoleculePreparation()
        setups = preparator.prepare(ligand.mol)
        if not setups:
            ligand.error = "meeko produced no molecule setups"
            return ligand
        pdbqt_string, is_ok, err_msg = PDBQTWriterLegacy.write_string(setups[0])
        if not is_ok:
            ligand.error = f"meeko PDBQT write failed: {err_msg}"
            return ligand
        out_path = os.path.join(output_dir, f"{_safe_filename(ligand.name)}.pdbqt")
        with open(out_path, "w") as fh:
            fh.write(pdbqt_string)
        ligand.pdbqt_path = out_path
    except Exception as exc:  # noqa: BLE001
        ligand.error = f"pdbqt conversion failed: {exc}"
    return ligand


def convert_all_to_pdbqt(ligands: list[Ligand], output_dir: str, progress_cb=None) -> list[Ligand]:
    total = len(ligands)
    for i, lig in enumerate(ligands):
        ligand_to_pdbqt(lig, output_dir)
        if progress_cb:
            progress_cb(i + 1, total, lig.name)
    return ligands


def _safe_filename(name: str) -> str:
    keep = "-_.() "
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip() or "ligand"


# --------------------------------------------------------------------------- #
# Receptor
# --------------------------------------------------------------------------- #

_WATER_RESNAMES = {"HOH", "WAT", "H2O", "DOD", "TIP", "TIP3", "TIP4"}


@dataclass
class Receptor:
    source_pdb: str
    cleaned_pdb: str | None = None
    pdbqt_path: str | None = None
    hetero_removed: list[str] = field(default_factory=list)
    error: str | None = None
    atoms_xyz: list[tuple[float, float, float]] = field(default_factory=list)
    prep_log: str = ""
    residue_warnings: list[str] = field(default_factory=list)


def strip_waters_and_hetero(pdb_path: str, output_path: str) -> Receptor:
    """
    Text-level pass over the PDB: drop water HETATM records and non-standard
    heteroatom groups (ligands, ions, cofactors) but keep standard ATOM records
    for the 20 amino acids (+ common variants). Also collects protein atom
    coordinates for box auto-detection.
    """
    rec = Receptor(source_pdb=pdb_path)
    removed_resnames: set[str] = set()
    coords: list[tuple[float, float, float]] = []

    try:
        with open(pdb_path, "r") as fh:
            lines = fh.readlines()

        kept_lines = []
        for line in lines:
            record = line[:6].strip()
            if record in ("ATOM", "HETATM"):
                resname = line[17:20].strip()
                if record == "HETATM":
                    # drop waters and any other heteroatom group entirely
                    removed_resnames.add(resname)
                    continue
                # standard ATOM record: keep, and track coordinates
                try:
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    coords.append((x, y, z))
                except ValueError:
                    pass
                kept_lines.append(line)
            elif record in ("TER", "END", "MODEL", "ENDMDL", "CRYST1"):
                kept_lines.append(line)
            # skip everything else (headers, CONECT, etc.)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as fh:
            fh.writelines(kept_lines)

        rec.cleaned_pdb = output_path
        rec.hetero_removed = sorted(removed_resnames)
        rec.atoms_xyz = coords
    except Exception as exc:  # noqa: BLE001
        rec.error = f"cleanup failed: {exc}"

    return rec

def load_prepared_receptor(pdbqt_path: str) -> Receptor:
    """Register an already-prepared receptor (a .pdbqt handed to us
    directly) without running strip/protonation -- still extracts atom
    coordinates so box auto-detection keeps working."""
    rec = Receptor(source_pdb=pdbqt_path, cleaned_pdb=pdbqt_path, pdbqt_path=pdbqt_path)
    coords = []
    try:
        with open(pdbqt_path, "r") as fh:
            for line in fh:
                if line[:6].strip() not in ("ATOM", "HETATM"):
                    continue
                try:
                    coords.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
                except ValueError:
                    pass
        rec.atoms_xyz = coords
    except Exception as exc:  # noqa: BLE001
        rec.error = f"could not read {pdbqt_path}: {exc}"
    return rec

def _find_mk_prepare_receptor() -> str | None:
    """Look next to the running app first (for a frozen .exe with the script
    copied alongside it, like Step 1 above), then fall back to PATH."""
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    for name in ("mk_prepare_receptor.exe", "mk_prepare_receptor.py"):
        candidate = os.path.join(app_dir, name)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("mk_prepare_receptor.exe") or shutil.which("mk_prepare_receptor.py")

def prepare_receptor_pdbqt(receptor: Receptor, output_dir: str) -> Receptor:
    """
    Runs Meeko's receptor-prep logic IN-PROCESS (calling its CLI module's main()
    directly) instead of shelling out to mk_prepare_receptor.py as a subprocess.
    This is what makes it actually work inside a compiled .exe -- there's no real
    python.exe to hand a script to in there, but meeko is already an importable
    bundled module either way (dev run or compiled).
    """
    if receptor.cleaned_pdb is None:
        receptor.error = receptor.error or "no cleaned PDB to prepare"
        return receptor

    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(receptor.cleaned_pdb))[0]
    out_base = os.path.join(output_dir, basename)

    import io
    import contextlib
    from meeko.cli.mk_prepare_receptor import main as _mk_prepare_receptor_main

    cli_args = ["--read_pdb", receptor.cleaned_pdb, "-o", out_base, "-p", "-a"]
    old_argv = sys.argv
    sys.argv = ["mk_prepare_receptor.py"] + cli_args
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    exit_code = 0
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                _mk_prepare_receptor_main()
            except SystemExit as exc:
                exit_code = exc.code or 0
    except Exception as exc:  # noqa: BLE001
        stderr_buf.write(f"\n[receptor prep raised] {exc}")
        exit_code = 1
    finally:
        sys.argv = old_argv

    receptor.prep_log = stdout_buf.getvalue() + "\n" + stderr_buf.getvalue()
    receptor.residue_warnings = _extract_residue_warnings(receptor.prep_log)

    if exit_code:
        receptor.error = f"receptor prep failed (exit {exit_code}) - see log above"
        return receptor

    candidate = out_base + ".pdbqt"
    if not os.path.exists(candidate):
        candidate = out_base + "_rigid.pdbqt"
    if os.path.exists(candidate):
        receptor.pdbqt_path = candidate
    else:
        receptor.error = "receptor prep ran but no PDBQT output was found"

    return receptor

def _extract_residue_warnings(log_text: str) -> list[str]:
    """Pull out lines that indicate a residue was skipped, missing an atom, or
    didn't match a template -- these are exactly the mismatches that used to
    fail silently under --allow_bad_res."""
    keywords = ("missing", "skip", "not matched", "no template", "unrecognized",
                "warning", "could not", "ignored")
    warnings = []
    for line in log_text.splitlines():
        low = line.lower()
        if any(k in low for k in keywords) and line.strip():
            warnings.append(line.strip())
    return warnings


# --------------------------------------------------------------------------- #
# Box auto-detection
# --------------------------------------------------------------------------- #

def box_from_whole_protein(receptor: Receptor, padding: float = 8.0) -> dict:
    """Bounding box around every protein atom, with padding on each side."""
    if not receptor.atoms_xyz:
        raise ValueError("receptor has no atom coordinates loaded")
    xs = [p[0] for p in receptor.atoms_xyz]
    ys = [p[1] for p in receptor.atoms_xyz]
    zs = [p[2] for p in receptor.atoms_xyz]
    return _box_from_bounds(xs, ys, zs, padding)


def box_from_residue(pdb_path: str, chain: str, resnum: int, padding: float = 8.0) -> dict:
    """Bounding box around one residue's atoms (e.g. a co-crystallized ligand
    kept as its own chain/resnum, or a catalytic residue), plus padding."""
    xs, ys, zs = [], [], []
    with open(pdb_path, "r") as fh:
        for line in fh:
            record = line[:6].strip()
            if record not in ("ATOM", "HETATM"):
                continue
            line_chain = line[21].strip()
            try:
                line_resnum = int(line[22:26])
            except ValueError:
                continue
            if line_chain == chain and line_resnum == resnum:
                xs.append(float(line[30:38]))
                ys.append(float(line[38:46]))
                zs.append(float(line[46:54]))
    if not xs:
        raise ValueError(f"no atoms found for chain {chain} residue {resnum}")
    return _box_from_bounds(xs, ys, zs, padding)


def _box_from_bounds(xs, ys, zs, padding) -> dict:
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    sx = (max(xs) - min(xs)) + 2 * padding
    sy = (max(ys) - min(ys)) + 2 * padding
    sz = (max(zs) - min(zs)) + 2 * padding
    return {
        "center_x": round(cx, 3), "center_y": round(cy, 3), "center_z": round(cz, 3),
        "size_x": round(sx, 3), "size_y": round(sy, 3), "size_z": round(sz, 3),
    }
