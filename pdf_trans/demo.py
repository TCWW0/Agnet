from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    # Allow `python pdf_trans/demo.py` from workspace root.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_trans.config import PipelineConfig
from pdf_trans.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PDF->Markdown demo pipeline")
    parser.add_argument(
        "--input",
        default="/root/agent/pdf_trans/endtoend.pdf",
        help="Input PDF path",
    )
    parser.add_argument(
        "--output-dir",
        default="/root/agent/pdf_trans/outputs",
        help="Output directory for markdown/chunks",
    )
    parser.add_argument(
        "--partition-strategy",
        default="auto",
        choices=["auto", "fast", "hi_res", "ocr_only"],
        help="unstructured partition strategy",
    )
    parser.add_argument(
        "--chunk-strategy",
        default="by_title",
        choices=["by_title", "static_chars"],
        help="chunking strategy",
    )
    parser.add_argument("--max-chars", type=int, default=1800, help="max chars per chunk")
    parser.add_argument("--overlap-chars", type=int, default=200, help="overlap chars")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    config = PipelineConfig(
        pdf_path=Path(args.input),
        output_dir=Path(args.output_dir),
        partition_strategy=args.partition_strategy,
        chunk_strategy=args.chunk_strategy,
        max_chunk_chars=args.max_chars,
        chunk_overlap_chars=args.overlap_chars,
    )
    result = run_pipeline(config)

    print("Demo finished")
    print(f"elements: {result.elements_count}")
    print(f"chunks: {result.chunks_count}")
    print(f"markdown: {result.markdown_path}")
    print(f"chunks preview: {result.chunks_preview_md_path}")
    if result.html_report_path:
        print(f"html report: {result.html_report_path}")


if __name__ == "__main__":
    main()