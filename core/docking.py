"""
Docking engine wrapper around the standalone AutoDock Vina executable (vina.exe
on Windows), called via subprocess.

CORRECTED from the original v1 design: the `vina` PyPI package only ships
prebuilt wheels for Linux/Mac, so it cannot be pip-installed on Windows.
This is why we now call the .exe you already had working on the command line
-- except every invocation always passes an explicit --seed, which is exactly
what fixed the segfault for you manually. You never have to remember it again.

This is still 100% native Windows -- vina.exe is a standalone binary, no WSL,
no bash, called the same way core.prep calls mk_prepare_receptor.py.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass, field


DEFAULT_SEED = 42


@dataclass
class DockingSettings:
    exhaustiveness: int = 8
    n_poses: int = 9
    seed: int = DEFAULT_SEED
    cpu: int = 0  # 0 lets vina.exe pick (all cores); some builds require omitting the flag entirely for "all"
    vina_exe: str = "vina.exe"  # path to the executable; can be just "vina.exe"/"vina" if it's on PATH


@dataclass
class DockResult:
    ligand_name: str
    ligand_pdbqt: str
    out_pdbqt: str | None = None
    best_affinity: float | None = None
    pose_affinities: list[float] = field(default_factory=list)
    pose_rmsd_lb: list[float] = field(default_factory=list)
    pose_rmsd_ub: list[float] = field(default_factory=list)
    error: str | None = None
    stdout: str = ""


import re

_TABLE_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(-?\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s*$"
)


def _parse_result_table(stdout_text: str) -> list[tuple[float, float, float]]:
    """Parse vina.exe's own console table:
        mode |   affinity | dist from best mode
             | (kcal/mol) | rmsd l.b.| rmsd u.b.
        -----+------------+----------+----------
           1       -9.7          0          0
    Returns [(affinity, rmsd_lb, rmsd_ub), ...] in mode order.
    """
    rows = []
    for line in stdout_text.splitlines():
        m = _TABLE_ROW_RE.match(line)
        if m:
            _, affinity, rmsd_lb, rmsd_ub = m.groups()
            rows.append((float(affinity), float(rmsd_lb), float(rmsd_ub)))
    return rows


def _parse_pose_affinities(pdbqt_path: str) -> list[float]:
    """Fallback only -- prefer _parse_result_table(stdout) which also has RMSD."""
    affinities = []
    with open(pdbqt_path, "r") as fh:
        for line in fh:
            if line.startswith("REMARK VINA RESULT:"):
                parts = line.split()
                try:
                    affinities.append(float(parts[3]))
                except (IndexError, ValueError):
                    pass
    return affinities


def find_vina_exe(user_supplied: str | None = None) -> str | None:
    """Best-effort locate vina.exe: explicit path > bundled copy > PATH lookup > common install dirs."""
    if user_supplied and os.path.isfile(user_supplied):
        return user_supplied
    from core.paths import bundled_vina_exe
    bundled = bundled_vina_exe()
    if os.path.isfile(bundled):
        return bundled
    found = shutil.which("vina.exe") or shutil.which("vina")
    if found:
        return found
    common_dirs = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\vina"),
        os.path.expandvars(r"%ProgramFiles%\The Scripps Research Institute\Vina"),
        os.path.expandvars(r"%ProgramFiles(x86)%\The Scripps Research Institute\Vina"),
    ]
    for d in common_dirs:
        candidate = os.path.join(d, "vina.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


class DockingEngine:
    """One instance = one receptor + one grid box, reused across many ligands.

    Note: unlike the in-process python bindings, the CLI recomputes the
    affinity maps on every invocation (there's no way to persist them across
    separate vina.exe calls). This is somewhat slower for large batches than
    the original in-process design would have been, but it's the option that
    actually installs and runs on Windows.
    """

    def __init__(self, receptor_pdbqt: str, box: dict, settings: DockingSettings):
        self.receptor_pdbqt = receptor_pdbqt
        self.box = box
        self.settings = settings
        exe = find_vina_exe(settings.vina_exe)
        if not exe:
            raise FileNotFoundError(
                "vina.exe not found. Set the full path to it in the Run tab, "
                "or add its folder to your Windows PATH."
            )
        self.vina_exe = exe

    def dock_ligand(self, ligand_name: str, ligand_pdbqt: str, output_dir: str,
                     log_cb=None) -> DockResult:
        result = DockResult(ligand_name=ligand_name, ligand_pdbqt=ligand_pdbqt)
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{_safe_filename(ligand_name)}_out.pdbqt")
        log_path = os.path.join(output_dir, f"{_safe_filename(ligand_name)}_log.txt")

        cmd = [
            self.vina_exe,
            "--receptor", self.receptor_pdbqt,
            "--ligand", ligand_pdbqt,
            "--center_x", str(self.box["center_x"]),
            "--center_y", str(self.box["center_y"]),
            "--center_z", str(self.box["center_z"]),
            "--size_x", str(self.box["size_x"]),
            "--size_y", str(self.box["size_y"]),
            "--size_z", str(self.box["size_z"]),
            "--exhaustiveness", str(self.settings.exhaustiveness),
            "--num_modes", str(self.settings.n_poses),
            "--seed", str(self.settings.seed),
            "--out", out_path,
        ]
        if self.settings.cpu and self.settings.cpu > 0:
            cmd += ["--cpu", str(self.settings.cpu)]

        stdout_lines = []
        try:
            if log_cb:
                log_cb(f"$ {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                line = line.rstrip("\n")
                stdout_lines.append(line)
                if log_cb and line.strip():
                    log_cb(line)
            returncode = proc.wait(timeout=3600)

            full_stdout = "\n".join(stdout_lines)
            with open(log_path, "w") as fh:
                fh.write(full_stdout)
            result.stdout = full_stdout

            if returncode != 0:
                result.error = f"vina.exe exited {returncode} - see {log_path}"
                return result

            if not os.path.exists(out_path):
                result.error = "vina.exe finished but no output PDBQT was produced"
                return result

            result.out_pdbqt = out_path
            table = _parse_result_table(full_stdout)
            if table:
                result.pose_affinities = [row[0] for row in table]
                result.pose_rmsd_lb = [row[1] for row in table]
                result.pose_rmsd_ub = [row[2] for row in table]
            else:
                # fallback if console table format ever changes on you
                result.pose_affinities = _parse_pose_affinities(out_path)
                result.pose_rmsd_lb = [0.0] * len(result.pose_affinities)
                result.pose_rmsd_ub = [0.0] * len(result.pose_affinities)
            result.best_affinity = min(result.pose_affinities) if result.pose_affinities else None
        except FileNotFoundError:
            result.error = f"could not execute {self.vina_exe} - check the path"
        except subprocess.TimeoutExpired:
            result.error = "vina.exe timed out (over 1 hour on a single ligand)"
        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
        return result


def dock_batch(receptor_pdbqt: str, box: dict, ligands: list, settings: DockingSettings,
                output_dir: str, progress_cb=None, log_cb=None) -> list[DockResult]:
    """Sequential batch docking -- one ligand at a time, matching the 'safest' mode chosen."""
    engine = DockingEngine(receptor_pdbqt, box, settings)
    results = []
    total = len(ligands)
    for i, lig in enumerate(ligands):
        if progress_cb:
            progress_cb(i, total, f"starting {lig.name}...")
        if not lig.pdbqt_path:
            results.append(DockResult(
                ligand_name=lig.name, ligand_pdbqt="",
                error="no PDBQT available (prep step failed or was skipped)",
            ))
        else:
            results.append(engine.dock_ligand(lig.name, lig.pdbqt_path, output_dir, log_cb=log_cb))
        if progress_cb:
            progress_cb(i + 1, total, lig.name)
    return results


def _safe_filename(name: str) -> str:
    keep = "-_.() "
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip() or "ligand"
