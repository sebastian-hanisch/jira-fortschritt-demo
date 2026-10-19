"""Laufzeit-Importe: jede Bibliothek, die app.py oder ein Modul im Wurzelordner importiert, steht in requirements.txt.

Lokal und in der CI ist requirements-dev.txt installiert, ein fehlendes Laufzeitpaket fällt dort also nicht auf; die Cloud
installiert nur requirements.txt (projektauswahl-demo brach 2026-09-25 mit ModuleNotFoundError). Bibliotheken nur für
Gegenproben (networkx, scikit-learn) gehören in requirements-dev.txt und werden nur unter tests/ importiert, das hier nicht
gescannt wird."""

import ast
import re
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Importname -> Distributionsname, falls das Paket nicht installiert ist (sonst löst importlib.metadata es selbst auf)
ALIASES = {"sklearn": "scikit-learn", "PIL": "pillow", "yaml": "pyyaml", "fpdf": "fpdf2", "cv2": "opencv-python"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements() -> set[str]:
    listed: set[str] = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line.split("#")[0].strip())
        if m:
            listed.add(_norm(m.group(0)))
    return listed


def _imports() -> dict[str, str]:
    """Importname (oberste Ebene) -> erste Datei, die ihn importiert; ohne Standardbibliothek und eigene Module."""
    local = {p.stem for p in ROOT.glob("*.py")} | {p.parent.name for p in ROOT.glob("*/__init__.py")}
    found: dict[str, str] = {}
    for path in sorted(ROOT.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name not in sys.stdlib_module_names and name not in local:
                    found.setdefault(name, path.name)
    return found


def test_jede_importierte_bibliothek_steht_in_requirements():
    listed = _requirements()
    dists = packages_distributions()
    missing = []
    for module, where in sorted(_imports().items()):
        names = {_norm(d) for d in dists.get(module, [])} or {_norm(ALIASES.get(module, module))}
        if not names & listed:
            missing.append(f"{module} (importiert in {where}; Distribution: {', '.join(sorted(names))})")
    assert not missing, "nicht in requirements.txt: " + "; ".join(missing)
