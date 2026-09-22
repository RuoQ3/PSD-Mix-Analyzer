"""Protect the domain boundary using imports rather than installed UI packages."""

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _assert_import_boundary(directory, forbidden):
    for source in directory.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [module, *(f"{module}.{item.name}" for item in node.names)]
            for name in names:
                assert not set(name.split(".")) & forbidden, (source, name)


def test_application_only_uses_domain_and_standard_library():
    _assert_import_boundary(
        ROOT / "src/psd_analyzer/application",
        {
            "plotly",
            "streamlit",
            "openpyxl",
            "pandas",
            "sqlalchemy",
            "infrastructure",
            "visualization",
            "ui",
            "numpy",
            "scipy",
        },
    )


def test_visualization_only_consumes_readonly_results():
    _assert_import_boundary(
        ROOT / "src/psd_analyzer/visualization",
        {
            "services",
            "use_cases",
            "infrastructure",
            "openpyxl",
            "pandas",
            "sqlalchemy",
            "streamlit",
            "q_fitting",
            "mixing",
            "psd_mixing",
            "policies",
            "ui",
        },
    )


def test_application_imports_without_presentation_and_io():
    code = """
import sys
class BlockOuter:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'plotly','streamlit','openpyxl','pandas','sqlalchemy'}:
            raise AssertionError('Unexpected outer dependency: '+fullname)
sys.meta_path.insert(0,BlockOuter())
from psd_analyzer.application.use_cases import AnalyzeRecipePSD, ComparePSDAnalysis
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)


def test_plot_builders_import_without_business_services():
    code = """
import sys
class BlockBusiness:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('psd_analyzer.domain.services',
                                'psd_analyzer.application.use_cases',
                                'psd_analyzer.infrastructure')):
            raise AssertionError('Unexpected business dependency: '+fullname)
sys.meta_path.insert(0,BlockBusiness())
from psd_analyzer.visualization import build_psd_figure
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)


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


def test_excel_has_no_numerical_service_dependencies():
    forbidden = {
        "scipy",
        "packing_models",
        "q_fitting",
        "metrics",
        "analysis",
        "psd_mixing",
        "mixing",
        "interpolation",
        "streamlit",
        "plotly",
        "sqlalchemy",
    }
    for source in (ROOT / "src/psd_analyzer/infrastructure/excel").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
                if (node.module or "").endswith("domain"):
                    names += [item.name for item in node.names]
            for name in names:
                assert not set(name.split(".")) & (forbidden | {"services"}), (source, name)


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


def test_metadata_free_mixing_service_has_no_business_or_fitting_imports():
    source = ROOT / "src/psd_analyzer/domain/services/psd_mixing.py"
    forbidden = {
        "recipe",
        "material",
        "basis_conversion",
        "mixing",
        "analysis",
        "q_fitting",
        "packing_models",
        "streamlit",
        "plotly",
        "pandas",
        "sqlalchemy",
        "openpyxl",
    }
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.ImportFrom):
            assert not set((node.module or "").split(".")) & forbidden
        if isinstance(node, ast.Import):
            for item in node.names:
                assert not set(item.name.split(".")) & forbidden


def test_mass_only_mix_runs_without_fitting_or_outer_modules():
    code = """
import sys
class BlockUnneeded:
    def find_spec(self, fullname, path=None, target=None):
        outer = {'scipy','streamlit','plotly','pandas','sqlalchemy','openpyxl'}
        if fullname.split('.')[0] in outer:
            raise AssertionError('Unexpected dependency: '+fullname)
        if fullname.split('.')[-1] in {'q_fitting','packing_models','basis_conversion','mixing'}:
            raise AssertionError('Unexpected business or fitting dependency: '+fullname)
sys.meta_path.insert(0,BlockUnneeded())
from psd_analyzer.domain.models.psd import PSD
from psd_analyzer.domain.services.psd_mixing import PSDMixingService
from psd_analyzer.domain.services.interpolation import LinearInterpolator
p=PSD((10,100),(0.2,0.8))
assert PSDMixingService().mix((p,),(1,),LinearInterpolator()) == p
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
