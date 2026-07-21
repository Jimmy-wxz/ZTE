import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_markdown_tables_module():
    spec = importlib.util.spec_from_file_location(
        "markdown_tables_bold_under_test",
        ROOT / "recursive" / "utils" / "markdown_tables.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalize_markdown_tables = load_markdown_tables_module().normalize_markdown_tables


def test_normalize_markdown_tables_preserves_bold_markers_in_cells():
    markdown = "| Dimension | Note |\n| --- | --- |\n| Security | **Key capability** |\n"

    normalized = normalize_markdown_tables(markdown)

    assert "**Key capability**" in normalized
