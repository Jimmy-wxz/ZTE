# coding:utf8

import re
from typing import List


TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def _is_pipe_row(line: str) -> bool:
    stripped = str(line or "").strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _split_cells(line: str) -> List[str]:
    text = str(line or "").strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _is_separator_row(line: str) -> bool:
    cells = _split_cells(line)
    return bool(cells) and all(TABLE_SEPARATOR_CELL_RE.match(cell or "") for cell in cells)


def _format_row(cells: List[str], column_count: int) -> str:
    padded = list(cells[:column_count])
    while len(padded) < column_count:
        padded.append("")
    return "| " + " | ".join(padded) + " |"


def _format_separator(column_count: int) -> str:
    return "| " + " | ".join(["---"] * column_count) + " |"


def _normalize_table_block(block: List[str]) -> List[str]:
    rows = [line for line in block if _is_pipe_row(line)]
    if len(rows) < 2:
        return block

    data_rows = [line for line in rows if not _is_separator_row(line)]
    if len(data_rows) < 2:
        return block

    column_count = max(len(_split_cells(line)) for line in data_rows)
    if column_count < 2:
        return block

    normalized = [
        _format_row(_split_cells(data_rows[0]), column_count),
        _format_separator(column_count),
    ]
    for row in data_rows[1:]:
        normalized.append(_format_row(_split_cells(row), column_count))
    return normalized


def normalize_markdown_tables(markdown: str) -> str:
    """Normalize Markdown pipe tables before saving/rendering reports.

    LLMs sometimes omit the separator row, produce inconsistent column counts,
    or leave tables adjacent to paragraphs. This keeps ordinary prose untouched
    while making obvious pipe-table blocks valid GitHub-flavored Markdown.
    """
    raw_lines = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: List[str] = []
    for line in raw_lines:
        if line.count("|") >= 8 and "---" in line:
            lines.extend(re.sub(r"\|\s+(?=\|)", "|\n", line).split("\n"))
        else:
            lines.append(line)
    output: List[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not _is_pipe_row(line):
            output.append(line)
            i += 1
            continue

        block = []
        while i < len(lines) and _is_pipe_row(lines[i]):
            block.append(lines[i])
            i += 1

        normalized = _normalize_table_block(block)
        if normalized != block and output and output[-1].strip():
            output.append("")
        output.extend(normalized)
        if normalized != block and i < len(lines) and lines[i].strip():
            output.append("")

    return "\n".join(output)
