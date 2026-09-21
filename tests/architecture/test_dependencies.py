"""Protect the domain boundary using imports rather than installed UI packages."""

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_domain_has_no_outer_layer_imports():
    forbidden = {
        "streamlit",
        "plotly",
        "pandas",
        "sqlalchemy",
        "openpyxl",
        "pydantic",
        "application",
        "infrastructure",
        "visualization",
        "ui",
    }
    for source in (ROOT / "src/psd_analyzer/domain").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not set(name.split(".")) & forbidden, (source, name)


def test_core_imports_without_ui_or_database_packages():
    code = """
import sys
class BlockOuterPackages:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'streamlit','plotly','pandas','sqlalchemy','openpyxl'}:
            raise AssertionError('Unexpected outer dependency: '+fullname)
sys.meta_path.insert(0,BlockOuterPackages())
from psd_analyzer.domain.services.analysis import analyze_mixture
from psd_analyzer.domain.services.comparison import compare_results
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
