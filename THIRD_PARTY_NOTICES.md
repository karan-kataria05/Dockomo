# Third-Party Notices

Dockomo is built on top of, and its Windows installer bundles, the following
third-party software. Each remains under its own original license; nothing
here changes those terms.

## AutoDock Vina (bundled binary, `vina.exe`)
- License: Apache License 2.0
- https://vina.scripps.edu/
- Copyright (c) The Scripps Research Institute
- Citation: O. Trott, A. J. Olson, "AutoDock Vina: improving the speed and
  accuracy of docking with a new scoring function, efficient optimization,
  and multithreading," Journal of Computational Chemistry 31 (2010) 455-461.

## Meeko
- Used for ligand/receptor PDBQT preparation.
- https://github.com/forlilab/Meeko
- Check the LICENSE file in your installed `meeko` package
  (`venv\Lib\site-packages\meeko-*.dist-info\LICENSE`) for its exact terms --
  don't take this notice's wording as confirmed; verify it yourself before
  relying on it.

## RDKit
- License: BSD 3-Clause
- Used for ligand loading and MMFF94/UFF minimization.
- https://www.rdkit.org/

## PyQt5
- License: GPL v3 (the open-source distribution used here; a commercial
  license is also available from Riverbank Computing)
- https://www.riverbankcomputing.com/software/pyqt/
- This is why Dockomo itself is distributed under the GPLv3 -- see LICENSE.

## 3Dmol.js
- License: BSD 3-Clause
- Loaded at runtime for the embedded 3D molecule viewer.
- https://3dmol.csb.pitt.edu/

## gemmi
- License: MPL 2.0
- https://gemmi.readthedocs.io/

## scipy / numpy
- License: BSD 3-Clause
- https://scipy.org/ / https://numpy.org/
