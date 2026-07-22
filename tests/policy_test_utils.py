import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "recursive" / "policy"
PACKAGE_NAME = "policy_under_test"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_policy_module(name: str):
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(POLICY_DIR)]
        sys.modules[PACKAGE_NAME] = package

    return _load_module(
        f"{PACKAGE_NAME}.{name}",
        POLICY_DIR / f"{name}.py",
    )
