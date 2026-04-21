from __future__ import annotations

import html
from pathlib import Path

from .models import ChunkRecord


def export_chunk_report_html(chunks: list[ChunkRecord], output_path: Path) -> None:
    rows: list[str] = []
    for chunk in chunks:
        rows.append(
            """
            <tr>
              <td>{index}</td>
              <td>{chunk_id}</td>
              <td>{pages}</td>
              <td>{chars}</td>
              <td>{tokens}</td>
              <td><pre>{content}</pre></td>
            </tr>
            """.format(
                index=chunk.chunk_index,
                chunk_id=html.escape(chunk.chunk_id),
                pages=html.escape(f"{chunk.page_start} -> {chunk.page_end}"),
                chars=chunk.char_count,
                tokens=chunk.estimated_tokens,
                content=html.escape(chunk.markdown),
            )
        )

    rows_html = "\n".join(rows)
    document = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PDF Chunk Report</title>
  <style>
    body {{
      margin: 0;
      font-family: "Source Sans 3", "Noto Sans", sans-serif;
      background: #f2f3f5;
      color: #1f2937;
    }}
    header {{
      background: linear-gradient(120deg, #113b54, #1f8a70);
      color: #ffffff;
      padding: 20px 24px;
    }}
    main {{
      padding: 20px 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border: 1px solid #e5e7eb;
      padding: 10px;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #f9fafb;
      text-align: left;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    pre {{
      white-space: pre-wrap;
      margin: 0;
      font-family: "JetBrains Mono", "Fira Code", monospace;
      font-size: 12px;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <header>
    <h1>PDF Chunk Report</h1>
    <p>Review chunk boundaries, lengths, and markdown content.</p>
  </header>
  <main>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Chunk ID</th>
          <th>Pages</th>
          <th>Chars</th>
          <th>Tokens</th>
          <th>Content</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </main>
</body>
</html>
"""

    output_path.write_text(document, encoding="utf-8")
