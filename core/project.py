"""Save/load a docking session so it can be resumed later (PyRx-style .dpx project)."""

import json
import os
from dataclasses import asdict, dataclass, field


PROJECT_EXT = ".dpxproj"  # "docking project" -- plain JSON, human-readable


@dataclass
class ProjectState:
    receptor_source_pdb: str | None = None
    receptor_cleaned_pdb: str | None = None
    receptor_pdbqt: str | None = None
    ligand_library_path: str | None = None
    ligand_names: list[str] = field(default_factory=list)
    ligand_pdbqt_paths: dict[str, str] = field(default_factory=dict)  # name -> path
    box: dict | None = None
    exhaustiveness: int = 8
    n_poses: int = 9
    seed: int = 42
    vina_exe: str = "vina.exe"
    output_dir: str | None = None
    results: dict[str, dict] = field(default_factory=dict)  # name -> {best_affinity, pose_affinities, out_pdbqt}


def save_project(state: ProjectState, path: str) -> None:
    if not path.endswith(PROJECT_EXT):
        path += PROJECT_EXT
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(asdict(state), fh, indent=2)


def load_project(path: str) -> ProjectState:
    with open(path, "r") as fh:
        data = json.load(fh)
    return ProjectState(**data)
