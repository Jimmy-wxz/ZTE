import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_get_index_module():
    module_names = [
        "recursive",
        "recursive.utils",
        "recursive.utils.file_io",
        "loguru",
    ]
    previous_modules = {name: sys.modules.get(name) for name in module_names}
    recursive_pkg = types.ModuleType("recursive")
    recursive_pkg.__path__ = [str(ROOT / "recursive")]
    utils_pkg = types.ModuleType("recursive.utils")
    utils_pkg.__path__ = [str(ROOT / "recursive" / "utils")]
    file_io = types.ModuleType("recursive.utils.file_io")
    file_io.auto_read = lambda *args, **kwargs: None
    file_io.auto_write = lambda *args, **kwargs: None
    loguru = types.ModuleType("loguru")
    loguru.logger = types.SimpleNamespace(
        warning=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["recursive"] = recursive_pkg
    sys.modules["recursive.utils"] = utils_pkg
    sys.modules["recursive.utils.file_io"] = file_io
    sys.modules["loguru"] = loguru

    spec = importlib.util.spec_from_file_location(
        "get_index_under_test",
        ROOT / "recursive" / "utils" / "get_index.py",
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


get_index = load_get_index_module()


def test_get_report_with_ref_makes_kb_and_web_citations_clickable():
    data = {
        "items": [
            {
                "global_index": 1,
                "url": "https://example.com/report",
                "title": "Example Market Report",
            },
            {
                "global_index": 2,
                "url": "local-kb://C:/kb/agc_platform.docx#chunk-7",
                "title": "C:/kb/agc_platform.docx",
            },
        ]
    }
    article = "公开资料显示存在外部趋势[reference:1]。内部资料显示平台能力稳定[reference:2]。"

    result = get_index.get_report_with_ref(data, article)

    assert "[[WEB:1]](https://example.com/report)" in result
    assert "[[KB:1]](#kb-ref-1)" in result
    assert "1. 🌐 **[WEB:1]** [Example Market Report](https://example.com/report)" in result
    assert '<span id="kb-ref-1"></span>**[KB:1]** agc_platform' in result
    assert "`C:/kb/agc_platform.docx`" in result
