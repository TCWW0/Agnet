from __future__ import annotations

from src.stream_framing import StreamFramer


def test_stream_framer_handles_marker_across_chunks() -> None:
    framer = StreamFramer(message_id="m1")

    frames = []
    frames.extend(framer.push_text("第一段<|PA"))
    frames.extend(framer.push_text("RA|>第二段"))
    frames.extend(framer.finalize())

    frame_types = [frame["type"] for frame in frames]
    assert frame_types == ["chunk", "paragraph", "chunk", "paragraph", "done"]

    paragraph_frames = [frame for frame in frames if frame["type"] == "paragraph"]
    assert paragraph_frames[0]["paragraphId"] == "p1"
    assert paragraph_frames[0]["text"] == "第一段"
    assert paragraph_frames[1]["paragraphId"] == "p2"
    assert paragraph_frames[1]["text"] == "第二段"

    seq_values = [frame["seq"] for frame in frames]
    assert seq_values == sorted(seq_values)


def test_stream_framer_flushes_trailing_partial_marker() -> None:
    framer = StreamFramer(message_id="m2")

    frames = []
    frames.extend(framer.push_text("ABC<|PA"))
    frames.extend(framer.finalize())

    chunk_frames = [frame for frame in frames if frame["type"] == "chunk"]
    paragraph_frames = [frame for frame in frames if frame["type"] == "paragraph"]
    done_frames = [frame for frame in frames if frame["type"] == "done"]

    assert len(chunk_frames) == 2
    merged_text = "".join(frame["text"] for frame in chunk_frames)
    assert merged_text == "ABC<|PA"
    assert len(paragraph_frames) == 1
    assert paragraph_frames[0]["text"] == "ABC<|PA"
    assert len(done_frames) == 1
