"""3D viewer pane. Uses 3Dmol.js (pure JS, loaded from CDN) inside a
QWebEngineView -- no native OpenGL binding required, so it's reliable across
Windows GPU/driver setups (another common PyRx crash source)."""

from PyQt5.QtWebEngineWidgets import QWebEngineView

_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.0.4/3Dmol-min.js"></script>
<style>
  html, body {{ margin:0; padding:0; height:100%; background:#1e1e1e; }}
  #viewer {{ width:100%; height:100%; position:relative; }}
</style>
</head>
<body>
<div id="viewer"></div>
<script>
  let viewer = $3Dmol.createViewer(document.getElementById('viewer'), {{backgroundColor:'#1e1e1e'}});
  let receptorPDB = {receptor_json};
  let ligandPDBQT = {ligand_json};
  let box = {box_json};

  if (receptorPDB) {{
    viewer.addModel(receptorPDB, 'pdb');
    viewer.setStyle({{model:0}}, {{cartoon: {{color:'spectrum'}}}});
  }}
  if (ligandPDBQT) {{
    let ligModelIdx = receptorPDB ? 1 : 0;
    viewer.addModel(ligandPDBQT, 'pdbqt');
    viewer.setStyle({{model: ligModelIdx}}, {{stick: {{colorscheme:'yellowCarbon'}}}});
  }}
  if (box) {{
    viewer.addBox({{
      center: {{x: box.center_x, y: box.center_y, z: box.center_z}},
      dimensions: {{w: box.size_x, h: box.size_y, d: box.size_z}},
      color: 'red',
      wireframe: true
    }});
  }}
  viewer.zoomTo();
  viewer.render();
</script>
</body>
</html>
"""


class MoleculeViewer(QWebEngineView):
    """Call .update_view(receptor_pdb_text, ligand_pdbqt_text, box_dict) to redraw."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.update_view(None, None, None)

    def update_view(self, receptor_pdb_text: str | None, ligand_pdbqt_text: str | None,
                     box: dict | None):
        import json
        html = _HTML_TEMPLATE.format(
            receptor_json=json.dumps(receptor_pdb_text),
            ligand_json=json.dumps(ligand_pdbqt_text),
            box_json=json.dumps(box),
        )
        self.setHtml(html)
