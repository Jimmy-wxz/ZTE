import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_markdown_tables_module():
    spec = importlib.util.spec_from_file_location(
        "markdown_tables_under_test",
        ROOT / "recursive" / "utils" / "markdown_tables.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalize_markdown_tables = load_markdown_tables_module().normalize_markdown_tables


def test_normalize_markdown_table_adds_separator():
    markdown = """## 对比
| 维度 | A | B |
| 功能 | 支持 | 不支持 |
| 价格 | 高 | 低 |
后续文本"""

    normalized = normalize_markdown_tables(markdown)

    assert "| 维度 | A | B |" in normalized
    assert "| --- | --- | --- |" in normalized
    assert "\n\n后续文本" in normalized


def test_normalize_markdown_table_pads_short_rows():
    markdown = """| 维度 | A | B |
| --- | --- | --- |
| 功能 | 支持 |
| 价格 | 高 | 低 |"""

    normalized = normalize_markdown_tables(markdown)

    assert "| 功能 | 支持 |  |" in normalized


def test_normalize_inline_collapsed_table_rows():
    markdown = "| 维度 | A | B | | --- | --- | --- | | 功能 | 支持 | 不支持 |"

    normalized = normalize_markdown_tables(markdown)

    assert "| 维度 | A | B |" in normalized
    assert "| 功能 | 支持 | 不支持 |" in normalized
    assert normalized.count("\n") >= 2
