from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ElementCoordinates(BaseModel):
    points: list[list[float]] = Field(default_factory=list)
    layout_width: Optional[float] = None
    layout_height: Optional[float] = None
    coordinate_system: Optional[str] = None


class ElementMetadata(BaseModel):
    filename: Optional[str] = None
    filetype: Optional[str] = None
    page_number: Optional[int] = None
    detection_origin: Optional[str] = None
    coordinates: Optional[ElementCoordinates] = None


class ElementRecord(BaseModel):
    element_id: str
    element_type: str
    text: str
    markdown: str = ""
    metadata: ElementMetadata


class ChunkRecord(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    markdown: str
    element_ids: list[str] = Field(default_factory=list)
    source_file: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    strategy: str
    estimated_tokens: int
    char_count: int
