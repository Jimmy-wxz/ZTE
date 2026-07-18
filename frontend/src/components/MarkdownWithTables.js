import React from 'react';
import ReactMarkdown from 'react-markdown';

const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
const TABLE_SEPARATOR_RE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;

const isTableRow = (line) => TABLE_ROW_RE.test(line || '');
const isSeparatorRow = (line) => TABLE_SEPARATOR_RE.test(line || '');

const splitCells = (line) => {
  let text = String(line || '').trim();
  if (text.startsWith('|')) text = text.slice(1);
  if (text.endsWith('|')) text = text.slice(0, -1);
  return text.split('|').map((cell) => cell.trim());
};

const normalizePipeTables = (markdown) => {
  return String(markdown || '')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .split('\n')
    .flatMap((line) => {
      if ((line.match(/\|/g) || []).length >= 8 && line.includes('---')) {
        return line.replace(/\|\s+(?=\|)/g, '|\n').split('\n');
      }
      return [line];
    })
    .join('\n');
};

const parseTableBlock = (lines) => {
  const rows = lines
    .filter((line) => isTableRow(line) && !isSeparatorRow(line))
    .map(splitCells)
    .filter((cells) => cells.some((cell) => cell));

  if (rows.length < 2) return null;

  const columnCount = Math.max(...rows.map((row) => row.length));
  const paddedRows = rows.map((row) => {
    const padded = [...row];
    while (padded.length < columnCount) padded.push('');
    return padded;
  });

  return {
    headers: paddedRows[0],
    rows: paddedRows.slice(1),
  };
};

const segmentMarkdown = (markdown) => {
  const lines = normalizePipeTables(markdown).split('\n');
  const segments = [];
  let textBuffer = [];
  let i = 0;

  const flushText = () => {
    if (!textBuffer.length) return;
    segments.push({ type: 'markdown', content: textBuffer.join('\n') });
    textBuffer = [];
  };

  while (i < lines.length) {
    const line = lines[i];
    if (isTableRow(line) && isSeparatorRow(lines[i + 1])) {
      flushText();
      const tableLines = [line, lines[i + 1]];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        tableLines.push(lines[i]);
        i += 1;
      }
      const table = parseTableBlock(tableLines);
      if (table) {
        segments.push({ type: 'table', table });
      } else {
        segments.push({ type: 'markdown', content: tableLines.join('\n') });
      }
      continue;
    }

    textBuffer.push(line);
    i += 1;
  }

  flushText();
  return segments;
};

const MarkdownTable = ({ table }) => (
  <div className="markdown-table-wrapper">
    <table className="markdown-table">
      <thead>
        <tr>
          {table.headers.map((header, index) => (
            <th key={`h-${index}`}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row, rowIndex) => (
          <tr key={`r-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <td key={`c-${rowIndex}-${cellIndex}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const MarkdownWithTables = ({ children }) => {
  const segments = segmentMarkdown(children);

  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === 'table') {
          return <MarkdownTable key={`table-${index}`} table={segment.table} />;
        }
        return (
          <ReactMarkdown key={`markdown-${index}`}>
            {segment.content}
          </ReactMarkdown>
        );
      })}
    </>
  );
};

export default MarkdownWithTables;
