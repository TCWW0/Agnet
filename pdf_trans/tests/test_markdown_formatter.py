from __future__ import annotations

from pdf_trans.markdown_formatter import render_markdown
from pdf_trans.models import ElementMetadata, ElementRecord


def _make_element(index: int, element_type: str, text: str, page: int = 1) -> ElementRecord:
    return ElementRecord(
        element_id=f"e{index}",
        element_type=element_type,
        text=text,
        metadata=ElementMetadata(filename="sample.pdf", page_number=page),
    )


def test_render_markdown_basic_mapping() -> None:
    elements = [
        _make_element(1, "Title", "Main Title"),
        _make_element(2, "NarrativeText", "hello    world"),
        _make_element(3, "ListItem", "first item"),
        _make_element(4, "Table", "a | b"),
        _make_element(5, "Title", "Section One"),
        _make_element(6, "NarrativeText", "section content"),
    ]

    rendered, markdown = render_markdown(elements)

    assert len(rendered) == 6
    assert "# Main Title" in markdown
    assert "## Section One" in markdown
    assert "hello world" in markdown
    assert "- first item" in markdown
    assert "```table" in markdown


def test_render_markdown_skips_page_counter_noise() -> None:
    elements = [
        _make_element(1, "Title", "Paper Title"),
        _make_element(2, "NarrativeText", "1"),
        _make_element(3, "NarrativeText", "Valid paragraph."),
    ]

    _, markdown = render_markdown(elements)

    assert "\n\n1\n\n" not in markdown
    assert "Valid paragraph." in markdown


def test_render_markdown_does_not_force_lowercase_title_to_heading() -> None:
    elements = [
        _make_element(1, "Title", "Main Section"),
        _make_element(2, "Title", "incorrect data, perhaps because of hardware faults"),
    ]

    _, markdown = render_markdown(elements)

    assert "# Main Section" in markdown
    assert "## incorrect data" not in markdown
    assert "incorrect data, perhaps because of hardware faults" in markdown


def test_render_markdown_promotes_sentence_case_title() -> None:
    elements = [
        _make_element(1, "Title", "Main Section"),
        _make_element(2, "Title", "Duplicate message suppression"),
    ]

    _, markdown = render_markdown(elements)

    assert "## Duplicate message suppression" in markdown


def test_render_markdown_promotes_inline_references_heading() -> None:
    elements = [
        _make_element(1, "Title", "Main Section"),
        _make_element(2, "NarrativeText", "References 1. First entry."),
    ]

    _, markdown = render_markdown(elements)

    assert "## References" in markdown
    assert "1. First entry." in markdown


def test_render_markdown_promotes_header_element_as_heading() -> None:
    elements = [
        _make_element(1, "Title", "Main Section"),
        _make_element(2, "Header", "Transaction management"),
    ]

    _, markdown = render_markdown(elements)

    assert "## Transaction management" in markdown
