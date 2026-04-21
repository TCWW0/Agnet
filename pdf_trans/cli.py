from __future__ import annotations

import argparse
from pathlib import Path

from .config import PipelineConfig
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert PDF to markdown + RAG chunks")
    parser.add_argument("--input", required=True, help="Path to input PDF")
    parser.add_argument("--output-dir", default="pdf_trans/outputs", help="Output directory")
    parser.add_argument(
        "--partition-strategy",
        choices=["auto", "fast", "hi_res", "ocr_only"],
        default="auto",
        help="unstructured partition strategy",
    )
    parser.add_argument(
        "--chunk-strategy",
        choices=["by_title", "static_chars"],
        default="by_title",
        help="chunking strategy",
    )
    parser.add_argument("--max-chars", type=int, default=1800, help="max chars in one chunk")
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=200,
        help="overlap chars between neighboring chunks",
    )
    parser.add_argument(
        "--include-page-breaks",
        action="store_true",
        help="include page break markers from parser",
    )
    parser.add_argument(
        "--no-html-report",
        action="store_true",
        help="disable HTML chunk inspection report",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = PipelineConfig(
        pdf_path=Path(args.input),
        output_dir=Path(args.output_dir),
        partition_strategy=args.partition_strategy,
        include_page_breaks=args.include_page_breaks,
        chunk_strategy=args.chunk_strategy,
        max_chunk_chars=args.max_chars,
        chunk_overlap_chars=args.overlap_chars,
        export_html_report=not args.no_html_report,
    )

    result = run_pipeline(config)

    print("Pipeline completed")
    print(f"elements: {result.elements_count}")
    print(f"chunks: {result.chunks_count}")
    print(f"markdown: {result.markdown_path}")
    print(f"elements_json: {result.elements_json_path}")
    print(f"chunks_ndjson: {result.chunks_ndjson_path}")
    print(f"chunks_preview: {result.chunks_preview_md_path}")
    if result.html_report_path:
        print(f"html_report: {result.html_report_path}")


if __name__ == "__main__":
    main()
