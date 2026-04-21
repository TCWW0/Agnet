from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any, Optional

from unstructured.partition.pdf import partition_pdf

from .config import PartitionStrategy
from .models import ElementCoordinates, ElementMetadata, ElementRecord


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _convert_coordinates(raw_coordinates: Any) -> Optional[ElementCoordinates]:
    if raw_coordinates is None:
        return None

    points: list[list[float]] = []
    raw_points = getattr(raw_coordinates, "points", None)
    if raw_points:
        for point in raw_points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x_value = _to_float(point[0])
            y_value = _to_float(point[1])
            if x_value is None or y_value is None:
                continue
            points.append([x_value, y_value])

    system = getattr(raw_coordinates, "system", None)
    coordinate_system = None
    if system is not None:
        coordinate_system = system.__class__.__name__

    layout_width = _to_float(getattr(raw_coordinates, "layout_width", None))
    layout_height = _to_float(getattr(raw_coordinates, "layout_height", None))

    if not points and layout_width is None and layout_height is None and coordinate_system is None:
        return None

    return ElementCoordinates(
        points=points,
        layout_width=layout_width,
        layout_height=layout_height,
        coordinate_system=coordinate_system,
    )


def _convert_metadata(raw_metadata: Any) -> ElementMetadata:
    if raw_metadata is None:
        return ElementMetadata()

    return ElementMetadata(
        filename=getattr(raw_metadata, "filename", None),
        filetype=getattr(raw_metadata, "filetype", None),
        page_number=_to_int(getattr(raw_metadata, "page_number", None)),
        detection_origin=getattr(raw_metadata, "detection_origin", None),
        coordinates=_convert_coordinates(getattr(raw_metadata, "coordinates", None)),
    )


def _build_element_id(index: int, element_type: str, page_number: Optional[int], text: str) -> str:
    source = f"{index}|{element_type}|{page_number}|{text}".encode("utf-8", errors="ignore")
    return sha1(source).hexdigest()[:16]


def parse_pdf_to_elements(
    pdf_path: Path,
    strategy: PartitionStrategy = "auto",
    include_page_breaks: bool = False,
) -> list[ElementRecord]:
    """Parse PDF into strongly-typed element records."""

    raw_elements = partition_pdf(
        filename=str(pdf_path),
        strategy=strategy,
        include_page_breaks=include_page_breaks,
    )

    records: list[ElementRecord] = []
    for index, element in enumerate(raw_elements):
        element_type = element.__class__.__name__
        text = (getattr(element, "text", "") or "").strip()

        # Keep page break markers when requested, but drop other empty elements.
        if not text and element_type != "PageBreak":
            continue

        metadata = _convert_metadata(getattr(element, "metadata", None))
        records.append(
            ElementRecord(
                element_id=_build_element_id(index, element_type, metadata.page_number, text),
                element_type=element_type,
                text=text,
                metadata=metadata,
            )
        )

    return records
