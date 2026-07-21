import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "recursive" / "evidence"
PACKAGE_NAME = "evidence_under_test"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_evidence_modules():
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(EVIDENCE_DIR)]
    sys.modules[PACKAGE_NAME] = package

    ledger = _load_module(
        f"{PACKAGE_NAME}.ledger",
        EVIDENCE_DIR / "ledger.py",
    )
    rubric = _load_module(
        f"{PACKAGE_NAME}.rubric",
        EVIDENCE_DIR / "rubric.py",
    )
    return ledger, rubric


def load_evidence_graph_module():
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(EVIDENCE_DIR)]
        sys.modules[PACKAGE_NAME] = package

    return _load_module(
        f"{PACKAGE_NAME}.graph",
        EVIDENCE_DIR / "graph.py",
    )


def load_evidence_module(name: str):
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(EVIDENCE_DIR)]
        sys.modules[PACKAGE_NAME] = package

    return _load_module(
        f"{PACKAGE_NAME}.{name}",
        EVIDENCE_DIR / f"{name}.py",
    )
