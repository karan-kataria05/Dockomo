import csv
import os

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QProgressBar, QPlainTextEdit,
    QLabel, QSplitter, QRadioButton, QButtonGroup, QLineEdit, QSpinBox,
    QDoubleSpinBox, QFormLayout, QMessageBox, QAction, QGroupBox,
)

from core import prep, docking, project
from core.paths import settings_ini_path, bundled_vina_exe, default_output_dir, is_writable_dir
from ui.viewer import MoleculeViewer
from ui.workers import Worker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dockomo - rigid docking (AutoDock Vina)")
        self.resize(1300, 800)

        # ---- in-memory state ----
        self.ligands: list[prep.Ligand] = []
        self.receptor: prep.Receptor | None = None
        self.box: dict | None = None
        self.dock_results: list[docking.DockResult] = []
        self._results_row_map: list[int] = []
        self.project_path: str | None = None
        self.output_dir: str = default_output_dir()
        self._worker: Worker | None = None

        # Persistent config (dockomo_settings.ini next to main.py) -- remembers
        # last-used folders across runs.
        self.settings = QSettings(settings_ini_path(), QSettings.IniFormat)
        remembered_output = self.settings.value("last_output_dir", "")
        if remembered_output and is_writable_dir(remembered_output):
            self.output_dir = remembered_output

        self._build_menu()
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_menu(self):
        menu = self.menuBar().addMenu("&Project")
        new_act = QAction("New", self)
        open_act = QAction("Open...", self)
        save_act = QAction("Save", self)
        save_as_act = QAction("Save As...", self)
        new_act.triggered.connect(self._new_project)
        open_act.triggered.connect(self._open_project)
        save_act.triggered.connect(self._save_project)
        save_as_act.triggered.connect(lambda: self._save_project(force_dialog=True))
        for a in (new_act, open_act, save_act, save_as_act):
            menu.addAction(a)

        help_menu = self.menuBar().addMenu("&Help")
        about_act = QAction("About Dockomo", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _show_about(self):
        QMessageBox.about(
            self, "About Dockomo",
            "<h3>Dockomo</h3>"
            "<p>Rigid molecular docking studio (AutoDock Vina)</p>"
            "<p>Created by <b>Karan Kataria</b></p>"
        )

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_ligands_tab(), "Ligands")
        self.tabs.addTab(self._build_macromolecule_tab(), "Macromolecule")
        self.tabs.addTab(self._build_box_tab(), "Vina Box")
        self.tabs.addTab(self._build_run_tab(), "Run")
        self.tabs.addTab(self._build_results_tab(), "Results")
        splitter.addWidget(self.tabs)

        self.viewer = MoleculeViewer()
        splitter.addWidget(self.viewer)
        splitter.setSizes([650, 650])

        self.setCentralWidget(splitter)
        self.statusBar().addPermanentWidget(QLabel("Dockomo  \u00b7  \u00a9 Karan Kataria"))

    # ---- Ligands tab ----
    def _build_ligands_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load Ligand Library (.sdf / .pdbqt)...")
        load_btn.clicked.connect(self._load_ligands)
        min_btn = QPushButton("Minimize All (MMFF94)")
        min_btn.clicked.connect(self._minimize_all)
        conv_btn = QPushButton("Convert All to PDBQT")
        conv_btn.clicked.connect(self._convert_all)
        for b in (load_btn, min_btn, conv_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        self.ligand_table = QTableWidget(0, 3)
        self.ligand_table.setHorizontalHeaderLabels(["Ligand", "Minimized", "PDBQT status"])
        layout.addWidget(self.ligand_table)

        self.ligand_progress = QProgressBar()
        layout.addWidget(self.ligand_progress)
        self.ligand_log = QPlainTextEdit(readOnly=True)
        self.ligand_log.setMaximumHeight(120)
        layout.addWidget(self.ligand_log)
        return w

    # ---- Macromolecule tab ----
    def _build_macromolecule_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load Receptor PDB...")
        load_btn.clicked.connect(self._load_receptor)
        prep_btn = QPushButton("Strip Waters/Hetero + Add H's + Convert to PDBQT")
        prep_btn.clicked.connect(self._prepare_receptor)
        btn_row.addWidget(load_btn)
        btn_row.addWidget(prep_btn)
        layout.addLayout(btn_row)

        self.receptor_status = QLabel("No receptor loaded.")
        layout.addWidget(self.receptor_status)
        self.receptor_log = QPlainTextEdit(readOnly=True)
        layout.addWidget(self.receptor_log)
        return w

    # ---- Box tab ----
    def _build_box_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        mode_group = QGroupBox("Auto-detect box around")
        mode_layout = QHBoxLayout(mode_group)
        self.box_mode_whole = QRadioButton("Whole protein")
        self.box_mode_residue = QRadioButton("Chain + residue number")
        self.box_mode_whole.setChecked(True)
        group = QButtonGroup(w)
        group.addButton(self.box_mode_whole)
        group.addButton(self.box_mode_residue)
        mode_layout.addWidget(self.box_mode_whole)
        mode_layout.addWidget(self.box_mode_residue)
        self.box_chain_input = QLineEdit()
        self.box_chain_input.setPlaceholderText("chain e.g. A")
        self.box_chain_input.setMaximumWidth(80)
        self.box_resnum_input = QSpinBox()
        self.box_resnum_input.setRange(1, 99999)
        mode_layout.addWidget(QLabel("Chain:"))
        mode_layout.addWidget(self.box_chain_input)
        mode_layout.addWidget(QLabel("Residue #:"))
        mode_layout.addWidget(self.box_resnum_input)
        layout.addWidget(mode_group)

        pad_row = QHBoxLayout()
        pad_row.addWidget(QLabel("Padding (\u00c5):"))
        self.box_padding = QDoubleSpinBox()
        self.box_padding.setRange(0, 50)
        self.box_padding.setValue(8.0)
        pad_row.addWidget(self.box_padding)
        detect_btn = QPushButton("Auto-Detect Box")
        detect_btn.clicked.connect(self._auto_detect_box)
        pad_row.addWidget(detect_btn)
        layout.addLayout(pad_row)

        form = QFormLayout()
        self.box_fields = {}
        for key, default in [("center_x", 0), ("center_y", 0), ("center_z", 0),
                              ("size_x", 20), ("size_y", 20), ("size_z", 20)]:
            spin = QDoubleSpinBox()
            spin.setRange(-9999, 9999)
            spin.setValue(default)
            self.box_fields[key] = spin
            form.addRow(key, spin)
        layout.addLayout(form)

        update_btn = QPushButton("Apply Box / Update Viewer")
        update_btn.clicked.connect(self._apply_box_from_fields)
        layout.addWidget(update_btn)
        layout.addStretch()
        return w

    # ---- Run tab ----
    def _build_run_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        form = QFormLayout()

        self.exhaustiveness_spin = QSpinBox()
        self.exhaustiveness_spin.setRange(1, 64)
        self.exhaustiveness_spin.setValue(8)
        form.addRow("Exhaustiveness", self.exhaustiveness_spin)

        self.n_poses_spin = QSpinBox()
        self.n_poses_spin.setRange(1, 30)
        self.n_poses_spin.setValue(9)
        form.addRow("Number of poses", self.n_poses_spin)

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2_147_483_647)
        self.seed_spin.setValue(docking.DEFAULT_SEED)
        form.addRow("Seed (fixed = reproducible, avoids the segfault)", self.seed_spin)

        layout.addLayout(form)

        vina_row = QHBoxLayout()
        self.vina_exe_edit = QLineEdit()
        self.vina_exe_edit.setPlaceholderText("vina.exe (leave as-is if it's already on PATH)")
        self.vina_exe_edit.setText(self.settings.value("last_vina_exe", bundled_vina_exe()))
        vina_browse_btn = QPushButton("Browse...")
        vina_browse_btn.clicked.connect(self._choose_vina_exe)
        vina_row.addWidget(QLabel("Vina executable:"))
        vina_row.addWidget(self.vina_exe_edit)
        vina_row.addWidget(vina_browse_btn)
        layout.addLayout(vina_row)

        out_row = QHBoxLayout()
        self.output_dir_label = QLabel(self.output_dir)
        out_btn = QPushButton("Choose Output Folder...")
        out_btn.clicked.connect(self._choose_output_dir)
        out_row.addWidget(self.output_dir_label)
        out_row.addWidget(out_btn)
        layout.addLayout(out_row)

        run_btn = QPushButton("Start Batch Docking")
        run_btn.clicked.connect(self._start_docking)
        layout.addWidget(run_btn)

        self.run_progress = QProgressBar()
        layout.addWidget(self.run_progress)
        self.run_log = QPlainTextEdit(readOnly=True)
        layout.addWidget(self.run_log)
        return w

    # ---- Results tab ----
    def _build_results_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        layout.addWidget(export_btn)

        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(
            ["Ligand (receptor_ligand_ff_E=energy)", "Affinity (kcal/mol)", "RMSD l.b.", "RMSD u.b."])
        self.results_table.itemSelectionChanged.connect(self._show_selected_pose)
        self.results_table.setSortingEnabled(True)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results_table)
        return w

    # ------------------------------------------------------------------ #
    # Ligands tab logic
    # ------------------------------------------------------------------ #
    def _load_ligands(self):
        start_dir = self.settings.value("last_ligand_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Load ligand library", start_dir, "Ligand files (*.sdf *.pdbqt *.mol2 *.pdb)")
        if not path:
            return
        self.settings.setValue("last_ligand_dir", os.path.dirname(path))
        try:
            new_ligands = prep.load_ligands(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self.ligands.extend(new_ligands)
        self._refresh_ligand_table()
        self.ligand_log.appendPlainText(f"Loaded {len(new_ligands)} ligand(s) from {path}")

    def _refresh_ligand_table(self):
        self.ligand_table.setRowCount(len(self.ligands))
        for row, lig in enumerate(self.ligands):
            self.ligand_table.setItem(row, 0, QTableWidgetItem(lig.name))
            self.ligand_table.setItem(row, 1, QTableWidgetItem("yes" if lig.minimized else "no"))
            status = lig.pdbqt_path or (lig.error or "pending")
            self.ligand_table.setItem(row, 2, QTableWidgetItem(status))

    def _minimize_all(self):
        if not self.ligands:
            QMessageBox.warning(self, "No ligands", "Load a ligand library first.")
            return
        self._run_worker(
            prep.minimize_all, self.ligands,
            on_progress=lambda d, t, name: self._log_progress(self.ligand_log, self.ligand_progress, d, t, name),
            on_done=self._minimize_done,
        )

    def _minimize_done(self, ligands):
        self.ligands = ligands
        self._refresh_ligand_table()
        self.ligand_log.appendPlainText("Minimization complete.")

    def _convert_all(self):
        if not self.ligands:
            QMessageBox.warning(self, "No ligands", "Load a ligand library first.")
            return
        out_dir = os.path.join(self.output_dir, "ligands_pdbqt")
        self._run_worker(
            prep.convert_all_to_pdbqt, self.ligands, out_dir,
            on_progress=lambda d, t, name: self._log_progress(self.ligand_log, self.ligand_progress, d, t, name),
            on_done=self._convert_done,
        )

    def _convert_done(self, ligands):
        self.ligands = ligands
        self._refresh_ligand_table()
        n_ok = sum(1 for lig in ligands if lig.pdbqt_path)
        self.ligand_log.appendPlainText(f"PDBQT conversion complete: {n_ok}/{len(ligands)} succeeded.")

    # ------------------------------------------------------------------ #
    # Macromolecule tab logic
    # ------------------------------------------------------------------ #
    def _load_receptor(self):
        start_dir = self.settings.value("last_receptor_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Load receptor PDB or PDBQT", start_dir,
            "Receptor files (*.pdb *.pdbqt);;PDB files (*.pdb);;Already-prepared PDBQT (*.pdbqt)")
        if not path:
            return
        self.settings.setValue("last_receptor_dir", os.path.dirname(path))

        if path.lower().endswith(".pdbqt"):
            self.receptor = prep.load_prepared_receptor(path)
            self._pending_receptor_pdb = None
            if self.receptor.error:
                self.receptor_status.setText("Receptor load FAILED - see log.")
                self.receptor_log.appendPlainText(f"ERROR: {self.receptor.error}")
                return
            self.receptor_status.setText(f"Ready (already prepared): {path}")
            self.receptor_log.appendPlainText(f"Loaded already-prepared receptor PDBQT: {path}")
            self._refresh_viewer()
        else:
            self._pending_receptor_pdb = path
            self.receptor_status.setText(f"Loaded: {path}  (not yet prepared)")
            self.receptor_log.appendPlainText(f"Receptor selected: {path}")

    def _prepare_receptor(self):
        if not getattr(self, "_pending_receptor_pdb", None):
            QMessageBox.warning(self, "No receptor", "Load a receptor PDB first.")
            return
        orig_base = os.path.splitext(os.path.basename(self._pending_receptor_pdb))[0]
        cleaned_path = os.path.join(self.output_dir, "receptor", f"{orig_base}_prepared.pdb")
        self.receptor_log.appendPlainText("Stripping waters/heteroatoms...")
        rec = prep.strip_waters_and_hetero(self._pending_receptor_pdb, cleaned_path)
        if rec.error:
            self.receptor_log.appendPlainText(f"ERROR: {rec.error}")
            return
        self.receptor_log.appendPlainText(f"Removed heteroatom groups: {', '.join(rec.hetero_removed) or '(none found)'}")
        self.receptor_log.appendPlainText("Running mk_prepare_receptor.py (adds H's, charges, writes PDBQT)...")
        rec = prep.prepare_receptor_pdbqt(rec, os.path.join(self.output_dir, "receptor"))
        self.receptor = rec

        if rec.prep_log.strip():
            self.receptor_log.appendPlainText("--- mk_prepare_receptor.py output ---")
            self.receptor_log.appendPlainText(rec.prep_log.strip())
        if rec.residue_warnings:
            self.receptor_log.appendPlainText(
                f"--- {len(rec.residue_warnings)} residue warning(s) (missing atoms / no template match) ---"
            )
            for w in rec.residue_warnings:
                self.receptor_log.appendPlainText(f"  ! {w}")

        if rec.error:
            self.receptor_log.appendPlainText(f"ERROR: {rec.error}")
            self.receptor_status.setText("Receptor prep FAILED - see log.")
            return
        self.receptor_status.setText(f"Ready: {rec.pdbqt_path}")
        if rec.residue_warnings:
            self.receptor_status.setText(
                self.receptor_status.text() + f"  ({len(rec.residue_warnings)} residue warning(s) - check log)"
            )
        self.receptor_log.appendPlainText(f"Receptor PDBQT: {rec.pdbqt_path}")
        self._refresh_viewer()

    # ------------------------------------------------------------------ #
    # Box tab logic
    # ------------------------------------------------------------------ #
    def _auto_detect_box(self):
        if not self.receptor or not self.receptor.cleaned_pdb:
            QMessageBox.warning(self, "No receptor", "Load and prepare a receptor first.")
            return
        padding = self.box_padding.value()
        try:
            if self.box_mode_whole.isChecked():
                box = prep.box_from_whole_protein(self.receptor, padding=padding)
            else:
                chain = self.box_chain_input.text().strip()
                resnum = self.box_resnum_input.value()
                if not chain:
                    QMessageBox.warning(self, "Missing chain", "Enter a chain ID.")
                    return
                box = prep.box_from_residue(self.receptor.cleaned_pdb, chain, resnum, padding=padding)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Box detection failed", str(exc))
            return
        self.box = box
        for key, spin in self.box_fields.items():
            spin.setValue(box[key])
        self._refresh_viewer()

    def _apply_box_from_fields(self):
        self.box = {key: spin.value() for key, spin in self.box_fields.items()}
        self._refresh_viewer()

    # ------------------------------------------------------------------ #
    # Run tab logic
    # ------------------------------------------------------------------ #
    def _choose_vina_exe(self):
        start_dir = self.settings.value("last_vina_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Locate vina.exe", start_dir, "Executable (*.exe);;All files (*)")
        if path:
            self.vina_exe_edit.setText(path)
            self.settings.setValue("last_vina_dir", os.path.dirname(path))
            self.settings.setValue("last_vina_exe", path)

    def _choose_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_dir)
        if d:
            self.output_dir = d
            self.output_dir_label.setText(d)
            self.settings.setValue("last_output_dir", d)

    def _start_docking(self):
        if not self.receptor or not self.receptor.pdbqt_path:
            QMessageBox.warning(self, "No receptor", "Prepare a receptor first.")
            return
        if not self.box:
            QMessageBox.warning(self, "No box", "Auto-detect or set the search box first.")
            return
        ready_ligands = [lig for lig in self.ligands if lig.pdbqt_path]
        if not ready_ligands:
            QMessageBox.warning(self, "No ligands", "Convert at least one ligand to PDBQT first.")
            return

        settings = docking.DockingSettings(
            exhaustiveness=self.exhaustiveness_spin.value(),
            n_poses=self.n_poses_spin.value(),
            seed=self.seed_spin.value(),
            vina_exe=self.vina_exe_edit.text().strip() or "vina.exe",
        )
        found_exe = docking.find_vina_exe(settings.vina_exe)
        if not found_exe:
            QMessageBox.critical(
                self, "vina.exe not found",
                "Couldn't locate vina.exe on PATH or at the path given.\n\n"
                "Use 'Browse...' next to Vina executable to point directly at "
                "the vina.exe you already used from the terminal.",
            )
            return
        out_dir = os.path.join(self.output_dir, "docked_poses")
        self.run_log.appendPlainText(
            f"Using vina executable: {found_exe}\n"
            f"Starting sequential batch docking of {len(ready_ligands)} ligand(s), "
            f"exhaustiveness={settings.exhaustiveness}, poses={settings.n_poses}, seed={settings.seed}"
        )
        self._run_worker(
            docking.dock_batch, self.receptor.pdbqt_path, self.box, ready_ligands, settings, out_dir,
            on_progress=lambda d, t, name: self._log_progress(self.run_log, self.run_progress, d, t, name),
            on_done=self._docking_done,
            with_log=True,
            on_log=self.run_log.appendPlainText,
        )

    def _docking_done(self, results):
        self.dock_results = results
        self.run_log.appendPlainText("Docking complete.")
        self._refresh_results_table()
        self.tabs.setCurrentIndex(4)

    # ------------------------------------------------------------------ #
    # Results tab logic
    # ------------------------------------------------------------------ #
    def _pose_label(self, ligand_name: str) -> str:
        receptor_base = "receptor"
        if self.receptor and self.receptor.pdbqt_path:
            receptor_base = os.path.splitext(os.path.basename(self.receptor.pdbqt_path))[0]
        lig = next((l for l in self.ligands if l.name == ligand_name), None)
        if lig and lig.min_forcefield and lig.min_energy is not None:
            return f"{receptor_base}_{ligand_name}_{lig.min_forcefield}_E={lig.min_energy:.2f}"
        return f"{receptor_base}_{ligand_name}"

    def _refresh_results_table(self):
        self.results_table.setSortingEnabled(False)
        # One row per pose, poses of the same ligand kept together (grouped),
        # in the order docking ran. self._results_row_map[row] -> index into self.dock_results
        self._results_row_map = []
        rows = []
        for res_idx, res in enumerate(self.dock_results):
            label = self._pose_label(res.ligand_name)
            if res.error or not res.pose_affinities:
                rows.append((res_idx, label, res.error or "n/a", "", ""))
                continue
            for pose_i, affinity in enumerate(res.pose_affinities):
                rmsd_lb = res.pose_rmsd_lb[pose_i] if pose_i < len(res.pose_rmsd_lb) else 0.0
                rmsd_ub = res.pose_rmsd_ub[pose_i] if pose_i < len(res.pose_rmsd_ub) else 0.0
                rows.append((res_idx, label, f"{affinity:.1f}", f"{rmsd_lb:.3f}", f"{rmsd_ub:.3f}"))

        self.results_table.setRowCount(len(rows))
        for row, (res_idx, label, affinity, rmsd_lb, rmsd_ub) in enumerate(rows):
            self._results_row_map.append(res_idx)
            self.results_table.setItem(row, 0, QTableWidgetItem(label))
            self.results_table.setItem(row, 1, QTableWidgetItem(str(affinity)))
            self.results_table.setItem(row, 2, QTableWidgetItem(str(rmsd_lb)))
            self.results_table.setItem(row, 3, QTableWidgetItem(str(rmsd_ub)))
        self.results_table.setSortingEnabled(True)

    def _show_selected_pose(self):
        rows = self.results_table.selectionModel().selectedRows()
        if not rows or not self.dock_results or not getattr(self, "_results_row_map", None):
            return
        table_row = rows[0].row()
        if table_row >= len(self._results_row_map):
            return
        res = self.dock_results[self._results_row_map[table_row]]
        if res.out_pdbqt and os.path.exists(res.out_pdbqt):
            with open(res.out_pdbqt) as fh:
                lig_text = fh.read()
            self._refresh_viewer(ligand_pdbqt_text=lig_text)

    def _export_csv(self):
        if not self.dock_results:
            QMessageBox.warning(self, "No results", "Run docking first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export results CSV", "docking_results.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ligand", "affinity_kcal_mol", "rmsd_lb", "rmsd_ub"])
            for res in self.dock_results:
                label = self._pose_label(res.ligand_name)
                if res.error or not res.pose_affinities:
                    writer.writerow([label, res.error or "n/a", "", ""])
                    continue
                for pose_i, affinity in enumerate(res.pose_affinities):
                    rmsd_lb = res.pose_rmsd_lb[pose_i] if pose_i < len(res.pose_rmsd_lb) else 0.0
                    rmsd_ub = res.pose_rmsd_ub[pose_i] if pose_i < len(res.pose_rmsd_ub) else 0.0
                    writer.writerow([label, f"{affinity:.1f}", f"{rmsd_lb:.3f}", f"{rmsd_ub:.3f}"])
        QMessageBox.information(self, "Exported", f"Results written to {path}")

    # ------------------------------------------------------------------ #
    # Project save/load
    # ------------------------------------------------------------------ #
    def _new_project(self):
        self.ligands = []
        self.receptor = None
        self.box = None
        self.dock_results = []
        self.project_path = None
        self._refresh_ligand_table()
        self._refresh_results_table()
        self.receptor_status.setText("No receptor loaded.")
        self._refresh_viewer()

    def _save_project(self, force_dialog=False):
        path = self.project_path
        if force_dialog or not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save project", "session", f"Project (*{project.PROJECT_EXT})")
            if not path:
                return
        state = project.ProjectState(
            receptor_source_pdb=getattr(self, "_pending_receptor_pdb", None),
            receptor_cleaned_pdb=self.receptor.cleaned_pdb if self.receptor else None,
            receptor_pdbqt=self.receptor.pdbqt_path if self.receptor else None,
            ligand_names=[lig.name for lig in self.ligands],
            ligand_pdbqt_paths={lig.name: lig.pdbqt_path for lig in self.ligands if lig.pdbqt_path},
            box=self.box,
            exhaustiveness=self.exhaustiveness_spin.value(),
            n_poses=self.n_poses_spin.value(),
            seed=self.seed_spin.value(),
            vina_exe=self.vina_exe_edit.text().strip() or "vina.exe",
            output_dir=self.output_dir,
            results={
                r.ligand_name: {
                    "best_affinity": r.best_affinity,
                    "pose_affinities": r.pose_affinities,
                    "out_pdbqt": r.out_pdbqt,
                } for r in self.dock_results
            },
        )
        project.save_project(state, path)
        self.project_path = path if path.endswith(project.PROJECT_EXT) else path + project.PROJECT_EXT
        QMessageBox.information(self, "Saved", f"Project saved to {self.project_path}")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", f"Project (*{project.PROJECT_EXT})")
        if not path:
            return
        state = project.load_project(path)
        self.project_path = path
        self.output_dir = state.output_dir or self.output_dir
        self.output_dir_label.setText(self.output_dir)
        self.exhaustiveness_spin.setValue(state.exhaustiveness)
        self.n_poses_spin.setValue(state.n_poses)
        self.seed_spin.setValue(state.seed)
        self.vina_exe_edit.setText(state.vina_exe or "vina.exe")
        self.box = state.box
        if self.box:
            for key, spin in self.box_fields.items():
                spin.setValue(self.box[key])
        # Rehydrate ligand list as lightweight already-converted entries
        self.ligands = [
            prep.Ligand(name=name, mol=None, source_path=state.ligand_library_path or "",
                        minimized=True, pdbqt_path=state.ligand_pdbqt_paths.get(name))
            for name in state.ligand_names
        ]
        self._refresh_ligand_table()
        if state.receptor_pdbqt:
            self.receptor = prep.Receptor(source_pdb=state.receptor_source_pdb or "",
                                           cleaned_pdb=state.receptor_cleaned_pdb,
                                           pdbqt_path=state.receptor_pdbqt)
            self.receptor_status.setText(f"Ready: {self.receptor.pdbqt_path}")
        self.dock_results = [
            docking.DockResult(ligand_name=name, ligand_pdbqt="", out_pdbqt=info.get("out_pdbqt"),
                                best_affinity=info.get("best_affinity"),
                                pose_affinities=info.get("pose_affinities", []))
            for name, info in state.results.items()
        ]
        self._refresh_results_table()
        self._refresh_viewer()
        self.run_log.appendPlainText(f"Project loaded from {path}")

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    def _refresh_viewer(self, ligand_pdbqt_text: str | None = None):
        receptor_text = None
        if self.receptor and self.receptor.cleaned_pdb and os.path.exists(self.receptor.cleaned_pdb):
            with open(self.receptor.cleaned_pdb) as fh:
                receptor_text = fh.read()
        self.viewer.update_view(receptor_text, ligand_pdbqt_text, self.box)

    def _log_progress(self, log_widget, progress_bar, done, total, label):
        progress_bar.setMaximum(total)
        progress_bar.setValue(done)
        log_widget.appendPlainText(f"[{done}/{total}] {label}")
        self.statusBar().showMessage(f"{label}  ({done}/{total})")

    def _run_worker(self, fn, *args, on_progress, on_done, with_log=False, on_log=None):
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another operation is still running.")
            return
        self._worker = Worker(fn, *args, with_log=with_log)
        self._worker.progress.connect(on_progress)
        self._worker.finished_ok.connect(on_done)
        self._worker.failed.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        if with_log and on_log:
            self._worker.log_line.connect(on_log)
        self._worker.start()